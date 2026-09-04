import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import html
import json
from pathlib import Path
from src.data import load_data,apply_filters
from src.analytics import metrics,group_metrics,client_classification,quick_insights,forecast_year,price_analysis,build_opportunities,monitoring_snapshot,compare_periods,commercial_command_center,market_watch
from src.assistant import answer
from src.cloud_storage import download_status
from src.operational_dashboard import render as render_operational_dashboard

st.set_page_config(page_title="Metalforte 360",layout="wide",page_icon="🏭")
px.defaults.template="plotly_white"
px.defaults.color_discrete_sequence=["#F36A2D","#2F8FD8","#34B27B","#F2B84B","#A78BFA","#EC6F91"]
def brl(v): return (f"R$ {v:,.0f}").replace(",",".")
def brl2(v): return brl(v)
def pct(v): return f"{v*100:.2f}%".replace(".",",")
def pp(v): return f"{v:+.2f}".replace(".",",")+" p.p."
@st.cache_data(ttl=300,show_spinner="Carregando Metalforte 360...")
def get_data(): return load_data()
@st.cache_data(ttl=300,show_spinner=False)
def get_load_status():
    try: return download_status()
    except Exception: return {}
def _is_fraction_percent(name):
    name=str(name).lower()
    return ("_pct" in name or "margem %" in name or name.endswith(" %") or any(term in name for term in ("variação %","variacao %","share","participação","participacao","cobertura","atingimento"))) and "desvio_%" not in name

def _is_money_column(name):
    name=str(name).lower()
    return any(term in name for term in ("faturamento","receita","margem","valor","preço","preco","custo","ticket","benchmark","gap","projeção","projecao","realizado","impacto")) and not _is_fraction_percent(name) and "p.p." not in name

def _numeric_column_config(data):
    """Moeda em R$, margens em % e os demais números sem casas decimais."""
    config={}
    for col in data.columns:
        if not pd.api.types.is_numeric_dtype(data[col]): continue
        name=str(col).lower()
        if "p.p." in name or "delta_margem_pp" in name: fmt="%.2f p.p."
        elif "desvio_%" in name: fmt="%.2f%%"
        elif _is_fraction_percent(name): fmt="%.2f%%"
        elif _is_money_column(name): fmt="R$ %.0f"
        else: fmt="%.0f"
        config[col]=st.column_config.NumberColumn(format=fmt)
    return config
def show_table(data,**kwargs):
    display=data.copy()
    for col in display.columns:
        if pd.api.types.is_numeric_dtype(display[col]) and _is_fraction_percent(col):
            display[col]=display[col]*100
        elif pd.api.types.is_numeric_dtype(display[col]) and _is_money_column(col):
            display[col]=display[col].map(lambda value: brl(value) if pd.notna(value) else "—")
    inferred=_numeric_column_config(display)
    inferred.update(kwargs.pop("column_config",{}) or {})
    return st.dataframe(display,column_config=inferred,**kwargs)
def show_chart(fig,**kwargs):
    fig.update_layout(font=dict(size=14,color="#27364A"),title_font=dict(size=18,color="#172033"),legend_font=dict(size=13,color="#27364A"),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#FFFFFF",margin=dict(l=28,r=28,t=60,b=42),hoverlabel=dict(font_size=14))
    fig.update_xaxes(tickfont=dict(size=12,color="#42546B"),title_font=dict(size=14,color="#27364A"),gridcolor="#E2E8F0",zerolinecolor="#CBD5E1")
    fig.update_yaxes(tickfont=dict(size=12,color="#42546B"),title_font=dict(size=14,color="#27364A"),gridcolor="#E2E8F0",zerolinecolor="#CBD5E1")
    for axis_name in ("xaxis","yaxis"):
        axis=getattr(fig.layout,axis_name,None); title=((axis.title.text if axis and axis.title else "") or "").lower()
        if "desvio_%" in title: axis.update(tickformat=",.1f",ticksuffix="%")
        elif any(term in title for term in ("margem %","margem_pct","participação","participacao","share")): axis.update(tickformat=".2%")
        elif any(term in title for term in ("faturamento","receita","margem","valor","preço","preco","custo","ticket","benchmark","gap")): axis.update(tickprefix="R$ ",tickformat=",.0f")
        elif title and not any(term in title for term in ("data","mês","mes","cliente","produto","vendedor","uf","município","municipio")): axis.update(tickformat=",.0f")
    return st.plotly_chart(fig,width="stretch",**kwargs)

def yoy_comparison(current,previous,dimension):
    """Compara dois períodos equivalentes no grão comercial selecionado."""
    columns=[dimension,'Faturamento atual','Faturamento anterior','Δ Faturamento','Variação %','Margem atual','Margem anterior','Margem % atual','Margem % anterior','Δ Margem p.p.','Clientes atuais','Clientes anteriores','Produtos atuais','Produtos anteriores','Situação']
    if current.empty and previous.empty: return pd.DataFrame(columns=columns)
    def aggregate(data,suffix):
        if data.empty: return pd.DataFrame(columns=[dimension,f'Faturamento {suffix}',f'Margem {suffix}',f'Clientes {suffix}',f'Produtos {suffix}'])
        return data.groupby(dimension,dropna=False).agg(**{
            f'Faturamento {suffix}':('Faturamento','sum'),
            f'Margem {suffix}':('Margem','sum'),
            f'Clientes {suffix}':('Cliente','nunique'),
            f'Produtos {suffix}':('Produto','nunique'),
        }).reset_index()
    result=aggregate(current,'atual').merge(aggregate(previous,'anterior'),on=dimension,how='outer').rename(columns={
        'Clientes atual':'Clientes atuais','Clientes anterior':'Clientes anteriores',
        'Produtos atual':'Produtos atuais','Produtos anterior':'Produtos anteriores',
    })
    numeric=[col for col in result.columns if col!=dimension]
    result[numeric]=result[numeric].fillna(0)
    result['Δ Faturamento']=result['Faturamento atual']-result['Faturamento anterior']
    result['Variação %']=result['Δ Faturamento']/result['Faturamento anterior'].replace(0,pd.NA)
    result['Margem % atual']=result['Margem atual']/result['Faturamento atual'].replace(0,pd.NA)
    result['Margem % anterior']=result['Margem anterior']/result['Faturamento anterior'].replace(0,pd.NA)
    result['Δ Margem p.p.']=(result['Margem % atual']-result['Margem % anterior'])*100
    result['Situação']='Estável'
    result.loc[(result['Faturamento anterior']==0)&(result['Faturamento atual']>0),'Situação']='Novo'
    result.loc[(result['Faturamento atual']==0)&(result['Faturamento anterior']>0),'Situação']='Perdido'
    result.loc[(result['Faturamento anterior']>0)&(result['Variação %']>=.02),'Situação']='Crescimento'
    result.loc[(result['Faturamento anterior']>0)&(result['Variação %']<=-.02),'Situação']='Retração'
    return result[columns].sort_values('Δ Faturamento',ascending=False)

df=get_data(); load_status=get_load_status(); base_min=df["Data"].min().date(); base_max=df["Data"].max().date(); last_update=base_max.strftime("%d/%m/%Y")
load_timestamp=pd.to_datetime(load_status.get('atualizado_em'),errors='coerce')
if pd.notna(load_timestamp):
    if load_timestamp.tzinfo is None: load_timestamp=load_timestamp.tz_localize('UTC')
    load_timestamp=load_timestamp.tz_convert('America/Sao_Paulo')
    last_load=load_timestamp.strftime('%d/%m/%Y às %H:%M')
else: last_load=f'{last_update} (horário indisponível)'
today=pd.Timestamp.today().date(); month_start=today.replace(day=1)
default_start=month_start if base_min<=month_start<=base_max else base_max.replace(day=1)
logo_path=Path(__file__).parent/'LOGO_METALFORTE.jpg'
head_logo,head_title=st.columns([.16,.84],vertical_alignment="center")
with head_logo:
    if logo_path.exists(): st.image(str(logo_path),width=190)
with head_title:
    st.title("METALFORTE 360")
    st.caption(f"Command Center Comercial • carteira • preço • planejamento • IA  |  Última carga: {last_load}")
st.markdown("""<style>
html,body,[class*="css"]{font-size:16px;color:#172033}
.stApp{background:linear-gradient(180deg,#FFFFFF 0,#F7F9FC 280px)}
.block-container{padding-top:1.6rem;padding-bottom:3rem;max-width:1800px}
h1{font-size:2.25rem!important;letter-spacing:-.02em} h2{font-size:1.65rem!important} h3{font-size:1.28rem!important}
[data-testid="stCaptionContainer"]{font-size:.92rem;color:#52647A!important;opacity:1!important}
[data-testid="stSidebar"]{background:#FFFFFF;border-right:1px solid #DCE3EC}
[data-testid="stSidebar"] label,[data-testid="stSidebar"] p{font-size:.95rem!important;color:#27364A!important}
.st-key-period_filter{min-height:178px}.st-key-period_filter [data-testid="stDateInput"]{min-height:72px}
.st-key-period_filter [data-testid="stForm"]{border:0;padding:0}
[data-testid="stMetric"]{background:#FFFFFF;border:1px solid #DCE3EC;border-radius:12px;padding:1rem 1.05rem;min-height:116px;box-shadow:0 3px 14px rgba(23,32,51,.05)}
[data-testid="stMetricLabel"] p{font-size:.9rem!important;font-weight:650;color:#52647A!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important}
[data-testid="stMetricValue"]{font-size:clamp(1.25rem,1.55vw,1.9rem)!important;font-weight:750;color:#172033;white-space:normal!important;overflow:visible!important;text-overflow:clip!important}
[data-testid="stMetricDelta"]{font-size:.88rem!important}
[data-baseweb="tab-list"]{gap:.3rem;overflow-x:auto}
[data-baseweb="tab"]{min-height:46px;padding:.7rem .9rem;font-size:.92rem;font-weight:650;color:#52647A;white-space:nowrap}
[aria-selected="true"][data-baseweb="tab"]{color:#C54112;background:#FFF1EA;border-radius:9px 9px 0 0}
.mf-status{display:inline-flex;align-items:center;gap:.5rem;padding:.45rem .8rem;border:1px solid #9AD5B5;border-radius:999px;font-size:.9rem;font-weight:700;background:#EEF9F3;color:#176B43}
.mf-dot{width:.58rem;height:.58rem;border-radius:50%;display:inline-block;background:#35C77B;box-shadow:0 0 0 4px #35C77B25}
.mf-alert{border-left:5px solid #D89A20;padding:.9rem 1rem;margin:.55rem 0;background:#FFF8E6;color:#664B0B;border-radius:0 .55rem .55rem 0;font-size:.98rem;line-height:1.45}
.mf-alert small{font-size:.88rem;color:#755F2B}.mf-critical{border-left-color:#DC4C58;background:#FFF0F1;color:#81252C}.mf-critical small{color:#8C4750}.mf-info{border-left-color:#3289CF;background:#EEF7FF;color:#18577E}.mf-info small{color:#3F6F8C}
.mw-strip{display:flex;gap:.65rem;overflow-x:auto;padding:.25rem 0 .8rem}.mw-quote{min-width:210px;background:#FFFFFF;border:1px solid #DCE3EC;border-radius:9px;padding:.7rem .8rem;box-shadow:0 2px 10px rgba(23,32,51,.04)}.mw-name{font-size:.78rem;color:#607086;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mw-value{font-size:1rem;font-weight:750;color:#172033;margin-top:.2rem}.mw-up{color:#168653}.mw-down{color:#C74426}.mw-flat{color:#637287}
[data-testid="stDataFrame"]{border:1px solid #DCE3EC;border-radius:10px;overflow:hidden}
.mf-funnel-note{padding:.85rem 1rem;background:#FFF4EE;border:1px solid #FFD5C2;border-radius:10px;color:#71371E;margin:.5rem 0 1rem}
button,input,[role="combobox"]{font-size:.95rem!important}
@media(max-width:900px){.block-container{padding-left:1rem;padding-right:1rem}[data-testid="stMetric"]{min-height:104px;padding:.8rem}[data-testid="stMetricValue"]{font-size:1.35rem!important}}
</style>""",unsafe_allow_html=True)

with st.sidebar:
    if logo_path.exists(): st.image(str(logo_path),width=220)
    st.header("Filtros")
    st.markdown(f'<span class="mf-status"><span class="mf-dot"></span> Última carga: {last_load}</span>',unsafe_allow_html=True)
    with st.container(key="period_filter"):
        st.subheader("Período")
        with st.form("period_form",border=False):
            selected_dates=st.date_input("Selecione no calendário",value=(default_start,base_max),min_value=base_min,max_value=base_max,format="DD/MM/YYYY",help="O mês atual já vem selecionado. Escolha o intervalo e clique em Aplicar período.",key="period_range")
            st.form_submit_button("Aplicar período",width="stretch")
    if isinstance(selected_dates,(tuple,list)) and len(selected_dates)==2: start_date,end_date=selected_dates
    elif isinstance(selected_dates,(tuple,list)) and len(selected_dates)==1: start_date=end_date=selected_dates[0]
    else: start_date=end_date=selected_dates
    st.caption(f"Período disponível: {base_min.strftime('%d/%m/%Y')} a {last_update}")
    names={1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
    filial=st.multiselect("Filial",sorted(df["Filial"].unique())); uf=st.multiselect("UF",sorted(df["UF"].unique())); pool=df if not uf else df[df["UF"].isin(uf)]; city=st.multiselect("Município",sorted(pool["Município"].unique())); vend=st.multiselect("Vendedor",sorted(df["Vendedor"].unique())); grupo=st.multiselect("Grupo Produto",sorted(df["Grupo Produto"].unique())); tipo=st.multiselect("Tipo Produto",sorted(df["Tipo Produto"].unique())); esp=st.multiselect("Espessura",sorted(df["Espessura"].dropna().unique())); ct=st.text_input("Buscar cliente"); pt=st.text_input("Buscar produto")
f=apply_filters(df,filial=filial,uf=uf,municipio=city,vendedor=vend,grupo=grupo,tipo=tipo,espessura=esp,cliente_text=ct,produto_text=pt,start_date=start_date,end_date=end_date)
# Forecast, meta anual e alertas YTD precisam do histórico completo. O calendário
# continua controlando todas as análises do período, mas não corta a série usada
# para projetar o fechamento do ano.
monitor_scope=apply_filters(df,filial=filial,uf=uf,municipio=city,vendedor=vend,grupo=grupo,tipo=tipo,espessura=esp,cliente_text=ct,produto_text=pt)

if f.empty:
    st.warning("Nenhum registro encontrado com os filtros atuais. Ajuste os filtros para continuar a análise.")

render_operational_dashboard(
    f, monitor_scope, start_date, end_date, last_load,
    brl, pct, pp, show_chart, show_table,
)
st.stop()
