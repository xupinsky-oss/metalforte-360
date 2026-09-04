import io
from pathlib import Path
import pandas as pd
from src.cloud_storage import download_bytes, is_configured

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "metalforte_base.csv.gz"
NUMERIC = ["Faturamento","Peso","Preço Real Kg","Benchmark Grupo","Desvio Benchmark %","Custo","Impostos","PIS","COFINS","ICMS","Margem","Margem %","Espessura"]

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
    if "Mes" not in df: df["Mes"]=df["Data"].dt.strftime("%Y-%m")
    if "Ano" not in df: df["Ano"]=df["Data"].dt.year
    for c in NUMERIC:
        if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
    for c in ["UF","Município","Grupo Produto","Tipo Produto","Vendedor","Filial","Segmento Cliente","Tipologia Cliente","Curva Cliente"]:
        if c in df: df[c]=df[c].fillna("Não mapeado").astype(str)
    return df

def apply_filters(df, years=None, months=None, filial=None, uf=None, municipio=None, vendedor=None, grupo=None, tipo=None, espessura=None, cliente_text="", produto_text="", start_date=None, end_date=None):
    x=df
    if start_date is not None: x=x[x["Data"]>=pd.Timestamp(start_date)]
    if end_date is not None: x=x[x["Data"]<pd.Timestamp(end_date)+pd.Timedelta(days=1)]
    if years: x=x[x["Ano"].isin(years)]
    if months: x=x[x["Data"].dt.month.isin(months)]
    for col,values in [("Filial",filial),("UF",uf),("Município",municipio),("Vendedor",vendedor),("Grupo Produto",grupo),("Tipo Produto",tipo),("Espessura",espessura)]:
        if values: x=x[x[col].isin(values)]
    if cliente_text: x=x[x["Cliente"].fillna("").str.contains(cliente_text,case=False,na=False)]
    if produto_text: x=x[x["Produto"].fillna("").str.contains(produto_text,case=False,na=False)]
    return x
