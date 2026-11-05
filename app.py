import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import html
import json
import inspect
import os
import importlib
import time
from pathlib import Path


def _load_src_module(module_name, attempts=5):
    """Retry transient src.* import races while Streamlit refreshes source files."""
    for attempt in range(attempts):
        try:
            return importlib.import_module(module_name)
        except (KeyError, ModuleNotFoundError) as error:
            missing = getattr(error, "name", None)
            if missing is None and error.args:
                missing = str(error.args[0])
            is_project_import = bool(missing) and (
                missing == "src" or missing.startswith("src.")
            )
            if not is_project_import or attempt + 1 >= attempts:
                raise
            importlib.invalidate_caches()
            time.sleep(0.15 * (attempt + 1))


_data_module = _load_src_module("src.data")
load_data = _data_module.load_data
load_targets = _data_module.load_targets
apply_filters = _data_module.apply_filters
try:
    depara_available = _data_module.depara_available
    prepare_depara_upload = _data_module.prepare_depara_upload
    publish_depara = _data_module.publish_depara
    clear_depara_cache = _data_module.clear_depara_cache
except (ImportError, AttributeError):
    def depara_available(): return False
    def prepare_depara_upload(payload): raise RuntimeError("A versão do aplicativo ainda não oferece importação do DE/PARA.")
    publish_depara = prepare_depara_upload
    def clear_depara_cache(): pass
normalize_seller = _load_src_module("src.dimensions").normalize_seller
try:
    # Evita indisponibilidade durante a troca de versão no Streamlit Cloud,
    # quando app.py pode reiniciar antes de src/data.py ser recarregado.
    load_stock = _load_src_module("src.data").load_stock
    load_pedidos_realizado = _load_src_module("src.data").load_pedidos_realizado
except ImportError:
    def load_stock():
        return pd.DataFrame()
    def load_pedidos_realizado():
        return pd.DataFrame()
_analytics = _load_src_module("src.analytics")
metrics = _analytics.metrics
group_metrics = _analytics.group_metrics
client_classification = _analytics.client_classification
quick_insights = _analytics.quick_insights
forecast_year = _analytics.forecast_year
price_analysis = _analytics.price_analysis
build_opportunities = _analytics.build_opportunities
monitoring_snapshot = _analytics.monitoring_snapshot
compare_periods = _analytics.compare_periods
commercial_command_center = _analytics.commercial_command_center
market_watch = _analytics.market_watch
answer = _load_src_module("src.assistant").answer
_cloud_storage = _load_src_module("src.cloud_storage")
download_status = _cloud_storage.download_status
upload_bytes = _cloud_storage.upload_bytes
is_configured = _cloud_storage.is_configured
object_version = _cloud_storage.object_version
dataset_path = _load_src_module("src.data_catalog").object_path
render_operational_dashboard = _load_src_module("src.operational_dashboard").render
_auth = _load_src_module("src.auth")
require_login = _auth.require_login
logout = _auth.logout
ROLE_LABELS = _auth.ROLE_LABELS
APP_RELEASE = _load_src_module("src.version").APP_RELEASE

st.set_page_config(page_title="Metalforte 360",layout="wide",page_icon=str(Path(__file__).parent / "LOGO_METALFORTE.jpg"))
px.defaults.template="plotly_white"
px.defaults.color_discrete_sequence=["#F36A2D","#2F8FD8","#34B27B","#F2B84B","#A78BFA","#EC6F91"]
def _ptbr_number(v, decimals=2):
    return f"{v:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
def brl(v): return f"R$ {_ptbr_number(v, 0)}"
def brl2(v): return f"R$ {_ptbr_number(v, 2)}"
def integer(v): return _ptbr_number(v, 0)
def pct(v): return f"{v*100:.2f}%".replace(".",",")
def pp(v): return f"{v:+.2f}".replace(".",",")+" p.p."
@st.cache_data(ttl=7200,show_spinner="Carregando Metalforte 360...")
def get_data(load_version): return load_data()
@st.cache_data(ttl=7200,show_spinner=False)
def get_targets(load_version): return load_targets()
@st.cache_data(ttl=7200,show_spinner=False)
def get_stock(load_version): return load_stock()
@st.cache_data(ttl=7200,show_spinner=False)
def get_pedidos_realizado(load_version): return load_pedidos_realizado()
@st.cache_data(ttl=60,show_spinner=False)
def get_load_status():
    try: return download_status()
    except Exception: return {}
@st.cache_data(ttl=60,show_spinner=False)
def get_reference_version():
    try:
        return _data_module.depara_reference_version()
    except Exception:
        return "unavailable"

def _is_fraction_percent(name):
    name=str(name).lower()
    return ("_pct" in name or "margem %" in name or name.endswith(" %") or any(term in name for term in ("variação %","variacao %","share","participação","participacao","cobertura","atingimento"))) and "desvio_%" not in name

def _is_weight_column(name):
    name=str(name).lower()
    is_weight="peso" in name or "kg" in name
    is_unit_price=any(term in name for term in ("preço","preco","custo","valor","ticket","r$"))
    return is_weight and not is_unit_price

def _is_average_price_column(name):
    name=str(name).lower()
    return any(term in name for term in ("preço","preco","pr. médio","pr médio","pr.médio"))

def _is_money_column(name):
    name=str(name).lower()
    return any(term in name for term in ("faturamento","receita","margem","valor","preço","preco","pr. médio","pr médio","pr.médio","custo","ticket","benchmark","gap","projeção","projecao","realizado","impacto","potencial","r$")) and not _is_fraction_percent(name) and not _is_weight_column(name) and "p.p." not in name

def _numeric_column_config(data):
    """Configuração de reserva para números que continuam numéricos na tabela."""
    config={}
    for col in data.columns:
        if not pd.api.types.is_numeric_dtype(data[col]): continue
        name=str(col).lower()
        if "p.p." in name or "delta_margem_pp" in name: fmt="%.2f p.p."
        elif "desvio_%" in name: fmt="%.2f%%"
        elif _is_fraction_percent(name): fmt="%.2f%%"
        elif _is_average_price_column(name): fmt="R$ %.2f"
        elif _is_money_column(name): fmt="R$ %.0f"
        else: fmt="%.0f"
        config[col]=st.column_config.NumberColumn(format=fmt)
    return config
DISPLAY_CUSTOMER_GROUPS={}
DISPLAY_SELLER_NAMES={}
def show_table(data,*,raw_detail=False,**kwargs):
    display=data.copy()
    if not raw_detail and "Razão Social" in display.columns:
        display=display.drop(columns=["Razão Social"])
    if "Cliente Painel" in display.columns:
        if "Razão Social" in display.columns:
            display["Cliente Painel"]=display["Cliente Painel"].fillna(display["Razão Social"])
        elif "Cliente" in display.columns:
            display["Cliente Painel"]=display["Cliente Painel"].fillna(display["Cliente"])
        if "Cliente" in display.columns:
            display=display.drop(columns=["Cliente"])
        display=display.rename(columns={"Cliente Painel":"Grupo de clientes"})
    elif "Cliente" in display.columns and not raw_detail:
        original=display["Cliente"].astype(str)
        mapped=original.map(DISPLAY_CUSTOMER_GROUPS)
        known_groups=set(DISPLAY_CUSTOMER_GROUPS.values())
        display["Cliente"]=mapped.where(mapped.notna(),original.where(original.isin(known_groups),original))
        display=display.rename(columns={"Cliente":"Grupo de clientes"})
    if "Vendedor Painel" in display.columns:
        display["Vendedor Painel"]=display["Vendedor Painel"].fillna("Não mapeado")
        if "Vendedor" in display.columns:
            display=display.drop(columns=["Vendedor"])
    elif "Vendedor" in display.columns:
        original=display["Vendedor"].astype(str)
        mapped=original.map(DISPLAY_SELLER_NAMES)
        known_sellers=set(DISPLAY_SELLER_NAMES.values())
        display["Vendedor"]=mapped.where(mapped.notna(),original.where(original.isin(known_sellers),"Não mapeado"))
        display=display.rename(columns={"Vendedor":"Vendedor Painel"})
    for col in display.columns:
        if not pd.api.types.is_numeric_dtype(display[col]): continue
        name=str(col).lower()
        if "p.p." in name or "delta_margem_pp" in name:
            display[col]=display[col].map(lambda value: f"{value:.2f} p.p.".replace(".", ",") if pd.notna(value) else "—")
        elif "desvio_%" in name:
            display[col]=display[col].map(lambda value: f"{value:.2f}%".replace(".", ",") if pd.notna(value) else "—")
        elif _is_fraction_percent(col):
            display[col]=display[col].map(lambda value: pct(value) if pd.notna(value) else "—")
        elif _is_average_price_column(name):
            display[col]=display[col].map(lambda value: brl2(value) if pd.notna(value) else "—")
        elif _is_money_column(col):
            display[col]=display[col].map(lambda value: brl(value) if pd.notna(value) else "—")
        elif _is_weight_column(col):
            display[col]=display[col].map(lambda value: integer(value) if pd.notna(value) else "—")
    # Destaque variações e atingimento sem colorir métricas absolutas.
    signal_values={}
    for col in display.columns:
        if col not in data.columns or not pd.api.types.is_numeric_dtype(data[col]):
            continue
        name=str(col).casefold()
        attainment=any(term in name for term in ("atingimento","% meta","meta atingida"))
        variation=any(term in name for term in ("variação","variacao","Δ ","delta ","diferença %","diferenca %"))
        if not (attainment or variation):
            continue
        raw=pd.to_numeric(data[col],errors="coerce")
        if not raw.notna().any():
            continue
        lower_is_better=any(term in name for term in ("inativo","pendente","queda","perdido","atraso","ruptura","risco","excesso"))
        if attainment:
            positive=raw.ge(1); negative=raw.lt(1)
            marker=raw.map(lambda value: "● " if pd.notna(value) else "")
        else:
            positive=raw.lt(0) if lower_is_better else raw.gt(0)
            negative=raw.gt(0) if lower_is_better else raw.lt(0)
            marker=raw.map(lambda value: ("↑ " if (value < 0 if lower_is_better else value > 0) else "↓ ") if pd.notna(value) and value != 0 else ("• " if pd.notna(value) else ""))
        display[col]=marker.astype(str)+display[col].astype(str)
        signal_values[col]=(positive,negative,attainment,raw)

    inferred=_numeric_column_config(display)
    inferred.update(kwargs.pop("column_config",{}) or {})
    if signal_values:
        def signal_style(_):
            styles=pd.DataFrame("",index=display.index,columns=display.columns)
            for column,(positive,negative,attainment,raw) in signal_values.items():
                styles.loc[positive.index[positive],column]="background-color:#EAF7EF;color:#176B43;font-weight:700"
                styles.loc[negative.index[negative],column]="background-color:#FFF0EF;color:#B33A2B;font-weight:700"
                if attainment:
                    middle=~positive & ~negative & raw.notna()
                    styles.loc[middle.index[middle],column]="background-color:#FFF7E5;color:#8A5A00;font-weight:700"
            return styles
        display=display.style.apply(signal_style,axis=None)
    return st.dataframe(display,column_config=inferred,**kwargs)
_HOVER_LABEL_COLOR="#64748B"
_HOVER_COUNT_TERMS=("clientes","pedidos","produtos","documentos","registros","quantidade","notas","positivados","entidades","municípios","municipios","nfs","amostra")
_HOVER_GENERIC_VALUES=("value","valor","valor (r$)","peso (kg)")
_CHART_RENDER_INDEX=0

def _plotly_points(event):
    """Retorna os pontos selecionados pelo usuário em um gráfico Plotly."""
    try:
        selection=event.get("selection",{})
        return list(selection.get("points",[]) or [])
    except Exception:
        return []

def _chart_filter_candidates(data,point):
    """Relaciona o rótulo clicado a uma dimensão existente na base comercial."""
    dimensions=("Cliente Painel","Grupo Econômico Cliente","Produto","Vendedor Painel","Grupo Vendedor","Canal","Segmento Cliente","Grupo Produto",
                "Subgrupo Produto","Tipo Produto","Tipologia Cliente","Filial","UF","Município",
                "Cluster PIVOT","ESPEC.","Sub Espec.","Espessura")
    candidates=[]
    values=[point.get(axis) for axis in ("x","y")]
    custom=point.get("customdata")
    if isinstance(custom,(list,tuple)):
        values.extend(custom)
    values.extend(point.get(name) for name in ("text","hovertext","label"))
    for value in values:
        if value is None or isinstance(value,(int,float)) and not isinstance(value,bool):
            continue
        text=str(value).strip()
        if not text:
            continue
        for column in dimensions:
            if column not in data.columns:
                continue
            try:
                matches=data[column].notna() & data[column].astype(str).str.strip().eq(text)
            except Exception:
                continue
            if matches.any():
                candidate=(column,text)
                if candidate not in candidates:
                    candidates.append(candidate)
        if "Data" in data.columns:
            try:
                month_text=None
                if len(text)==7 and text[4] in "-/" and text[:4].isdigit() and text[5:7].isdigit():
                    month_text=f"{text[:4]}-{text[5:7]}"
                elif len(text)==7 and text[2] in "/-" and text[:2].isdigit() and text[3:].isdigit():
                    month_text=f"{text[3:]}-{text[:2]}"
                dates=pd.to_datetime(data["Data"],errors="coerce")
                if month_text:
                    period=pd.Period(month_text,freq="M")
                    if dates.dt.to_period("M").eq(period).any():
                        candidate=("Data",month_text)
                        if candidate not in candidates:
                            candidates.append(candidate)
                    continue
                parsed=pd.to_datetime(value,errors="coerce")
                if pd.notna(parsed):
                    if (dates.dt.normalize()==parsed.normalize()).any():
                        candidate=("Data",parsed.strftime("%Y-%m-%d"))
                        if candidate not in candidates:
                            candidates.append(candidate)
            except Exception:
                pass
    return candidates

def _filter_chart_dimension(data,dimension,value):
    """Aplica o valor selecionado às tabelas e visuais seguintes do painel."""
    if data is None or data.empty:
        return data
    if dimension=="Data" and "Data" in data.columns:
        dates=pd.to_datetime(data["Data"],errors="coerce")
        if len(str(value))==7:
            try:
                period=pd.Period(value,freq="M")
                return data.loc[dates.dt.to_period("M")==period].copy()
            except Exception:
                pass
        parsed=pd.to_datetime(value,errors="coerce")
        return data.loc[dates.dt.normalize()==parsed.normalize()].copy() if pd.notna(parsed) else data
    if dimension not in data.columns:
        return data
    return data.loc[data[dimension].notna() & data[dimension].astype(str).str.strip().eq(str(value))].copy()

def _hover_raw(trace,base):
    """Dados do traço referenciados no popup, para descobrir se o campo é texto, data ou número."""
    try:
        if base in ("x","y","z"): values=getattr(trace,base,None)
        elif base=="marker.size": values=trace.marker.size
        elif base.startswith("customdata["):
            index=int(base[len("customdata["):-1]); data=trace.customdata
            values=None if data is None else [row[index] for row in data]
        else: return None
        if values is None or isinstance(values,(str,int,float)): return None
        return pd.Series(list(values)).infer_objects()
    except Exception:
        return None

def _hover_value(label,base,raw):
    """Formata o valor do popup pelo nome da medida, no padrão brasileiro."""
    name=str(label).lower()
    if raw is not None and pd.api.types.is_datetime64_any_dtype(raw):
        return f"%{{{base}|{'%m/%Y' if name in ('mês','mes','mês referência') else '%d/%m/%Y'}}}"
    if raw is not None and not pd.api.types.is_numeric_dtype(raw): return f"%{{{base}}}"
    if "p.p." in name: return f"%{{{base}:,.2f}} p.p."
    if _is_fraction_percent(name): return f"%{{{base}:.2%}}"
    if name.endswith(" t") or name.endswith("(t)"): return f"%{{{base}:,.0f}} t"
    if _is_weight_column(name): return f"%{{{base}:,.0f}} kg"
    if _is_average_price_column(name): return f"R$ %{{{base}:,.2f}}"
    if _is_money_column(name): return f"R$ %{{{base}:,.0f}}"
    if "dias" in name: return f"%{{{base}:,.0f}} dias"
    if any(term in name for term in _HOVER_COUNT_TERMS): return f"%{{{base}:,.0f}}"
    return f"%{{{base}:,.0f}}"

def _rich_hover(fig):
    """Troca o popup padrão do Plotly ("Campo=valor") por título em destaque e valores formatados.

    Só reescreve popups gerados automaticamente; os que o painel já define à mão ficam intactos.
    """
    for trace in fig.data:
        template=getattr(trace,"hovertemplate",None)
        if not isinstance(template,str) or "=%{" not in template: continue
        parts=[part for part in template.replace("<extra></extra>","").split("<br>") if part]
        static={}
        for part in parts:
            if "=" in part and "%{" not in part:
                label,value=part.split("=",1); static[label]=value
        title=None; lines=[]
        for part in parts:
            if "=" not in part:
                if "%{hovertext}" in part: title=part
                else: lines.append(part)
                continue
            label,expression=part.split("=",1)
            if "%{" not in expression:
                if len(static)==1 and any(p.split("=",1)[0].lower() in _HOVER_GENERIC_VALUES for p in parts if "=%{" in p):
                    continue  # vira o rótulo do valor logo abaixo (gráficos em formato largo)
                lines.append(f"<span style='color:{_HOVER_LABEL_COLOR}'>{label}:</span> <b>{expression}</b>"); continue
            inner=expression[expression.index("%{")+2:expression.index("}")]
            base=inner.split(":")[0].split("|")[0]
            raw=_hover_raw(trace,base)
            shown=label
            if label.lower() in _HOVER_GENERIC_VALUES and len(static)==1: shown=next(iter(static.values()))
            value=_hover_value(label if label.lower() not in ("value","valor") else shown,base,raw)
            is_dimension=raw is not None and not pd.api.types.is_numeric_dtype(raw)
            if title is None and is_dimension:
                title=f"<b style='font-size:14px'>{value}</b>"; continue
            lines.append(f"<span style='color:{_HOVER_LABEL_COLOR}'>{shown}:</span> <b>{value}</b>")
        body=([title,""] if title else [])+lines
        trace.hovertemplate="<br>".join(body)+"<extra></extra>"
    return fig

def show_chart(fig,**kwargs):
    global _CHART_RENDER_INDEX
    _rich_hover(fig)
    # Mantém a seta padrão ao passar sobre o gráfico e habilita seleção por clique.
    fig.update_layout(dragmode=False,clickmode="event+select",separators=",.",font=dict(size=14,color="#27364A"),title_font=dict(size=18,color="#172033"),legend_font=dict(size=13,color="#27364A"),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#FFFFFF",margin=dict(l=28,r=28,t=60,b=42),hoverlabel=dict(bgcolor="#FFFFFF",bordercolor="#CBD5E1",align="left",namelength=-1,font=dict(family="Source Sans Pro, Arial, sans-serif",size=13,color="#172033")))
    fig.update_xaxes(tickfont=dict(size=12,color="#42546B"),title_font=dict(size=14,color="#27364A"),gridcolor="#E2E8F0",zerolinecolor="#CBD5E1")
    fig.update_yaxes(tickfont=dict(size=12,color="#42546B"),title_font=dict(size=14,color="#27364A"),gridcolor="#E2E8F0",zerolinecolor="#CBD5E1")
    for axis_name in ("xaxis","yaxis"):
        axis=getattr(fig.layout,axis_name,None); title=((axis.title.text if axis and axis.title else "") or "").lower()
        if "desvio_%" in title: axis.update(tickformat=",.2f",ticksuffix="%")
        elif any(term in title for term in ("margem %","margem_pct","participação","participacao","share")): axis.update(tickformat=".2%")
        elif _is_average_price_column(title): axis.update(tickprefix="R$ ",tickformat=",.2f")
        elif any(term in title for term in ("faturamento","receita","margem","valor","custo","ticket","benchmark","gap")): axis.update(tickprefix="R$ ",tickformat=",.0f")
        elif title and not any(term in title for term in ("data","mês","mes","cliente","produto","vendedor","uf","município","municipio")): axis.update(tickformat=",.0f")
    chart_title=getattr(getattr(fig.layout,"title",None),"text",None) or "gráfico"
    chart_key=kwargs.setdefault("key",f"mf_chart_{_CHART_RENDER_INDEX}_{abs(hash(str(chart_title)))%100000000}")
    _CHART_RENDER_INDEX+=1
    kwargs.setdefault("on_select","rerun")
    kwargs.setdefault("selection_mode","points")
    config=kwargs.pop("config",{}) or {}
    config={**config,"responsive":True,"displaylogo":False,"scrollZoom":False}
    event=st.plotly_chart(fig,width="stretch",config=config,**kwargs)
    points=_plotly_points(event)
    point=points[0] if points else None
    signature=json.dumps(point,ensure_ascii=False,sort_keys=True,default=str) if point else ""
    signature_key=f"_chart_selection_signature_{chart_key}"
    previous=st.session_state.get(signature_key,"")
    if signature!=previous:
        st.session_state[signature_key]=signature
        st.session_state["_chart_crossfilter_point"]=point
        st.rerun()
    return event

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

access=require_login()
load_status=get_load_status()
reference_version=get_reference_version()
getattr(_data_module,"set_depara_version",lambda version: None)(reference_version)
load_version=str(load_status.get("atualizado_em") or "sem-versao-publicada")+"|depara:"+reference_version
df=get_data(load_version)
@st.cache_data(ttl=7200,show_spinner=False)
def get_display_names(version, _source):
    source=_source
    customers=source[["Cliente","Cliente Painel"]].drop_duplicates("Cliente") if {"Cliente","Cliente Painel"}.issubset(source.columns) else pd.DataFrame()
    sellers=source[["Vendedor","Vendedor Painel"]].drop_duplicates("Vendedor") if {"Vendedor","Vendedor Painel"}.issubset(source.columns) else pd.DataFrame()
    return (dict(zip(customers["Cliente"],customers["Cliente Painel"])) if not customers.empty else {},
            dict(zip(sellers["Vendedor"],sellers["Vendedor Painel"])) if not sellers.empty else {})
DISPLAY_CUSTOMER_GROUPS,DISPLAY_SELLER_NAMES=get_display_names(load_version, df)
if access["role"] == "seller":
    seller_scope = normalize_seller(access.get("seller_scope", ""))
    if not seller_scope:
        st.error("Seu perfil de vendedor ainda não possui uma carteira associada. Procure um administrador.")
        st.stop()
    df = df[df["Vendedor"].astype(str) == seller_scope].copy()
    if df.empty:
        st.error("A carteira associada ao usuário não foi encontrada na base atual. Procure um administrador.")
        st.stop()
base_min=df["Data"].min().date(); base_max=df["Data"].max().date(); last_update=base_max.strftime("%d/%m/%Y")
load_timestamp=pd.to_datetime(load_status.get('atualizado_em'),errors='coerce')
if pd.notna(load_timestamp):
    if load_timestamp.tzinfo is None: load_timestamp=load_timestamp.tz_localize('UTC')
    load_timestamp=load_timestamp.tz_convert('America/Sao_Paulo')
    last_load=load_timestamp.strftime('%d/%m/%Y às %H:%M')
else: last_load=f'{last_update} (horário indisponível)'
today=pd.Timestamp.today().date(); month_start=today.replace(day=1)
default_start=month_start if base_min<=month_start<=base_max else base_max.replace(day=1)
logo_path=Path(__file__).parent/'LOGO_METALFORTE.jpg'
with st.container(key="mf_app_header"):
    head_logo,head_title=st.columns([.095,.905],vertical_alignment="center",gap="medium")
    with head_logo:
        if logo_path.exists(): st.image(str(logo_path),width=112)
    with head_title:
        st.title("METALFORTE 360")
        st.caption(f"Command Center e operação comercial em um único app  ·  Versão {APP_RELEASE}  ·  Última carga: {last_load}")
st.markdown("""<style>
html,body,[class*="css"]{font-size:16px;color:#172033}
.stApp{background:linear-gradient(180deg,#FFFFFF 0,#F7F9FC 280px)}
.block-container{padding-top:1.6rem;padding-bottom:3rem;max-width:1800px}
.st-key-mf_app_header [data-testid="stHorizontalBlock"]{align-items:center!important;gap:1rem!important}
.st-key-mf_app_header [data-testid="stImage"] img{width:clamp(72px,8vw,112px)!important;height:auto!important;border-radius:10px}
.st-key-mf_app_header h1{margin:0!important;line-height:1.05!important}
.st-key-mf_app_header [data-testid="stCaptionContainer"]{margin-top:.3rem}
h1{font-size:2.25rem!important;letter-spacing:-.02em} h2{font-size:1.65rem!important} h3{font-size:1.28rem!important}
[data-testid="stCaptionContainer"]{font-size:.92rem;color:#52647A!important;opacity:1!important}
[data-testid="stSidebar"]{background:#FFFFFF;border-right:1px solid #DCE3EC}
[data-testid="stSidebar"] label,[data-testid="stSidebar"] p{font-size:.95rem!important;color:#27364A!important}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"]{margin-bottom:.2rem!important}
[data-testid="stSidebar"] [data-testid="stMultiSelect"] [data-baseweb="select"]{min-height:42px!important;align-items:flex-start!important}
[data-testid="stSidebar"] [data-testid="stMultiSelect"] [data-baseweb="tag"]{max-width:100%;overflow:hidden}
[data-testid="stSidebar"] [data-testid="stMultiSelect"] [data-baseweb="tag"] span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
[data-testid="stSidebar"] [data-testid="stSelectbox"],[data-testid="stSidebar"] [data-testid="stMultiSelect"],[data-testid="stSidebar"] [data-testid="stDateInput"]{width:100%;min-width:0}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{white-space:normal!important;line-height:1.25!important}
[data-testid="stSidebar"] [data-testid="stTextInput"] :is([data-testid="stTextInputRootElement"],[data-baseweb="input"]){background:#F7F9FC!important;border:1px solid #CBD5E1!important;border-radius:8px!important;transition:border-color .15s,box-shadow .15s}
[data-testid="stSidebar"] [data-testid="stTextInput"] :is([data-testid="stTextInputRootElement"],[data-baseweb="input"]):hover{border-color:#94A3B8!important}
[data-testid="stSidebar"] [data-testid="stTextInput"] :is([data-testid="stTextInputRootElement"],[data-baseweb="input"]):focus-within{border-color:#F36A2D!important;box-shadow:0 0 0 3px rgba(243,106,45,.15)!important;background:#FFFFFF!important}
[data-testid="stSidebar"] [data-testid="stTextInput"] [data-baseweb="base-input"],[data-testid="stSidebar"] [data-testid="stTextInput"] input{background:transparent!important;color:#172033!important}
[data-testid="stSidebar"] [data-testid="stTextInput"] input::placeholder{color:#8391A5!important;opacity:1!important}
.st-key-period_filter{min-height:178px}.st-key-period_filter [data-testid="stDateInput"]{min-height:72px}
.st-key-period_filter [data-testid="stForm"]{border:0;padding:0}
[data-testid="stMetric"]{background:#FFFFFF;border:1px solid #DCE3EC;border-radius:12px;padding:1rem 1.05rem;min-height:116px;box-shadow:0 3px 14px rgba(23,32,51,.05)}
[data-testid="stMetricLabel"] p{font-size:.9rem!important;font-weight:650;color:#52647A!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important}
[data-testid="stMetricValue"]{font-size:clamp(1.25rem,1.55vw,1.9rem)!important;font-weight:750;color:#172033;white-space:normal!important;overflow:visible!important;text-overflow:clip!important}
[data-testid="stMetricDelta"]{font-size:.88rem!important}
[data-baseweb="tab-list"]{gap:.3rem;overflow-x:auto;scrollbar-width:thin;scroll-behavior:smooth}
[data-baseweb="tab"]{min-height:46px;padding:.7rem .9rem;font-size:.92rem;font-weight:650;color:#52647A;white-space:nowrap}
[aria-selected="true"][data-baseweb="tab"]{color:#C54112;background:#FFF1EA;border-radius:9px 9px 0 0}
.mf-status{display:inline-flex;align-items:center;gap:.5rem;padding:.45rem .8rem;border:1px solid #9AD5B5;border-radius:999px;font-size:.9rem;font-weight:700;background:#EEF9F3;color:#176B43}
.mf-dot{width:.58rem;height:.58rem;border-radius:50%;display:inline-block;background:#35C77B;box-shadow:0 0 0 4px #35C77B25}
.mf-alert{border-left:5px solid #D89A20;padding:.9rem 1rem;margin:.55rem 0;background:#FFF8E6;color:#664B0B;border-radius:0 .55rem .55rem 0;font-size:.98rem;line-height:1.45}
.mf-alert small{font-size:.88rem;color:#755F2B}.mf-critical{border-left-color:#DC4C58;background:#FFF0F1;color:#81252C}.mf-critical small{color:#8C4750}.mf-info{border-left-color:#3289CF;background:#EEF7FF;color:#18577E}.mf-info small{color:#3F6F8C}
.mw-strip{display:flex;gap:.65rem;overflow-x:auto;padding:.25rem 0 .8rem}.mw-quote{min-width:210px;background:#FFFFFF;border:1px solid #DCE3EC;border-radius:9px;padding:.7rem .8rem;box-shadow:0 2px 10px rgba(23,32,51,.04)}.mw-name{font-size:.78rem;color:#607086;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mw-value{font-size:1rem;font-weight:750;color:#172033;margin-top:.2rem}.mw-up{color:#168653}.mw-down{color:#C74426}.mw-flat{color:#637287}
[data-testid="stDataFrame"]{border:1px solid #DCE3EC;border-radius:10px;overflow:hidden}
[data-testid="stDataFrame"] [role="grid"]{border-radius:10px}
.mf-funnel-note{padding:.85rem 1rem;background:#FFF4EE;border:1px solid #FFD5C2;border-radius:10px;color:#71371E;margin:.5rem 0 1rem}
button,input,[role="combobox"]{font-size:.95rem!important}
.st-key-mf_page{margin:.35rem 0 1.15rem}
.st-key-mf_page [data-testid="stWidgetLabel"] p{font-size:.86rem!important;font-weight:750!important;letter-spacing:.02em;color:#52647A!important;text-transform:uppercase}
.st-key-mf_page [role="radiogroup"]{display:grid!important;grid-template-columns:repeat(var(--mf-nav-cols,8),minmax(0,1fr));grid-auto-rows:1fr;gap:.42rem;width:100%;padding:.48rem;background:linear-gradient(135deg,#F5F7FA,#EDF2F7);border:1px solid #DCE3EC;border-radius:12px}
.st-key-mf_page [role="radiogroup"]>*{width:100%!important;min-width:0!important;height:100%!important}
.st-key-mf_page [role="radiogroup"] button,.st-key-mf_page [role="radiogroup"] label{justify-content:center!important;min-height:42px!important;height:100%!important;width:100%!important;border-radius:8px!important;transition:background .16s ease,border-color .16s ease,transform .16s ease}
.st-key-mf_page [role="radiogroup"] button:hover,.st-key-mf_page [role="radiogroup"] label:hover{transform:translateY(-1px);border-color:#F36A2D!important}
.st-key-mf_page [role="radiogroup"] p{white-space:normal!important;text-align:center!important;line-height:1.15!important;font-size:.88rem!important;font-weight:650!important}
@media(min-width:700px) and (max-width:1400px){
  .block-container{padding:1.1rem 1.15rem 2.4rem;max-width:100%}
  h1{font-size:1.9rem!important} h2{font-size:1.42rem!important} h3{font-size:1.16rem!important}
  [data-testid="stSidebar"]{min-width:14rem!important;max-width:14rem!important}
  [data-testid="stSidebar"] [data-testid="stImage"] img{max-width:170px!important;height:auto!important}
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.75rem!important}
  [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{flex:1 1 min(100%,260px)!important;width:auto!important;min-width:min(100%,220px)!important}
  [data-testid="stMetric"]{min-height:104px;padding:.78rem}
  [data-testid="stMetricValue"]{font-size:1.3rem!important}
  .mf-kpi{min-height:146px!important}
  [data-testid="stSegmentedControl"] [role="radiogroup"]{display:flex!important;flex-wrap:wrap!important}
  .st-key-mf_page [role="radiogroup"]{display:grid!important;grid-template-columns:repeat(var(--mf-nav-cols-md,4),minmax(0,1fr))!important}
  [data-baseweb="tab-list"]{overflow-x:auto!important;scrollbar-width:thin}
  [data-testid="stDataFrame"]{max-width:100%;overflow-x:auto}
}
@media(max-width:699px){
  .block-container{padding-left:.8rem;padding-right:.8rem}
  .st-key-mf_app_header [data-testid="stHorizontalBlock"]{gap:.65rem!important}
  .st-key-mf_app_header [data-testid="stImage"] img{width:68px!important}
  [data-testid="stMetric"]{min-height:100px;padding:.75rem}
  [data-testid="stMetricValue"]{font-size:1.28rem!important}
  [data-testid="stSegmentedControl"] [role="radiogroup"]{display:flex!important;flex-wrap:wrap!important}
  .st-key-mf_page [role="radiogroup"]{display:grid!important;grid-template-columns:repeat(var(--mf-nav-cols-sm,2),minmax(0,1fr))!important;gap:.3rem!important;padding:.32rem!important}
}
</style>""",unsafe_allow_html=True)

with st.sidebar:
    if logo_path.exists(): st.image(str(logo_path),width=220)
    user=access["user"]
    display_name=(user.get("user_metadata") or {}).get("display_name") or user.get("email", "Usuário")
    st.caption(f"Conectado como **{display_name}**  \n{ROLE_LABELS.get(access['role'], access['role'])}")
    if st.button("Sair", width="stretch"):
        logout(); st.rerun()
    st.divider()
    st.header("Filtros")
    st.markdown(f'<span class="mf-status"><span class="mf-dot"></span> Última carga: {last_load}</span>',unsafe_allow_html=True)
    if st.button("Atualizar visualização", width="stretch"):
        get_reference_version.clear()
        clear_depara_cache()
        get_load_status.clear()
        get_data.clear()
        get_targets.clear()
        get_stock.clear()
        get_pedidos_realizado.clear()
        st.rerun()
    if access["role"] == "admin":
        with st.expander("DE/PARA de clientes e vendedores"):
            if reference_version.startswith("db:") and depara_available():
                st.success("Agrupamentos conectados às tabelas do Supabase.")
            else:
                st.warning("A referência central ainda não está disponível nesta sessão.")
            st.caption("Edite grupo_economico em depara_clientes; vendedor_painel e classificacao em depara_vendedores. Clientes sem grupo usam a razão social. Preserve códigos, loja e nomes de cadastro para manter os vínculos com as vendas.")
            st.link_button("Editar DE/PARA no Supabase", "https://supabase.com/dashboard/project/uaqekqgnwxpbfetqxmnb/editor", width="stretch")
            st.caption("Após salvar, use Atualizar visualização. A versão também é consultada no próximo uso do painel, com cache de até 60 segundos.")
    with st.container(key="period_filter"):
        st.subheader("Período")
        with st.form("period_form",border=False):
            selected_dates=st.date_input("Selecione no calendário",value=(default_start,base_max),min_value=base_min,max_value=base_max,format="DD/MM/YYYY",help="O mês atual já vem selecionado. Escolha o intervalo e clique em Aplicar período.",key="period_range")
            st.form_submit_button("Aplicar período",width="stretch")
    if isinstance(selected_dates,(tuple,list)) and len(selected_dates)==2: start_date,end_date=selected_dates
    elif isinstance(selected_dates,(tuple,list)) and len(selected_dates)==1: start_date=end_date=selected_dates[0]
    else: start_date=end_date=selected_dates
    st.caption(f"Período disponível: {base_min.strftime('%d/%m/%Y')} a {last_update}")
    filial=st.multiselect("Filial",sorted(df["Filial"].unique()))
    uf=st.multiselect("UF",sorted(df["UF"].unique()))
    vend=[]  # Nome cadastrado permanece interno; o filtro visível usa Vendedor Painel.
    seller_options=sorted(df["Vendedor Painel"].dropna().astype(str).unique()) if "Vendedor Painel" in df else sorted(df["Vendedor"].dropna().astype(str).unique())
    client_pool=df
    if filial: client_pool=client_pool[client_pool["Filial"].isin(filial)]
    if uf: client_pool=client_pool[client_pool["UF"].isin(uf)]
    client_label="Cliente Painel" if "Cliente Painel" in client_pool else ("Grupo Econômico Cliente" if "Grupo Econômico Cliente" in client_pool else "Cliente")
    mapping_available=depara_available()
    client_values=sorted(client_pool[client_label].dropna().astype(str).unique().tolist())
    group_values=set()
    if mapping_available and "Grupo Econômico Cliente" in client_pool:
        group_values=set(client_pool.loc[
            client_pool["Grupo Econômico Cliente"].notna()
            & ~client_pool["Grupo Econômico Cliente"].astype(str).str.strip().str.casefold().isin({"", "não mapeado", "nao mapeado"}),
            "Grupo Econômico Cliente",
        ].astype(str))
    option_to_value={"Todos os grupos": None}
    option_labels=[]
    for value in client_values:
        label=f"Grupo · {value}" if value in group_values else f"Cliente sem grupo · {value}"
        option_to_value[label]=value
        option_labels.append(label)
    if mapping_available:
        st.caption(f"DE/PARA ativo · {len(group_values):,} grupo(s) econômico(s) disponíveis.".replace(",", "."))
    else:
        st.warning("DE/PARA de clientes indisponível. A lista abaixo mostra razões sociais individuais; os grupos econômicos só aparecem após carregar o arquivo DE/PARA na seção acima.")
    client_scope=st.selectbox(
        "Grupo de clientes", ["Todos os grupos"] + option_labels, index=0,
        help="Grupos econômicos vêm do DE/PARA privado. Clientes sem grupo aparecem identificados pela razão social. A razão social dos membros do grupo fica disponível no drill-down da aba Clientes.",
    )
    selected_client=option_to_value[client_scope]
    st.subheader("Mais filtros")
    with st.container(key="more_filters"):
        pool=df if not uf else df[df["UF"].isin(uf)]
        cidade_pivot=st.multiselect(
            "Cluster de cidades (PIVOT)", sorted(pool["Cluster PIVOT"].unique()),
            help="Agrupa cada município à cidade PIVOT de maior potencial de sua região.",
        ) if "Cluster PIVOT" in pool else []
        if cidade_pivot:
            pool=pool[pool["Cluster PIVOT"].isin(cidade_pivot)]
        city=st.multiselect("Município",sorted(pool["Município"].unique()))
        canal=st.multiselect(
            "Canal (segmento de clientes)", sorted(df["Canal"].unique())
        ) if "Canal" in df else []
        tipologia=st.multiselect(
            "Tipo de cliente", sorted(df["Tipologia Cliente"].unique()),
            help="Classificação comercial do cliente, como revenda, construtora e demais tipologias.",
        ) if "Tipologia Cliente" in df else []
        grupo_economico=st.multiselect(
            "Grupo econômico do cliente", sorted(df["Grupo Econômico Cliente"].dropna().astype(str).unique()),
            help="Consolida filiais e empresas relacionadas conforme o DE/PARA privado da METALFORTE.",
        ) if "Grupo Econômico Cliente" in df and mapping_available else []
        grupo_vendedor=st.multiselect(
            "Classificação do vendedor", sorted(df["Grupo Vendedor"].dropna().astype(str).unique()),
            help="Agrupa vendedores pela classificação indicada no DE/PARA.",
        ) if "Grupo Vendedor" in df and mapping_available else []
        vendedor_painel=st.multiselect(
            "Vendedor Painel", seller_options,
            help="Filtro de vendedor baseado na coluna Vendedor Painel.",
        ) if seller_options else []
        grupo=st.multiselect("Grupo Produto",sorted(df["Grupo Produto"].unique()))
        subgrupo=st.multiselect("Subgrupo Produto",sorted(df["Subgrupo Produto"].unique())) if "Subgrupo Produto" in df else []
        tipo=st.multiselect("Tipo Produto",sorted(df["Tipo Produto"].unique()))
        espec=st.multiselect("ESPEC.",sorted(df["ESPEC."].unique())) if "ESPEC." in df else []
        sub_espec=st.multiselect("Sub Espec.",sorted(df["Sub Espec."].unique())) if "Sub Espec." in df else []
        esp=st.multiselect("Espessura",sorted(df["Espessura"].dropna().unique()))
        ct=st.text_input("Buscar cliente",placeholder="🔍 Nome do cliente")
        pt=st.text_input("Buscar produto",placeholder="🔍 Nome do produto")
        chart_point=st.session_state.get("_chart_crossfilter_point")
        chart_filter=None
        if chart_point:
            candidates=_chart_filter_candidates(df,chart_point)
            if candidates:
                option_labels=[f"{dimension}: {value}" for dimension,value in candidates]
                point_token=abs(hash(json.dumps(chart_point,ensure_ascii=False,sort_keys=True,default=str)))%100000000
                chosen=st.selectbox(
                    "Filtrar pelo ponto clicado",option_labels,
                    key=f"chart_crossfilter_choice_{point_token}",
                    help="O clique em um gráfico aplica esta dimensão às análises e tabelas do painel.",
                )
                chart_filter=candidates[option_labels.index(chosen)]
                st.caption("Filtro de gráfico aplicado ao painel.")
            else:
                st.caption("O ponto foi selecionado, mas seus valores não correspondem a uma dimensão da base para cruzar os visuais.")
            if st.button("Limpar filtro do gráfico",key="clear_chart_crossfilter",width="stretch"):
                st.session_state["_chart_crossfilter_point"]=None
                st.rerun()
monitor_scope=apply_filters(df,filial=filial,uf=uf,municipio=city,cidade_pivot=cidade_pivot,vendedor=vend,vendedor_painel=vendedor_painel,grupo_vendedor=grupo_vendedor,grupo_economico=grupo_economico,canal=canal,tipologia=tipologia,grupo=grupo,subgrupo=subgrupo,tipo=tipo,espec=espec,sub_espec=sub_espec,espessura=esp,cliente=selected_client,cliente_text=ct,produto_text=pt)
if chart_filter:
    monitor_scope=_filter_chart_dimension(monitor_scope,*chart_filter)
f=apply_filters(monitor_scope,start_date=start_date,end_date=end_date)
def target_history_loader():
    # Metas não têm grão de cliente; o filtro de grupo econômico não reduz o
    # realizado isoladamente para evitar comparar meta integral com cliente parcial.
    result=apply_filters(df,filial=filial,uf=uf,municipio=city,cidade_pivot=cidade_pivot,vendedor=vend,vendedor_painel=vendedor_painel,grupo_vendedor=grupo_vendedor,canal=canal,tipologia=tipologia,grupo=grupo,subgrupo=subgrupo,tipo=tipo,espec=espec,sub_espec=sub_espec,espessura=esp)
    return _filter_chart_dimension(result,*chart_filter) if chart_filter else result

def inventory_history_loader():
    # Estoque é corporativo; filtros de cliente e vendedor não recortam o saldo.
    result=apply_filters(df,grupo=grupo,subgrupo=subgrupo,tipo=tipo,espec=espec,sub_espec=sub_espec,espessura=esp,produto_text=pt)
    return _filter_chart_dimension(result,*chart_filter) if chart_filter else result
target_filters={
    "sellers": ([seller_scope] if access["role"] == "seller" else vend),
    "seller_panels": vendedor_painel,
    "seller_groups": grupo_vendedor,
    "groups": grupo,
    "client": selected_client,
    "client_text": ct,
    "product_text": pt,
}

if f.empty:
    st.warning("Nenhum registro encontrado com os filtros atuais. Ajuste os filtros para continuar a análise.")

dashboard_kwargs={
    "permissions": access["permissions"], "current_user": access["user"], "targets": lambda: get_targets(load_version),
    "target_history": target_history_loader, "target_filters": target_filters,
    "commercial_indicators": load_status.get("indicadores", {}),
    # Pedidos, metas e estoque são carregados apenas ao abrir suas páginas.
    # A base de eventos do funil continua sendo publicada para o HTML, mas não
    # é baixada pelo Streamlit enquanto nenhuma página visível a utiliza.
    "flow_events": None,
    "order_actual": lambda: get_pedidos_realizado(load_version),
    "view_filters": {
        "uf": uf, "clusters": cidade_pivot,
        "seller_scope": seller_scope if access["role"] == "seller" else None,
        "order_actual_filters": {
            "sellers": [seller_scope] if access["role"] == "seller" else vend,
            "seller_panels": vendedor_painel,
            "groups": grupo, "segments": canal, "tipologies": tipologia,
            "uf": uf, "municipalities": city, "clusters": cidade_pivot,
            "client": selected_client, "client_text": ct, "product_text": pt,
        },
        "released_order_filters": {
            "sellers": [seller_scope] if access["role"] == "seller" else vend,
            "seller_panels": vendedor_painel,
            "client": selected_client, "client_text": ct, "product_text": pt, "groups": grupo,
        },
    },
}
# O Streamlit pode recarregar app.py antes dos módulos importados. Durante essa
# janela curta, só envia os argumentos novos se a função já os reconhecer.
dashboard_parameters=inspect.signature(render_operational_dashboard).parameters
if "stock" in dashboard_parameters:
    dashboard_kwargs["stock"]=lambda: get_stock(load_version)
if "inventory_history" in dashboard_parameters:
    dashboard_kwargs["inventory_history"]=inventory_history_loader
if "order_actual" not in dashboard_parameters:
    dashboard_kwargs.pop("order_actual",None)

render_operational_dashboard(
    f, monitor_scope, start_date, end_date, last_load,
    brl, brl2, pct, pp, show_chart, show_table,
    **dashboard_kwargs,
)
st.stop()
