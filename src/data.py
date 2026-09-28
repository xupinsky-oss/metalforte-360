import io
import os
import unicodedata
from functools import lru_cache
from pathlib import Path
import pandas as pd
from src.cloud_storage import download_bytes, is_configured

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "metalforte_base.csv.gz"
DEFAULT_TARGETS = Path(__file__).resolve().parents[1] / "data" / "metalforte_metas.csv.gz"
DEFAULT_FLOW = Path(__file__).resolve().parents[1] / "data" / "metalforte_fluxo.csv.gz"
CITY_CLUSTERS = Path(__file__).resolve().parents[1] / "resources" / "cidades_pivot.csv.gz"
NUMERIC = ["Faturamento","Peso","Preço Real Kg","Benchmark Grupo","Desvio Benchmark %","Custo","Impostos","PIS","COFINS","ICMS","Margem","Margem %","Espessura"]


def _location_key(value):
    text=unicodedata.normalize("NFKD", "" if pd.isna(value) else str(value))
    return "".join(char for char in text if not unicodedata.combining(char)).strip().upper()


@lru_cache(maxsize=1)
def _cached_city_clusters():
    if not CITY_CLUSTERS.exists():
        return pd.DataFrame(columns=["UF","Município","_municipio_key","Cidade PIVOT","Cluster PIVOT","Latitude","Longitude"])
    result=pd.read_csv(CITY_CLUSTERS,compression="gzip",low_memory=False)
    result["UF"]=result["UF"].fillna("").astype(str).str.strip().str.upper()
    result["_municipio_key"]=result["_municipio_key"].fillna("").astype(str)
    return result.drop_duplicates(["UF","_municipio_key"],keep="first")


def load_city_clusters():
    """Matriz pública/gerencial de municípios e respectivas cidades PIVOT."""
    return _cached_city_clusters().copy()


def enrich_city_clusters(frame):
    """Acrescenta o cluster geográfico sem alterar o grão da base realizada."""
    if frame is None or frame.empty or not {"UF","Município"}.issubset(frame.columns):
        return frame
    mapping=load_city_clusters()[["UF","_municipio_key","Cidade PIVOT","Cluster PIVOT"]]
    if mapping.empty:
        return frame
    result=frame.drop(columns=[column for column in ("Cidade PIVOT","Cluster PIVOT") if column in frame],errors="ignore").copy()
    result["_municipio_key"]=result["Município"].map(_location_key)
    result["UF"]=result["UF"].fillna("").astype(str).str.strip().str.upper()
    result=result.merge(mapping,on=["UF","_municipio_key"],how="left",validate="many_to_one")
    result["Cidade PIVOT"]=result["Cidade PIVOT"].fillna("Não mapeado")
    result["Cluster PIVOT"]=result["Cluster PIVOT"].fillna("Não mapeado")
    return result.drop(columns="_municipio_key")

def load_data(path=None):
    path=Path(path) if path else DEFAULT_DATA
    if path.exists():
        source=path; compression="infer"
    elif is_configured():
        source=io.BytesIO(download_bytes()); compression="gzip"
    else:
        raise FileNotFoundError("Base não encontrada. Configure o Supabase ou disponibilize data/metalforte_base.csv.gz.")
    df=pd.read_csv(source,low_memory=False,compression=compression)
    df["Data"]=pd.to_datetime(df["Data"],errors="coerce")
    if "Data Pedido" in df:
        df["Data Pedido"]=pd.to_datetime(df["Data Pedido"],errors="coerce")
    if "Mes" not in df: df["Mes"]=df["Data"].dt.strftime("%Y-%m")
    if "Ano" not in df: df["Ano"]=df["Data"].dt.year
    for c in NUMERIC:
        if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
    for c in ["UF","Município","Grupo Produto","Subgrupo Produto","Tipo Produto","ESPEC.","Sub Espec.","Fonte Classificação Produto","Vendedor","Filial","Canal","Segmento Cliente","Tipologia Cliente","Curva Cliente"]:
        if c in df: df[c]=df[c].fillna("Não mapeado").astype(str)
    # Regra comercial METALFORTE: "Canal" é o segmento de clientes.
    # Mantemos o alias para preservar filtros e relatórios legados que já usam
    # o nome Canal, mas a fonte oficial passa a ser Segmento Cliente.
    if "Segmento Cliente" in df:
        df["Canal"]=df["Segmento Cliente"]
    return enrich_city_clusters(df)

def load_targets(path=None):
    path=Path(path) if path else DEFAULT_TARGETS
    try:
        if path.exists(): source=path
        elif is_configured(): source=io.BytesIO(download_bytes(object_path=os.getenv("SUPABASE_TARGET_PATH", "bases/metalforte_metas.csv.gz")))
        else: return pd.DataFrame()
        result=pd.read_csv(source,low_memory=False,compression="gzip")
    except Exception:
        return pd.DataFrame()
    if "Competência" in result: result["Competência"]=pd.to_datetime(result["Competência"],errors="coerce")
    for column in ("Meta KG","Meta R$"):
        if column in result: result[column]=pd.to_numeric(result[column],errors="coerce")
    return result

def load_flow(path=None):
    """Carrega a trilha privada do funil e preserva cada data do processo."""
    path=Path(path) if path else DEFAULT_FLOW
    try:
        if path.exists(): source=path
        elif is_configured(): source=io.BytesIO(download_bytes(object_path=os.getenv("SUPABASE_FLOW_PATH", "bases/metalforte_fluxo.csv.gz")))
        else: return pd.DataFrame()
        result=pd.read_csv(source,low_memory=False,compression="gzip")
    except Exception:
        return pd.DataFrame()
    for column in result.columns:
        if str(column).startswith("Data "):
            result[column]=pd.to_datetime(result[column],errors="coerce")
    for column in ("Peso","Valor"):
        if column in result: result[column]=pd.to_numeric(result[column],errors="coerce")
    return result

def apply_filters(df, years=None, months=None, filial=None, uf=None, municipio=None, cidade_pivot=None, vendedor=None, canal=None, tipologia=None, grupo=None, subgrupo=None, tipo=None, espec=None, sub_espec=None, espessura=None, cliente=None, cliente_text="", produto_text="", start_date=None, end_date=None):
    x=df
    if start_date is not None: x=x[x["Data"]>=pd.Timestamp(start_date)]
    if end_date is not None: x=x[x["Data"]<pd.Timestamp(end_date)+pd.Timedelta(days=1)]
    if years: x=x[x["Ano"].isin(years)]
    if months: x=x[x["Data"].dt.month.isin(months)]
    for col,values in [("Filial",filial),("UF",uf),("Município",municipio),("Cluster PIVOT",cidade_pivot),("Vendedor",vendedor),("Canal",canal),("Tipologia Cliente",tipologia),("Grupo Produto",grupo),("Subgrupo Produto",subgrupo),("Tipo Produto",tipo),("ESPEC.",espec),("Sub Espec.",sub_espec),("Espessura",espessura)]:
        if values and col in x: x=x[x[col].isin(values)]
    if cliente and "Cliente" in x: x=x[x["Cliente"]==cliente]
    if cliente_text: x=x[x["Cliente"].fillna("").str.contains(cliente_text,case=False,na=False)]
    if produto_text: x=x[x["Produto"].fillna("").str.contains(produto_text,case=False,na=False)]
    return x
