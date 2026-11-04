import io
import os
import re
import unicodedata
import time
import logging
import hashlib
from functools import lru_cache
from pathlib import Path
import pandas as pd
from src.cloud_storage import download_bytes, is_configured, upload_bytes
from src.dimensions import normalize_dimensions
from src.product_groups import normalize_product_group
from src.data_catalog import object_path as dataset_path, local_path

DEFAULT_DATA = local_path("sales")
DEFAULT_TARGETS = local_path("targets")
DEFAULT_FLOW = local_path("flow")
DEFAULT_STOCK = local_path("stock")
DEFAULT_PEDIDOS_REALIZADO = local_path("orders")
CITY_CLUSTERS = Path(__file__).resolve().parents[1] / "resources" / "cidades_pivot.csv.gz"
NUMERIC = ["Faturamento","Peso","Preço Real Kg","Benchmark Grupo","Desvio Benchmark %","Custo","Impostos","PIS","COFINS","ICMS","Margem","Margem %","Espessura"]
DEFAULT_DEPARA_PATH = "bases/DE_PARA_METALFORTE360.xlsx"
_DEPARA_VERSION = None


def set_depara_version(version):
    global _DEPARA_VERSION
    _DEPARA_VERSION = version


def _depara_cache_key():
    return _DEPARA_VERSION if _DEPARA_VERSION is not None else int(time.time() // 60)


def _location_key(value):
    text=unicodedata.normalize("NFKD", "" if pd.isna(value) else str(value))
    return "".join(char for char in text if not unicodedata.combining(char)).strip().upper()


def _dimension_key(value):
    text = unicodedata.normalize("NFKD", "" if pd.isna(value) else str(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text)


def _code_key(value):
    text = "" if pd.isna(value) else str(value).strip()
    text = re.sub(r"\.0$", "", text).strip()
    return (text.lstrip("0") or "0") if text.isdigit() else text


def _first_column(frame, names):
    keys = {_dimension_key(column): column for column in frame.columns}
    return next((keys[_dimension_key(name)] for name in names if _dimension_key(name) in keys), None)


def _read_mapping_sheet(workbook, sheet_name):
    """Reconhece títulos mesmo com linhas vazias/capa antes do cabeçalho."""
    preview = pd.read_excel(workbook, sheet_name=sheet_name, header=None, nrows=25, dtype=str)
    required = {"vendedorcadastro", "vendedorpainel"} if _dimension_key(sheet_name) == "deparavendedor" else {"cliente", "grupoeconomico"}
    header = next((index for index, row in preview.iterrows() if required.issubset({_dimension_key(value) for value in row})), None)
    if header is None:
        raise ValueError(f"Cabeçalho de agrupamentos não encontrado na aba {sheet_name}.")
    return pd.read_excel(workbook, sheet_name=sheet_name, header=int(header), dtype=str)


@lru_cache(maxsize=2)
def _cached_depara(object_path, version_window=0):
    """Lê o DE/PARA do bucket privado e mantém somente dimensões necessárias."""
    if not is_configured():
        return None
    try:
        payload = download_bytes(object_path=object_path)
        workbook = pd.ExcelFile(io.BytesIO(payload), engine="openpyxl")
        seller_sheet = next((name for name in workbook.sheet_names if _dimension_key(name) == "deparavendedor"), None)
        client_sheet = next((name for name in workbook.sheet_names if _dimension_key(name) == "deparacliente"), None)
        if not seller_sheet or not client_sheet:
            return None
        sellers = _read_mapping_sheet(workbook, seller_sheet)
        clients = _read_mapping_sheet(workbook, client_sheet)

        seller_source = _first_column(sellers, ("VENDEDOR CADASTRO",))
        seller_panel = _first_column(sellers, ("VENDEDOR PAINEL",))
        seller_group = _first_column(sellers, ("CLASSIFICAÇÃO", "CLASSIFICACAO"))
        customer_code = _first_column(clients, ("Cód. Cliente", "Cod. Cliente", "Código Cliente", "Cod Cliente"))
        customer_branch = _first_column(clients, ("Lj Cliente", "Loja Cliente", "Filial Cliente"))
        customer_name = _first_column(clients, ("Cliente", "Nome Cliente"))
        economic_group = _first_column(clients, ("GRUPO ECONOMICO", "Grupo Econômico", "Grupo Economico"))
        if not all((seller_source, seller_panel, seller_group, customer_code, customer_name, economic_group)):
            return None

        seller_map = sellers[[seller_source, seller_panel, seller_group]].copy()
        seller_map.columns = ["_source", "Vendedor Painel", "Grupo Vendedor"]
        seller_map = seller_map.dropna(subset=["_source"])
        seller_map["_key"] = seller_map["_source"].map(_dimension_key)
        seller_known = set(seller_map.loc[seller_map["_key"].ne(""), "_key"])
        seller_map = seller_map.dropna(subset=["Vendedor Painel"])
        seller_map["Grupo Vendedor"] = seller_map["Grupo Vendedor"].fillna("Não classificado")
        seller_map = seller_map[seller_map["_key"].ne("")].drop_duplicates("_key", keep="last")

        client_cols = [customer_code, customer_name, economic_group]
        if customer_branch:
            client_cols.insert(1, customer_branch)
        client_map = clients[client_cols].copy()
        renamed = {customer_code: "_code", customer_name: "_name", economic_group: "Grupo Econômico Cliente"}
        if customer_branch:
            renamed[customer_branch] = "_branch"
        client_map = client_map.rename(columns=renamed)
        client_map["_code_key"] = client_map["_code"].map(_code_key)
        client_map["_name_key"] = client_map["_name"].map(_dimension_key)
        if "_branch" in client_map:
            client_map["_branch_key"] = client_map["_branch"].map(_code_key)
            client_map["_composite_key"] = client_map["_code_key"] + "|" + client_map["_branch_key"]
        else:
            client_map["_composite_key"] = ""
        client_map["Grupo Econômico Cliente"] = client_map["Grupo Econômico Cliente"].fillna("").astype(str).str.strip()

        def unique_lookup(key_column):
            pairs = client_map.loc[client_map[key_column].ne("") & client_map["Grupo Econômico Cliente"].ne(""), [key_column, "Grupo Econômico Cliente"]].drop_duplicates()
            counts = pairs.groupby(key_column)["Grupo Econômico Cliente"].nunique()
            valid = counts[counts.eq(1)].index
            return pairs[pairs[key_column].isin(valid)].drop_duplicates(key_column).set_index(key_column)["Grupo Econômico Cliente"].to_dict()

        def known_lookup(key_column):
            return set(client_map.loc[client_map[key_column].ne(""), key_column].dropna().astype(str))

        return {
            "sellers": seller_map.set_index("_key")[["Vendedor Painel", "Grupo Vendedor"]].to_dict("index"),
            "seller_known": seller_known,
            "customer_composite": unique_lookup("_composite_key"),
            "customer_code": unique_lookup("_code_key"),
            "customer_name": unique_lookup("_name_key"),
            "customer_known_composite": known_lookup("_composite_key"),
            "customer_known_code": known_lookup("_code_key"),
            "customer_known_name": known_lookup("_name_key"),
        }
    except Exception as error:
        logging.getLogger(__name__).warning("DE/PARA indisponível (%s)", type(error).__name__)
        # DE/PARA ausente ou temporariamente indisponível não impede a leitura
        # das vendas publicadas; a interface permanece funcional sem agrupamento.
        return None


def apply_depara(frame):
    """Acrescenta grupos econômicos e consolidações sem sobrescrever campos fonte."""
    if frame is None or frame.empty:
        return frame
    object_path = dataset_path("depara")
    mapping = _cached_depara(object_path, _depara_cache_key())
    result = frame.copy()
    if mapping:
        seller_column = _first_column(result, ("Vendedor", "Vendedor cadastro", "Nome Vendedor"))
        if seller_column:
            seller_keys = result[seller_column].map(dict((value, _dimension_key(value)) for value in result[seller_column].drop_duplicates()))
            result["Vendedor Painel"] = seller_keys.map(lambda key: mapping["sellers"].get(key, {}).get("Vendedor Painel", "Não mapeado"))
            result["Grupo Vendedor"] = seller_keys.map(lambda key: mapping["sellers"].get(key, {}).get("Grupo Vendedor", "Não mapeado"))
            seller_known = seller_keys.isin(mapping.get("seller_known", set()))
            seller_mapped = result["Vendedor Painel"].fillna("").astype(str).str.strip().ne("") & ~result["Vendedor Painel"].astype(str).str.casefold().isin({"não mapeado", "nao mapeado"})
            result["Status DE/PARA Vendedor"] = pd.Series("Novo no DE/PARA", index=result.index, dtype="string")
            result.loc[seller_known & ~seller_mapped, "Status DE/PARA Vendedor"] = "Sem grupo"
            result.loc[seller_mapped, "Status DE/PARA Vendedor"] = "Com grupo"

        code_column = _first_column(result, ("Cod Cliente", "Cód. Cliente", "Código Cliente", "Cliente Código"))
        branch_column = _first_column(result, ("Lj Cliente", "Loja Cliente", "Filial Cliente"))
        name_column = _first_column(result, ("Cliente", "Nome Cliente"))
        group_values = pd.Series(pd.NA, index=result.index, dtype="object")
        known_customer = pd.Series(False, index=result.index)
        if code_column:
            codes = result[code_column].map(dict((value, _code_key(value)) for value in result[code_column].drop_duplicates()))
            if branch_column:
                branches = result[branch_column].map(_code_key)
                composite_keys = codes + "|" + branches
                composite = composite_keys.map(mapping["customer_composite"].get)
                known_customer |= composite_keys.isin(mapping.get("customer_known_composite", set()))
                group_values = group_values.where(composite.isna(), composite)
            by_code = codes.map(mapping["customer_code"].get)
            known_customer |= codes.isin(mapping.get("customer_known_code", set()))
            group_values = group_values.where(group_values.notna() | by_code.isna(), by_code)
        if name_column:
            name_keys = result[name_column].map(dict((value, _dimension_key(value)) for value in result[name_column].drop_duplicates()))
            by_name = name_keys.map(mapping["customer_name"].get)
            known_customer |= name_keys.isin(mapping.get("customer_known_name", set()))
            group_values = group_values.where(group_values.notna() | by_name.isna(), by_name)
        result["Grupo Econômico Cliente"] = group_values.fillna("Não mapeado")
        valid_group = group_values.notna() & group_values.astype(str).str.strip().ne("") & ~group_values.astype(str).str.casefold().isin({"não mapeado", "nao mapeado"})
        result["Status DE/PARA Cliente"] = pd.Series("Novo no DE/PARA", index=result.index, dtype="string")
        result.loc[known_customer & ~valid_group, "Status DE/PARA Cliente"] = "Sem grupo"
        result.loc[valid_group, "Status DE/PARA Cliente"] = "Com grupo"
    else:
        if "Vendedor" in result:
            result["Status DE/PARA Vendedor"] = "DE/PARA indisponível"
        if "Cliente" in result:
            result["Status DE/PARA Cliente"] = "DE/PARA indisponível"

    # Rótulo para visuais e filtros: o nome jurídico fica preservado apenas
    # como detalhe para drill-down. Não alteramos o grão nem as chaves de CNPJ.
    if "Cliente" in result:
        result["Razão Social"] = result["Cliente"]
        groups = result.get("Grupo Econômico Cliente", pd.Series("Não mapeado", index=result.index))
        valid_group = groups.notna() & groups.astype(str).str.strip().ne("") & ~groups.astype(str).str.casefold().isin({"não mapeado", "nao mapeado"})
        result["Cliente Painel"] = groups.where(valid_group, result["Razão Social"]).fillna("Cliente sem razão social").astype("string")
    if "Vendedor" in result:
        if "Vendedor Painel" not in result:
            result["Vendedor Painel"] = result["Vendedor"]
        panel = result["Vendedor Painel"].fillna("").astype(str).str.strip()
        missing_panel = panel.eq("") | panel.str.casefold().isin({"não mapeado", "nao mapeado"})
        result["Vendedor Painel"] = panel.where(~missing_panel, "Não mapeado").astype("string")
    return result


def depara_available():
    """Indica se o arquivo de mapeamento privado está acessível nesta sessão."""
    return _cached_depara(dataset_path("depara"), _depara_cache_key()) is not None


def prepare_depara_upload(payload):
    """Valida e reduz o xlsx aos campos de agrupamento antes do envio privado."""
    workbook = pd.ExcelFile(io.BytesIO(payload), engine="openpyxl")
    seller_sheet = next((name for name in workbook.sheet_names if _dimension_key(name) == "deparavendedor"), None)
    client_sheet = next((name for name in workbook.sheet_names if _dimension_key(name) == "deparacliente"), None)
    if not seller_sheet or not client_sheet:
        raise ValueError("A planilha precisa conter as abas DE_PARA_VENDEDOR e DE_PARA_CLIENTE.")

    seller_headers = _read_mapping_sheet(workbook, seller_sheet)
    seller_columns = [
        _first_column(seller_headers, ("VENDEDOR CADASTRO",)),
        _first_column(seller_headers, ("CLASSIFICAÇÃO", "CLASSIFICACAO")),
        _first_column(seller_headers, ("VENDEDOR PAINEL",)),
    ]
    client_headers = _read_mapping_sheet(workbook, client_sheet)
    customer_code = _first_column(client_headers, ("Cód. Cliente", "Cod. Cliente", "Código Cliente", "Cod Cliente"))
    customer_branch = _first_column(client_headers, ("Lj Cliente", "Loja Cliente", "Filial Cliente"))
    customer_name = _first_column(client_headers, ("Cliente", "Nome Cliente"))
    economic_group = _first_column(client_headers, ("GRUPO ECONOMICO", "Grupo Econômico", "Grupo Economico"))
    if not all(seller_columns) or not all((customer_code, customer_name, economic_group)):
        raise ValueError("Não encontrei as colunas necessárias de vendedor, código/cliente e grupo econômico.")

    sellers = seller_headers[seller_columns].copy()
    clients_columns = [customer_code, customer_name, economic_group] + ([customer_branch] if customer_branch else [])
    clients = client_headers[clients_columns].copy()
    sellers = sellers.rename(columns={
        seller_columns[0]: "VENDEDOR CADASTRO",
        seller_columns[1]: "CLASSIFICAÇÃO",
        seller_columns[2]: "VENDEDOR PAINEL",
    })
    clients = clients.rename(columns={
        customer_code: "Cód. Cliente", customer_name: "Cliente",
        economic_group: "GRUPO ECONOMICO",
        **({customer_branch: "Lj Cliente"} if customer_branch else {}),
    })
    sellers = sellers.dropna(subset=["VENDEDOR CADASTRO", "VENDEDOR PAINEL"])
    # Cadastros sem grupo também precisam existir para a auditoria distinguir
    # "Sem grupo" de "Novo no DE/PARA".
    clients = clients.dropna(subset=["Cód. Cliente", "Cliente"])
    sellers = sellers.drop_duplicates()
    clients = clients.drop_duplicates()
    if sellers.empty or clients.empty:
        raise ValueError("O DE/PARA não contém cadastros válidos de clientes e vendedores.")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sellers.to_excel(writer, sheet_name="DE_PARA_VENDEDOR", index=False)
        clients.to_excel(writer, sheet_name="DE_PARA_CLIENTE", index=False)
    return output.getvalue(), {"vendedores": len(sellers), "clientes": len(clients)}


def clear_depara_cache():
    _cached_depara.cache_clear()


def publish_depara(payload):
    """Validação e publicação usadas tanto pela tela administrativa quanto pelo CLI."""
    normalized, counts = prepare_depara_upload(payload)
    destination = dataset_path("depara")
    if not upload_bytes(normalized, destination, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
        raise RuntimeError("Armazenamento privado não configurado.")
    confirmed = download_bytes(object_path=destination)
    if hashlib.sha256(confirmed).digest() != hashlib.sha256(normalized).digest():
        raise RuntimeError("O arquivo publicado não passou na conferência de integridade.")
    clear_depara_cache()
    return counts


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

def _read_dataset(dataset, path=None, *, required=False):
    """Um único critério de origem: override explícito, nuvem ou desenvolvimento."""
    try:
        if path is not None:
            source = Path(path)
            if not source.exists():
                raise FileNotFoundError("Arquivo de desenvolvimento não encontrado.")
            compression = "infer"
        elif is_configured():
            source = io.BytesIO(download_bytes(object_path=dataset_path(dataset)))
            compression = "gzip"
        else:
            source = local_path(dataset)
            if not source.exists():
                raise FileNotFoundError("Base não encontrada. Configure o Supabase ou a base de desenvolvimento.")
            compression = "infer"
        return pd.read_csv(source, low_memory=False, compression=compression)
    except Exception as error:
        logging.getLogger(__name__).warning("Base %s indisponível (%s)", dataset, type(error).__name__)
        if required:
            raise
        result = pd.DataFrame()
        result.attrs["load_error"] = type(error).__name__
        result.attrs["dataset"] = dataset
        return result


def load_data(path=None):
    df=_read_dataset("sales",path,required=True)
    df["Data"]=pd.to_datetime(df["Data"],errors="coerce")
    if "Data Pedido" in df:
        df["Data Pedido"]=pd.to_datetime(df["Data Pedido"],errors="coerce")
    if "Mes" not in df: df["Mes"]=df["Data"].dt.strftime("%Y-%m")
    if "Ano" not in df: df["Ano"]=df["Data"].dt.year
    for c in NUMERIC:
        if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
    for c in ["UF","Município","Grupo Produto","Subgrupo Produto","Tipo Produto","ESPEC.","Sub Espec.","Fonte Classificação Produto","Vendedor","Filial","Canal","Segmento Cliente","Tipologia Cliente","Curva Cliente"]:
        if c in df: df[c]=df[c].fillna("Não mapeado").astype(str)
    df=normalize_dimensions(df)
    df=apply_depara(df)
    if "Grupo Produto" in df:
        df["Grupo Produto"]=df["Grupo Produto"].map(normalize_product_group)
    # Regra comercial METALFORTE: "Canal" é o segmento de clientes.
    # Mantemos o alias para preservar filtros e relatórios legados que já usam
    # o nome Canal, mas a fonte oficial passa a ser Segmento Cliente.
    if "Segmento Cliente" in df:
        df["Canal"]=df["Segmento Cliente"]
    return enrich_city_clusters(df)

def load_targets(path=None):
    result=_read_dataset("targets",path)
    if result.empty: return result
    if "Competência" in result: result["Competência"]=pd.to_datetime(result["Competência"],errors="coerce")
    result=normalize_dimensions(result)
    result=apply_depara(result)
    if "Grupo Produto" in result: result["Grupo Produto"]=result["Grupo Produto"].map(normalize_product_group)
    for column in ("Meta KG","Meta R$"):
        if column in result: result[column]=pd.to_numeric(result[column],errors="coerce")
    return result

def load_flow(path=None):
    """Carrega a trilha privada do funil e preserva cada data do processo."""
    result=_read_dataset("flow",path)
    if result.empty: return result
    for column in result.columns:
        if str(column).startswith("Data "):
            result[column]=pd.to_datetime(result[column],errors="coerce")
    result=normalize_dimensions(result)
    result=apply_depara(result)
    for column in ("Peso","Valor","Projeção Custo","Projeção Imposto","Projeção Margem","Margem %"):
        if column in result: result[column]=pd.to_numeric(result[column],errors="coerce")
    return result


def load_stock(path=None):
    """Carrega a fotografia atual do relatório de estoque 19745161."""
    from src.inventory import prepare_stock
    result=_read_dataset("stock",path)
    return prepare_stock(result) if not result.empty else result


def load_pedidos_realizado(path=None):
    """Carrega a série separada de pedidos liberados e faturamento realizado."""
    result=_read_dataset("orders",path)
    if result.empty: return result
    if "Competência" in result:
        result["Competência"]=pd.to_datetime(result["Competência"],errors="coerce")
    for column in ("Pedidos (R$)","Pedidos (kg)","Faturado (R$)","Faturado (kg)"):
        if column in result: result[column]=pd.to_numeric(result[column],errors="coerce").fillna(0)
    for column in ("Cod Cliente","Produto Codigo","Cod Vendedor"):
        if column in result: result[column]=result[column].fillna("").astype(str).str.replace(r"\.0$","",regex=True).str.strip()
    return apply_depara(normalize_dimensions(result))

def apply_filters(df, years=None, months=None, filial=None, uf=None, municipio=None, cidade_pivot=None, vendedor=None, vendedor_painel=None, grupo_vendedor=None, grupo_economico=None, canal=None, tipologia=None, grupo=None, subgrupo=None, tipo=None, espec=None, sub_espec=None, espessura=None, cliente=None, cliente_text="", produto_text="", start_date=None, end_date=None):
    x=df
    if start_date is not None: x=x[x["Data"]>=pd.Timestamp(start_date)]
    if end_date is not None: x=x[x["Data"]<pd.Timestamp(end_date)+pd.Timedelta(days=1)]
    if years: x=x[x["Ano"].isin(years)]
    if months: x=x[x["Data"].dt.month.isin(months)]
    for col,values in [("Filial",filial),("UF",uf),("Município",municipio),("Cluster PIVOT",cidade_pivot),("Vendedor",vendedor),("Vendedor Painel",vendedor_painel),("Grupo Vendedor",grupo_vendedor),("Grupo Econômico Cliente",grupo_economico),("Canal",canal),("Tipologia Cliente",tipologia),("Grupo Produto",grupo),("Subgrupo Produto",subgrupo),("Tipo Produto",tipo),("ESPEC.",espec),("Sub Espec.",sub_espec),("Espessura",espessura)]:
        if values and col in x: x=x[x[col].isin(values)]
    client_label = "Cliente Painel" if "Cliente Painel" in x else ("Grupo Econômico Cliente" if "Grupo Econômico Cliente" in x else "Cliente")
    if cliente and client_label in x: x=x[x[client_label].astype(str)==str(cliente)]
    if cliente_text and client_label in x: x=x[x[client_label].fillna("").astype(str).str.contains(cliente_text,case=False,na=False)]
    if produto_text: x=x[x["Produto"].fillna("").str.contains(produto_text,case=False,na=False)]
    return x
