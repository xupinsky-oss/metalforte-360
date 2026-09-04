import io,json,logging,os,shutil,sys,zipfile
from datetime import datetime
from pathlib import Path
import pandas as pd
from src.totvs import TotvsGoodDataConnector,REPORTS
from src.secure_credentials import load_credential
from src.cloud_storage import upload_file,upload_status

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; RAW=DATA/'raw'; BACKUP=DATA/'backup'; LOGS=ROOT/'logs'
ACTIVE=DATA/'metalforte_base.csv.gz'; CREDENTIAL=ROOT/'.streamlit'/'gooddata_credential.bin'
WORKSPACE=os.getenv('TOTVS_WORKSPACE','sltez8zoyskp9vazf6jomo5askrbntnl')
DASHBOARD=os.getenv('TOTVS_DASHBOARD','11078478')
BASE_URL=os.getenv('TOTVS_BASE_URL','https://analytics.totvs.com.br')
FINAL_COLUMNS=['Data','Mes','Ano','Fonte Data','Filial','Vendedor','Cod Cliente','Cliente','UF','Município','Geo Fonte','Segmento Cliente','Tipologia Cliente','Curva Cliente','Pedido','NF','Produto Codigo','Produto','Grupo Produto','Tipo Produto','Espessura','CFOP','TES','Faturamento','Peso','Preço Real Kg','Benchmark Grupo','Desvio Benchmark %','Custo','Impostos','PIS','COFINS','ICMS','Margem','Margem %']

for p in (RAW,BACKUP,LOGS): p.mkdir(parents=True,exist_ok=True)
logging.basicConfig(filename=LOGS/'atualizacao_gooddata.log',level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s',encoding='utf-8')

def credentials():
    return load_credential()

def parse_raw(content):
    if content[:2]==b'PK':
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            names=[n for n in z.namelist() if n.lower().endswith(('.csv','.txt'))]
            if not names: raise ValueError('ZIP do GoodData sem CSV.')
            content=z.read(names[0])
    for encoding in ('utf-8-sig','utf-16','latin-1'):
        for sep in (',',';','\t'):
            try:
                frame=pd.read_csv(io.BytesIO(content),encoding=encoding,sep=sep,low_memory=False)
                if frame.shape[1]>1: return frame
            except Exception: pass
    raise ValueError('Formato RAW não reconhecido.')

def _key(series):
    return pd.to_numeric(series,errors='coerce').astype('Int64').astype('string')

def consolidate(downloaded):
    fat=downloaded['faturamento'].copy(); fat.columns=['Filial','Data','Vendedor','Cliente','NF','Item','Produto','CFOP','TES','Faturamento','Peso','Preço Real Kg']
    cli=downloaded['clientes_pedidos'].copy(); cli.columns=['Vendedor CP','Cod Cliente','Cliente CP','Data Pedido','Pedido','NF','Item','Produto CP','Peso CP','Faturamento CP','Preço CP','Margem CP %']
    mar=downloaded['margem'].copy(); mar.columns=['Pedido M','NF','Item','Produto Codigo','Produto M','Margem M %','Margem','Preço M','Venda','Devolução','Faturamento M','Qtd Venda','Qtd Devolução','Qtd Faturada','Custo Unitário','Custo','COFINS','ICMS','PIS','Impostos']
    prod=downloaded['produto_classificacao'].copy(); prod.columns=['Produto Codigo','Produto Cadastro','Espessura','Grupo Produto','Tipo Produto','Peso Comercial','Peso Total']
    geo=downloaded['cliente_geo'].copy(); geo.columns=['Cod Cliente','Cliente Geo','UF','Município','Faturamento Geo']
    classification=downloaded['cliente_classificacao'].copy()
    expected_classification=['Cod Cliente','Loja Cliente','Cliente Classificação','CPF/CNPJ','Segmento Cliente','Tipologia Cliente','Vendedor Classificação','Vlr Venda Classificação','Faturamento Classificação','Qtd NF Classificação','Frequência','Última Compra Classificação','Recência','Margem Classificação %','Nota Margem','Soma Notas']
    if classification.shape[1] < 7:
        raise ValueError(f'Relatório de classificação de clientes incompleto: {classification.shape[1]} colunas')
    classification.columns=expected_classification[:classification.shape[1]] if classification.shape[1]<=len(expected_classification) else expected_classification+[f'Classificação Extra {i}' for i in range(classification.shape[1]-len(expected_classification))]
    bench=downloaded['preco_benchmark'].copy(); bench.columns=['Mes Benchmark','Grupo Produto','Benchmark Grupo']

    for d in (fat,cli,mar):
        d['NF Chave']=_key(d['NF']); d['Item Chave']=_key(d['Item'])
    cli=cli.sort_values(['NF Chave','Item Chave']).drop_duplicates(['NF Chave','Item Chave'],keep='last')
    mar=mar.sort_values(['NF Chave','Item Chave']).drop_duplicates(['NF Chave','Item Chave'],keep='last')
    keep_cli=['NF Chave','Item Chave','Cod Cliente','Pedido','Margem CP %']
    keep_mar=['NF Chave','Item Chave','Produto Codigo','Margem M %','Margem','Custo','Impostos','PIS','COFINS','ICMS']
    x=fat.merge(cli[keep_cli],on=['NF Chave','Item Chave'],how='left').merge(mar[keep_mar],on=['NF Chave','Item Chave'],how='left')
    x['Cod Cliente']=_key(x['Cod Cliente']); x['Produto Codigo']=_key(x['Produto Codigo'])
    prod['Produto Codigo']=_key(prod['Produto Codigo']); prod=prod.dropna(subset=['Produto Codigo']).drop_duplicates('Produto Codigo')
    geo['Cod Cliente']=_key(geo['Cod Cliente']); geo=geo.dropna(subset=['Cod Cliente']).sort_values('Faturamento Geo').drop_duplicates('Cod Cliente',keep='last')
    classification['Cod Cliente']=_key(classification['Cod Cliente'])
    classification=classification.dropna(subset=['Cod Cliente']).drop_duplicates('Cod Cliente',keep='last')
    x=x.merge(prod[['Produto Codigo','Grupo Produto','Tipo Produto','Espessura']],on='Produto Codigo',how='left')
    x=x.merge(geo[['Cod Cliente','UF','Município']],on='Cod Cliente',how='left')
    x=x.merge(classification[['Cod Cliente','Segmento Cliente','Tipologia Cliente']],on='Cod Cliente',how='left')
    geo_names=geo.assign(_cliente=geo['Cliente Geo'].astype(str).str.strip().str.upper())
    geo_names=geo_names[~geo_names['_cliente'].duplicated(keep=False)].set_index('_cliente')
    name_key=x['Cliente'].astype(str).str.strip().str.upper()
    x['Cod Cliente']=x['Cod Cliente'].fillna(name_key.map(geo_names['Cod Cliente']))
    x['UF']=x['UF'].fillna(name_key.map(geo_names['UF'])); x['Município']=x['Município'].fillna(name_key.map(geo_names['Município']))
    x['Data']=pd.to_datetime(x['Data'],dayfirst=True,errors='coerce'); x['Mes']=x['Data'].dt.strftime('%Y-%m'); x['Ano']=x['Data'].dt.year
    bench['Mes']=pd.to_datetime(bench['Mes Benchmark'],format='%b %Y',errors='coerce').dt.strftime('%Y-%m')
    bench=bench.dropna(subset=['Mes']).drop_duplicates(['Mes','Grupo Produto'],keep='last')
    x=x.merge(bench[['Mes','Grupo Produto','Benchmark Grupo']],on=['Mes','Grupo Produto'],how='left')
    numeric=['Faturamento','Peso','Preço Real Kg','Benchmark Grupo','Custo','Impostos','PIS','COFINS','ICMS','Margem','Margem M %','Margem CP %','Espessura']
    for c in numeric: x[c]=pd.to_numeric(x[c],errors='coerce')
    x['Margem %']=x['Margem M %'].fillna(x['Margem CP %']); x['Margem']=x['Margem'].fillna(x['Margem %']*x['Faturamento'])
    x['Margem %']=x['Margem %'].fillna(x['Margem']/x['Faturamento'].replace(0,pd.NA)).fillna(0); x['Margem']=x['Margem'].fillna(0)
    x['Benchmark Grupo']=x['Benchmark Grupo'].fillna(0); x['Desvio Benchmark %']=(x['Preço Real Kg']/x['Benchmark Grupo'].replace(0,pd.NA)-1).fillna(0)
    for c in ['Custo','Impostos','PIS','COFINS','ICMS']: x[c]=x[c].fillna(0)
    x['UF']=x['UF'].fillna('Não mapeado'); x['Município']=x['Município'].fillna('Não mapeado'); x['Geo Fonte']=x['UF'].map(lambda v:'Código cliente' if v!='Não mapeado' else 'Não mapeado')
    x['Segmento Cliente']=x['Segmento Cliente'].fillna('Não classificado').astype(str).str.strip().replace('', 'Não classificado')
    x['Tipologia Cliente']=x['Tipologia Cliente'].fillna('Não classificado').astype(str).str.strip().replace('', 'Não classificado')
    x['Grupo Produto']=x['Grupo Produto'].fillna('Não mapeado'); x['Tipo Produto']=x['Tipo Produto'].fillna('Não mapeado'); x['Fonte Data']='GoodData automático'
    revenue=x.groupby('Cod Cliente',dropna=False)['Faturamento'].sum().sort_values(ascending=False); positive=revenue.clip(lower=0); cum=positive.cumsum()/positive.sum() if positive.sum() else positive
    curve=pd.Series('C',index=cum.index); curve[cum<=.90]='B'; curve[cum<=.70]='A'; x['Curva Cliente']=x['Cod Cliente'].map(curve).fillna('C')
    x['NF']=_key(x['NF']); x['Filial']=pd.to_numeric(x['Filial'],errors='coerce')
    return x[FINAL_COLUMNS]

def main():
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); cred=credentials()
    con=TotvsGoodDataConnector(BASE_URL,WORKSPACE,DASHBOARD); con.login(cred['login'],cred['password'])
    downloaded={}
    for name,report_id in REPORTS.items():
        logging.info('Baixando %s (%s)',name,report_id)
        content=con.raw_report(report_id,offset_from=-60,offset_to=0)
        (RAW/f'{name}_{stamp}.raw').write_bytes(content)
        frame=parse_raw(content); frame.to_csv(RAW/f'{name}_atual.csv.gz',index=False,compression='gzip')
        downloaded[name]=frame; logging.info('%s: %s linhas, %s colunas',name,len(frame),len(frame.columns))
    main_df=consolidate(downloaded)
    if len(main_df)<300000: raise ValueError(f'Base consolidada abaixo do mínimo de segurança: {len(main_df):,} linhas')
    if main_df['Data'].notna().mean()<.99: raise ValueError('Cobertura de datas abaixo de 99%.')
    source_total=pd.to_numeric(downloaded['faturamento'].iloc[:,9],errors='coerce').sum(); final_total=main_df['Faturamento'].sum()
    if source_total and abs(final_total/source_total-1)>.0001: raise ValueError('Total de faturamento divergiu na consolidação.')
    classified_revenue=main_df.loc[main_df['Segmento Cliente']!='Não classificado','Faturamento'].sum()
    classification_coverage=classified_revenue/final_total if final_total else 0
    if classification_coverage<.50: raise ValueError(f'Cobertura de classificação de clientes abaixo de 50%: {classification_coverage:.1%}')
    if ACTIVE.exists(): shutil.copy2(ACTIVE,BACKUP/f'metalforte_base_{stamp}.csv.gz')
    tmp=DATA/'metalforte_base.nova.csv.gz'; main_df.to_csv(tmp,index=False,compression='gzip')
    cloud_updated=upload_file(tmp)
    tmp.replace(ACTIVE)
    logging.info('Base ativa substituída: %s linhas',len(main_df))
    result={'status':'ok','atualizado_em':datetime.now().astimezone().isoformat(),'raws':{k:len(v) for k,v in downloaded.items()},'base_substituida':True,'nuvem_atualizada':cloud_updated,'linhas':len(main_df),'ultima_data':str(main_df['Data'].max().date()),'faturamento':round(final_total,2),'cobertura_classificacao_clientes':round(classification_coverage,6),'segmentos_clientes':int(main_df.loc[main_df['Segmento Cliente']!='Não classificado','Segmento Cliente'].nunique()),'tipologias_clientes':int(main_df.loc[main_df['Tipologia Cliente']!='Não classificado','Tipologia Cliente'].nunique())}
    upload_status(result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        logging.exception('Falha na atualização'); print(f'ERRO: {exc}',file=sys.stderr); raise
