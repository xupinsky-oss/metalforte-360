import io,json,logging,os,shutil,sys,unicodedata,zipfile
from datetime import datetime
from pathlib import Path
import pandas as pd
from src.totvs import TotvsGoodDataConnector,REPORTS,INDICATOR_REPORTS,DETAIL_REPORTS,FUNNEL_INDICATOR_REPORTS,FUNNEL_DETAIL_REPORTS,FUNNEL_DATE_REPORTS
from src.secure_credentials import load_credential
from src.cloud_storage import download_bytes,is_configured,upload_file,upload_status
from src.targets import consolidate_targets,merge_target_history

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; RAW=DATA/'raw'; BACKUP=DATA/'backup'; LOGS=ROOT/'logs'
ACTIVE=DATA/'metalforte_base.csv.gz'; CREDENTIAL=ROOT/'.streamlit'/'gooddata_credential.bin'
ACTIVE_TARGETS=DATA/'metalforte_metas.csv.gz'; ACTIVE_FLOW=DATA/'metalforte_fluxo.csv.gz'
INDICATORS=DATA/'indicadores_comerciais.json'
PRODUCT_MATRIX=ROOT/'resources'/'produtos_classificacao.csv.gz'
WORKSPACE=os.getenv('TOTVS_WORKSPACE','sltez8zoyskp9vazf6jomo5askrbntnl')
DASHBOARD=os.getenv('TOTVS_DASHBOARD','11078478')
BASE_URL=os.getenv('TOTVS_BASE_URL','https://analytics.totvs.com.br')
FINAL_COLUMNS=['Data','Data Pedido','Mes','Ano','Fonte Data','Filial','Vendedor','Cod Cliente','Cliente','UF','Município','Geo Fonte','Segmento Cliente','Tipologia Cliente','Curva Cliente','Pedido','NF','Produto Codigo','Produto','Fonte Classificação Produto','Grupo Produto','Subgrupo Produto','Tipo Produto','ESPEC.','Sub Espec.','Espessura','CFOP','TES','Faturamento','Peso','Preço Real Kg','Benchmark Grupo','Desvio Benchmark %','Custo','Impostos','PIS','COFINS','ICMS','Margem','Margem %']

for p in (RAW,BACKUP,LOGS): p.mkdir(parents=True,exist_ok=True)
logging.basicConfig(filename=LOGS/'atualizacao_gooddata.log',level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s',encoding='utf-8')

def credentials():
    return load_credential()

def parse_raw(content,allow_single_column=False):
    if content[:2]==b'PK':
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            names=[n for n in z.namelist() if n.lower().endswith(('.csv','.txt'))]
            if not names: raise ValueError('ZIP do GoodData sem CSV.')
            content=z.read(names[0])
    for encoding in ('utf-8-sig','utf-16','latin-1'):
        for sep in (',',';','\t'):
            try:
                frame=pd.read_csv(io.BytesIO(content),encoding=encoding,sep=sep,low_memory=False)
                if frame.shape[1]>1 or (allow_single_column and frame.shape[1]==1): return frame
            except Exception: pass
    raise ValueError('Formato RAW não reconhecido.')

def _key(series):
    return pd.to_numeric(series,errors='coerce').astype('Int64').astype('string')

def prepare_product_matrix(frame):
    """Normaliza a matriz comercial e garante uma classificação por produto."""
    required=['Produto Codigo','Tipo Produto Matriz','Grupo Produto Matriz','Subgrupo Produto','ESPEC.','Sub Espec.','Espessura Matriz']
    missing=[column for column in required if column not in frame.columns]
    if missing: raise ValueError(f'Matriz de produtos sem colunas obrigatórias: {missing}')
    result=frame[required].copy()
    result['Produto Codigo']=_key(result['Produto Codigo'])
    for column in required[1:-1]:
        result[column]=result[column].astype('string').str.strip().replace('',pd.NA)
    result['Espessura Matriz']=pd.to_numeric(result['Espessura Matriz'],errors='coerce')
    result=result.dropna(subset=['Produto Codigo'])
    duplicated=result['Produto Codigo'].duplicated(keep=False)
    if duplicated.any():
        examples=result.loc[duplicated,'Produto Codigo'].drop_duplicates().head(5).tolist()
        raise ValueError(f'Matriz de produtos possui códigos duplicados: {examples}')
    result['Fonte Classificação Produto']='Matriz Ecommerce'
    return result

def load_product_matrix(path=PRODUCT_MATRIX):
    path=Path(path)
    if not path.exists(): raise FileNotFoundError(f'Matriz de produtos não encontrada: {path}')
    return prepare_product_matrix(pd.read_csv(path,sep=';',compression='infer',encoding='utf-8-sig',low_memory=False,dtype={'Produto Codigo':'string'}))

def _parse_indicator_value(value):
    """Converte os formatos exportados pelo GoodData (R$ e Kg) em número."""
    text=str(value).replace('\u00a0',' ').replace('R$','').replace('Kg','').replace('KG','').strip()
    text=''.join(ch for ch in text if ch.isdigit() or ch in '.,-')
    if not text or text in {'-','.',','}: return None
    if ',' in text and '.' in text:
        text=text.replace('.','').replace(',','.') if text.rfind(',')>text.rfind('.') else text.replace(',','')
    elif ',' in text:
        text=text.replace(',','.')
    try: return float(text)
    except ValueError: return None

def extract_indicator(frame):
    values=[]
    for value in frame.astype(str).to_numpy().ravel():
        parsed=_parse_indicator_value(value)
        if parsed is not None: values.append(parsed)
    if not values: raise ValueError('Indicador GoodData retornou sem valor numérico.')
    # Relatórios de indicador possuem uma medida e eventualmente ano/mês no
    # export. O maior valor absoluto é a medida, não o rótulo do período.
    return max(values,key=abs)

def sum_detail_measure(frame, column_hint):
    """Soma uma medida de relatório analítico sem misturar valor e peso."""
    candidates=[column for column in frame.columns if column_hint.casefold() in str(column).casefold()]
    if not candidates:
        raise ValueError(f"Coluna '{column_hint}' não encontrada no detalhamento.")
    values=frame[candidates[0]].map(_parse_indicator_value).dropna()
    if values.empty:
        raise ValueError(f"Coluna '{candidates[0]}' não retornou valores numéricos.")
    return float(values.sum())

def _flow_name(value):
    return ''.join(ch for ch in unicodedata.normalize('NFKD',str(value)).lower() if not unicodedata.combining(ch)).replace('.','').replace(' ','')

def _flow_column(frame, *names):
    normalized={_flow_name(column):column for column in frame.columns}
    for name in names:
        key=_flow_name(name)
        if key in normalized: return normalized[key]
    return None

def _flow_series(frame, *names, date=False):
    column=_flow_column(frame,*names)
    values=frame[column] if column else pd.Series(pd.NA,index=frame.index)
    return pd.to_datetime(values,dayfirst=True,errors='coerce') if date else values

def build_flow_timeline(frames):
    """Normaliza eventos oficiais sem imputar datas ausentes."""
    columns=['Origem','Modalidade','Pedido','Item','OP','Data Orçamento','Data Pedido','Data Liberação','Data Emissão OP','Data Confirmação OP','Data OS','Data Montagem Carga','Data Emissão NF','Data Saída','Hora Saída','Data Desejo Cliente','Data Previsão Entrega','Data Produção','Peso','Valor']
    rows=[]
    for name,modalidade in (('fluxo_liberados_cif','CIF'),('fluxo_liberados_fob','FOB')):
        frame=frames.get(name)
        if frame is None or frame.empty: continue
        item=pd.DataFrame({'Origem':'Pedido liberado','Modalidade':modalidade,'Pedido':_flow_series(frame,'Nº Pedido','N Pedido'),'Item':_flow_series(frame,'Item'),'OP':pd.NA,'Data Orçamento':pd.NaT,'Data Pedido':_flow_series(frame,'Emiss. PV','Emiss PV',date=True),'Data Liberação':_flow_series(frame,'Lib. PV','Lib PV',date=True),'Data Emissão OP':_flow_series(frame,'Emissão OP','Emissao OP',date=True),'Data Confirmação OP':_flow_series(frame,'Confirm. OP','Confirm OP',date=True),'Data OS':_flow_series(frame,'Data O.S.','Data OS',date=True),'Data Montagem Carga':_flow_series(frame,'Mont. Carga','Mont Carga',date=True),'Data Emissão NF':_flow_series(frame,'Emiss. NF','Emiss NF',date=True),'Data Saída':_flow_series(frame,'Data Saída','Data Saida',date=True),'Hora Saída':_flow_series(frame,'Hora Saída','Hora Saida'),'Data Desejo Cliente':_flow_series(frame,'Desejo Cli.','Desejo Cli',date=True),'Data Previsão Entrega':pd.NaT,'Data Produção':pd.NaT,'Peso':_flow_series(frame,'Peso Pedidos'),'Valor':_flow_series(frame,'Vlr. Pedidos','Vlr Pedidos')})
        rows.append(item)
    quote=frames.get('orcamentos_abertos_detalhe')
    if quote is not None and not quote.empty:
        rows.append(pd.DataFrame({'Origem':'Orçamento em aberto','Modalidade':pd.NA,'Pedido':_flow_series(quote,'Pedido'),'Item':pd.NA,'OP':pd.NA,'Data Orçamento':_flow_series(quote,'Emissão','Emissao',date=True),'Data Pedido':pd.NaT,'Data Liberação':pd.NaT,'Data Emissão OP':pd.NaT,'Data Confirmação OP':pd.NaT,'Data OS':pd.NaT,'Data Montagem Carga':pd.NaT,'Data Emissão NF':pd.NaT,'Data Saída':pd.NaT,'Hora Saída':pd.NA,'Data Desejo Cliente':pd.NaT,'Data Previsão Entrega':pd.NaT,'Data Produção':pd.NaT,'Peso':_flow_series(quote,'Peso'),'Valor':_flow_series(quote,'Total')}))
    op=frames.get('op_sob_encomenda')
    if op is not None and not op.empty:
        # A OP não possui uma chave de pedido confiável neste relatório. Ela é
        # preservada como trilha produtiva independente, sem forçar uma junção.
        rows.append(pd.DataFrame({'Origem':'OP sob encomenda','Modalidade':pd.NA,'Pedido':pd.NA,'Item':_flow_series(op,'Item'),'OP':_flow_series(op,'OP'),'Data Orçamento':pd.NaT,'Data Pedido':pd.NaT,'Data Liberação':pd.NaT,'Data Emissão OP':_flow_series(op,'Emissão','Emissao',date=True),'Data Confirmação OP':_flow_series(op,'Confirma.','Confirma',date=True),'Data OS':pd.NaT,'Data Montagem Carga':pd.NaT,'Data Emissão NF':pd.NaT,'Data Saída':pd.NaT,'Hora Saída':pd.NA,'Data Desejo Cliente':_flow_series(op,'Desejo',date=True),'Data Previsão Entrega':_flow_series(op,'Previsão Entr.','Previsao Entr.',date=True),'Data Produção':_flow_series(op,'Produção','Producao',date=True),'Peso':_flow_series(op,'Kg Aberto'),'Valor':pd.NA}))
    result=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame(columns=columns)
    for column in ('Peso','Valor'): result[column]=result[column].map(_parse_indicator_value)
    # Exportações do GoodData podem trazer rodapés (Sum/Rollup). Remove-os
    # apenas quando a linha deveria ser um pedido/orçamento, mantendo as OPs.
    if not result.empty:
        pedido=result['Pedido'].astype('string').str.strip()
        is_order=result['Origem'].isin(['Pedido liberado','Orçamento em aberto'])
        result=result[~is_order | (pedido.notna() & ~pedido.str.casefold().isin(['','sum','rollup']))]
        op_key=result['OP'].astype('string').str.strip()
        is_production=result['Origem'].eq('OP sob encomenda')
        result=result[~is_production | (op_key.notna() & ~op_key.str.casefold().isin(['','sum','rollup']))]
    return result.reindex(columns=columns)

def collect_target_periods(con,current_detail,current_value):
    """Lê metas mensais anteriores e futuras sem misturar competências."""
    offset_from=int(os.getenv('TOTVS_TARGET_OFFSET_FROM','-12'))
    offset_to=int(os.getenv('TOTVS_TARGET_OFFSET_TO','12'))
    if offset_from>offset_to or offset_from < -24 or offset_to > 24:
        raise ValueError('Intervalo de competências da meta inválido; use limites entre -24 e 24 meses.')
    base_competence=pd.Timestamp.today().to_period('M').start_time
    periods=[]
    for offset in range(offset_from,offset_to+1):
        competence=base_competence+pd.DateOffset(months=offset)
        try:
            if offset==0:
                detail,value=current_detail,current_value
            else:
                detail=parse_raw(con.raw_report(
                    DETAIL_REPORTS['meta_kg_vendedor_grupo'],offset_from=offset,offset_to=offset
                ))
                value=parse_raw(con.raw_report(
                    INDICATOR_REPORTS['meta_valor'],offset_from=offset,offset_to=offset
                ),allow_single_column=True)
            period=consolidate_targets(detail,value,competence)
            periods.append(period)
            logging.info('Meta %s: %s linhas',competence.strftime('%Y-%m'),len(period))
        except Exception as exc:
            if offset==0:
                raise
            logging.warning('Meta %s indisponível (%s): %s',competence.strftime('%Y-%m'),type(exc).__name__,str(exc))
    if not periods:
        raise ValueError('Nenhuma competência válida de meta foi retornada pelo GoodData.')
    return pd.concat(periods,ignore_index=True)

def consolidate(downloaded,product_matrix=None):
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
    keep_cli=['NF Chave','Item Chave','Cod Cliente','Pedido','Data Pedido','Margem CP %']
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
    x['Data']=pd.to_datetime(x['Data'],dayfirst=True,errors='coerce'); x['Data Pedido']=pd.to_datetime(x['Data Pedido'],dayfirst=True,errors='coerce'); x['Mes']=x['Data'].dt.strftime('%Y-%m'); x['Ano']=x['Data'].dt.year
    bench['Mes']=pd.to_datetime(bench['Mes Benchmark'],format='%b %Y',errors='coerce').dt.strftime('%Y-%m')
    bench=bench.dropna(subset=['Mes']).drop_duplicates(['Mes','Grupo Produto'],keep='last')
    x=x.merge(bench[['Mes','Grupo Produto','Benchmark Grupo']],on=['Mes','Grupo Produto'],how='left')
    # O benchmark continua conciliado pelo grupo oficial do GoodData. A matriz
    # comercial passa a prevalecer somente depois dessa junção.
    matrix=load_product_matrix() if product_matrix is None else prepare_product_matrix(product_matrix)
    x=x.merge(matrix,on='Produto Codigo',how='left',validate='many_to_one')
    x['Grupo Produto']=x['Grupo Produto Matriz'].combine_first(x['Grupo Produto'])
    x['Tipo Produto']=x['Tipo Produto Matriz'].combine_first(x['Tipo Produto'])
    x['Espessura']=x['Espessura Matriz'].combine_first(pd.to_numeric(x['Espessura'],errors='coerce'))
    x=x.drop(columns=['Grupo Produto Matriz','Tipo Produto Matriz','Espessura Matriz'])
    numeric=['Faturamento','Peso','Preço Real Kg','Benchmark Grupo','Custo','Impostos','PIS','COFINS','ICMS','Margem','Margem M %','Margem CP %','Espessura']
    for c in numeric: x[c]=pd.to_numeric(x[c],errors='coerce')
    x['Margem %']=x['Margem M %'].fillna(x['Margem CP %']); x['Margem']=x['Margem'].fillna(x['Margem %']*x['Faturamento'])
    x['Margem %']=x['Margem %'].fillna(x['Margem']/x['Faturamento'].replace(0,pd.NA)).fillna(0); x['Margem']=x['Margem'].fillna(0)
    x['Benchmark Grupo']=x['Benchmark Grupo'].fillna(0); x['Desvio Benchmark %']=(x['Preço Real Kg']/x['Benchmark Grupo'].replace(0,pd.NA)-1).fillna(0)
    for c in ['Custo','Impostos','PIS','COFINS','ICMS']: x[c]=x[c].fillna(0)
    x['UF']=x['UF'].fillna('Não mapeado'); x['Município']=x['Município'].fillna('Não mapeado'); x['Geo Fonte']=x['UF'].map(lambda v:'Código cliente' if v!='Não mapeado' else 'Não mapeado')
    x['Segmento Cliente']=x['Segmento Cliente'].fillna('Não classificado').astype(str).str.strip().replace('', 'Não classificado')
    x['Tipologia Cliente']=x['Tipologia Cliente'].fillna('Não classificado').astype(str).str.strip().replace('', 'Não classificado')
    for column in ['Grupo Produto','Subgrupo Produto','Tipo Produto','ESPEC.','Sub Espec.']:
        x[column]=x[column].fillna('Não mapeado')
    x['Fonte Classificação Produto']=x['Fonte Classificação Produto'].fillna('GoodData / não mapeado'); x['Fonte Data']='GoodData automático'
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
    indicators={}
    indicator_frames={}
    for name,report_id in INDICATOR_REPORTS.items():
        logging.info('Baixando indicador %s (%s)',name,report_id)
        content=con.raw_report(report_id,offset_from=0,offset_to=0)
        frame=parse_raw(content,allow_single_column=True)
        indicator_frames[name]=frame
        indicators[name]=round(extract_indicator(frame),4)
        logging.info('%s: %s',name,indicators[name])
    for name,report_id in FUNNEL_INDICATOR_REPORTS.items():
        logging.info('Baixando etapa do funil %s (%s)',name,report_id)
        try:
            frame=parse_raw(con.raw_report(report_id,offset_from=0,offset_to=0),allow_single_column=True)
            indicators[name]=round(extract_indicator(frame),4)
        except Exception as exc:
            # A ausência de uma etapa opcional não interrompe as cargas de
            # faturamento. O painel a indicará como indisponível.
            logging.warning('Etapa do funil indisponível %s: %s',name,type(exc).__name__)
    for name,(report_id,column_hint) in FUNNEL_DETAIL_REPORTS.items():
        logging.info('Baixando detalhamento do funil %s (%s)',name,report_id)
        try:
            frame=parse_raw(con.raw_report(report_id,offset_from=0,offset_to=0))
            indicators[name]=round(sum_detail_measure(frame,column_hint),4)
        except Exception as exc:
            logging.warning('Detalhamento do funil indisponível %s: %s',name,type(exc).__name__)
    flow_frames={}
    for name,report_id in FUNNEL_DATE_REPORTS.items():
        try:
            logging.info('Baixando eventos de data %s (%s)',name,report_id)
            flow_frames[name]=parse_raw(con.raw_report(report_id,offset_from=-90,offset_to=0))
        except Exception as exc:
            logging.warning('Eventos de data indisponíveis %s: %s',name,type(exc).__name__)
    # Os cartões 043/045 de peso já são exportados em kg. O multiplicador de
    # tonelada para kg aplica-se somente ao detalhamento da meta (relatório 044).
    weight_multiplier=float(os.getenv('TOTVS_INDICATOR_WEIGHT_MULTIPLIER','1'))
    for name in ('meta_peso','pedidos_nao_faturados_peso','pedidos_liberados_peso'):
        if name in indicators: indicators[name]=round(indicators[name]*weight_multiplier,4)
    detail_frames={}
    for name,report_id in DETAIL_REPORTS.items():
        logging.info('Baixando detalhamento %s (%s)',name,report_id)
        try:
            content=con.raw_report(report_id,offset_from=-36 if name=='carteira_clientes' else 0,offset_to=0)
        except Exception:
            if name=='carteira_clientes':
                logging.warning('Fonte complementar de carteira indisponível; a base consolidada será usada.',exc_info=True)
                continue
            raise
        frame=parse_raw(content); detail_frames[name]=frame
        (RAW/f'{name}_{stamp}.raw').write_bytes(content)
        frame.to_csv(RAW/f'{name}_atual.csv.gz',index=False,compression='gzip')
    main_df=consolidate(downloaded)
    current_targets=collect_target_periods(con,detail_frames['meta_kg_vendedor_grupo'],indicator_frames['meta_valor'])
    previous_targets=pd.DataFrame()
    try:
        if ACTIVE_TARGETS.exists(): previous_targets=pd.read_csv(ACTIVE_TARGETS,compression='gzip',low_memory=False)
        elif is_configured(): previous_targets=pd.read_csv(io.BytesIO(download_bytes(object_path=os.getenv('SUPABASE_TARGET_PATH','bases/metalforte_metas.csv.gz'))),compression='gzip',low_memory=False)
    except Exception as exc:
        logging.warning('Histórico anterior de metas indisponível: %s',type(exc).__name__)
    target_df=merge_target_history(previous_targets,current_targets)
    if len(main_df)<300000: raise ValueError(f'Base consolidada abaixo do mínimo de segurança: {len(main_df):,} linhas')
    if main_df['Data'].notna().mean()<.99: raise ValueError('Cobertura de datas abaixo de 99%.')
    source_total=pd.to_numeric(downloaded['faturamento'].iloc[:,9],errors='coerce').sum(); final_total=main_df['Faturamento'].sum()
    if source_total and abs(final_total/source_total-1)>.0001: raise ValueError('Total de faturamento divergiu na consolidação.')
    classified_revenue=main_df.loc[main_df['Segmento Cliente']!='Não classificado','Faturamento'].sum()
    classification_coverage=classified_revenue/final_total if final_total else 0
    if classification_coverage<.50: raise ValueError(f'Cobertura de classificação de clientes abaixo de 50%: {classification_coverage:.1%}')
    product_scope=main_df.dropna(subset=['Produto Codigo']).drop_duplicates('Produto Codigo')
    product_matrix_coverage=product_scope['Fonte Classificação Produto'].eq('Matriz Ecommerce').mean() if len(product_scope) else 0
    product_spec_coverage=product_scope['ESPEC.'].ne('Não mapeado').mean() if len(product_scope) else 0
    if product_matrix_coverage<.50: raise ValueError(f'Cobertura da matriz de produtos abaixo de 50%: {product_matrix_coverage:.1%}')
    if ACTIVE.exists(): shutil.copy2(ACTIVE,BACKUP/f'metalforte_base_{stamp}.csv.gz')
    tmp=DATA/'metalforte_base.nova.csv.gz'; main_df.to_csv(tmp,index=False,compression='gzip')
    cloud_updated=upload_file(tmp)
    tmp.replace(ACTIVE)
    target_tmp=DATA/'metalforte_metas.nova.csv.gz'; target_df.to_csv(target_tmp,index=False,compression='gzip')
    target_path=os.getenv('SUPABASE_TARGET_PATH','bases/metalforte_metas.csv.gz')
    target_cloud_updated=upload_file(target_tmp,object_path=target_path)
    target_tmp.replace(ACTIVE_TARGETS)
    flow=build_flow_timeline(flow_frames)
    flow_cloud_updated=False
    if not flow.empty:
        flow_tmp=DATA/'metalforte_fluxo.novo.csv.gz'; flow.to_csv(flow_tmp,index=False,compression='gzip')
        try:
            flow_cloud_updated=upload_file(flow_tmp,object_path=os.getenv('SUPABASE_FLOW_PATH','bases/metalforte_fluxo.csv.gz'))
            flow_tmp.replace(ACTIVE_FLOW)
        except Exception as exc:
            logging.warning('Publicação da tabela de eventos do funil indisponível: %s',type(exc).__name__)
            flow_tmp.unlink(missing_ok=True)
    indicator_sources={**INDICATOR_REPORTS,**FUNNEL_INDICATOR_REPORTS,**{name: report_id for name,(report_id,_hint) in FUNNEL_DETAIL_REPORTS.items()}}
    INDICATORS.write_text(json.dumps({'atualizado_em':datetime.now().astimezone().isoformat(),'fontes':indicator_sources,'valores':indicators},ensure_ascii=False),encoding='utf-8')
    logging.info('Base ativa substituída: %s linhas',len(main_df))
    current_competence=pd.Timestamp.today().to_period('M').start_time
    current_snapshot=current_targets[current_targets['Competência']==current_competence]
    result={'status':'ok','atualizado_em':datetime.now().astimezone().isoformat(),'raws':{k:len(v) for k,v in downloaded.items()},'indicadores':indicators,'base_substituida':True,'nuvem_atualizada':cloud_updated,'metas_publicadas':target_cloud_updated,'eventos_funil_publicados':flow_cloud_updated,'linhas_eventos_funil':len(flow),'linhas':len(main_df),'ultima_data':str(main_df['Data'].max().date()),'faturamento':round(final_total,2),'meta_competencia':str(current_competence.date()),'meta_linhas':len(current_snapshot),'meta_kg':round(float(current_snapshot['Meta KG'].sum()),2),'meta_valor':round(float(current_snapshot['Meta R$'].sum()),2),'meta_cobertura_inicio':str(current_targets['Competência'].min().date()),'meta_cobertura_fim':str(current_targets['Competência'].max().date()),'cobertura_classificacao_clientes':round(classification_coverage,6),'cobertura_matriz_produtos':round(product_matrix_coverage,6),'cobertura_espec_produtos':round(product_spec_coverage,6),'segmentos_clientes':int(main_df.loc[main_df['Segmento Cliente']!='Não classificado','Segmento Cliente'].nunique()),'tipologias_clientes':int(main_df.loc[main_df['Tipologia Cliente']!='Não classificado','Tipologia Cliente'].nunique())}
    upload_status(result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        logging.exception('Falha na atualização'); print(f'ERRO: {exc}',file=sys.stderr); raise
