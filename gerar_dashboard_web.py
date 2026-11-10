"""Gera o resumo privado do painel comercial com carteira e estoque.

O arquivo permanece no bucket privado e as funções de leitura verificam
a identidade do proprietário antes de entregar os dados por cliente.
"""

import json
import os
from datetime import datetime

import pandas as pd

from src.cloud_storage import upload_bytes
from src.data import load_data, load_stock
from src.inventory import build_inventory_analysis
from src.value_intelligence import portfolio_health


OUTPUT_PATH = os.getenv("SUPABASE_DASHBOARD_PATH", "dashboard/command-center.json")
INDICATORS_PATH = os.path.join(os.path.dirname(__file__), "data", "indicadores_comerciais.json")
FLOW_PATH = os.path.join(os.path.dirname(__file__), "data", "metalforte_fluxo.csv.gz")


def _number(value):
    if pd.isna(value):
        return 0
    return round(float(value), 4)


def _metrics(data):
    revenue = data["Faturamento"].sum()
    margin = data["Margem"].sum()
    return {
        "faturamento": _number(revenue),
        "peso": _number(data["Peso"].sum()),
        "margem": _number(margin),
        "margem_pct": _number(margin / revenue) if revenue else 0,
        "clientes": int(data["Cliente"].nunique()),
        "produtos": int(data["Produto"].nunique()),
        "preco_medio_kg": _number(revenue / data["Peso"].sum()) if data["Peso"].sum() else 0,
    }


def _breakdown(data, dimension, limit=10):
    if dimension not in data:
        return []
    grouped = data.groupby(dimension, dropna=False).agg(
        faturamento=("Faturamento", "sum"),
        peso=("Peso", "sum"),
        margem=("Margem", "sum"),
        clientes=("Cliente", "nunique"),
        produtos=("Produto", "nunique"),
    ).reset_index().sort_values("faturamento", ascending=False)
    total = grouped["faturamento"].sum()
    grouped["margem_pct"] = grouped["margem"] / grouped["faturamento"].replace(0, pd.NA)
    grouped["participacao_pct"] = grouped["faturamento"] / total if total else 0
    records = []
    for _, row in grouped.head(limit).iterrows():
        records.append({
            "nome": str(row[dimension]) if pd.notna(row[dimension]) else "Não mapeado",
            "faturamento": _number(row["faturamento"]),
            "peso": _number(row["peso"]),
            "margem": _number(row["margem"]),
            "margem_pct": _number(row["margem_pct"]),
            "participacao_pct": _number(row["participacao_pct"]),
            "clientes": int(row["clientes"]),
            "produtos": int(row["produtos"]),
        })
    return records


def _load_indicators():
    if not os.path.exists(INDICATORS_PATH):
        return {}
    try:
        with open(INDICATORS_PATH, encoding="utf-8") as source:
            return json.load(source).get("valores", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _optional_number(indicators, key):
    return _number(indicators[key]) if key in indicators else None


def _customer_payload(history, end_date):
    """Publica status e carteira mínima, sem telefone, e-mail ou histórico por nota."""
    _, detail = portfolio_health(history, end_date, inactivity_days=180)
    if detail.empty:
        return {
            "data_referencia": pd.Timestamp(end_date).date().isoformat(),
            "regras": {"novo_dias": 90, "ativo_dias": 90, "em_risco_dias": 180},
            "contagens": {"total": 0, "novos": 0, "ativos": 0, "em_risco": 0, "inativos": 0},
            "clientes": [],
        }
    names = {
        "Novo": "novos",
        "Ativo": "ativos",
        "Em risco": "em_risco",
        "Inativo": "inativos",
    }
    counts = {value: int(detail["Status"].eq(key).sum()) for key, value in names.items()}
    counts["total"] = int(len(detail))
    columns = [
        "Cod Cliente", "Cliente", "Vendedor", "Segmento Cliente", "UF", "Município",
        "Primeira compra", "Última compra", "Dias sem comprar", "Status",
        "Faturamento 12m", "KG 12m", "Pedidos 12m", "Grupo Produto",
    ]
    if "Grupo Produto" in history and "Cod Cliente" in history:
        eligible = history[pd.to_datetime(history["Data"], errors="coerce").le(pd.Timestamp(end_date))].copy()
        if not eligible.empty:
            latest_groups = eligible.sort_values("Data").groupby("Cod Cliente", dropna=False).tail(1)
            group_map = {
                str(row["Cod Cliente"]).removesuffix(".0"): str(row["Grupo Produto"])
                for _, row in latest_groups[["Cod Cliente", "Grupo Produto"]].iterrows()
            }
            detail["Grupo Produto"] = detail["Cod Cliente"].astype(str).str.removesuffix(".0").map(group_map).fillna("Não mapeado")
    else:
        detail["Grupo Produto"] = "Não mapeado"
    records = []
    ordered = detail.sort_values(
        ["Status", "Dias sem comprar", "Faturamento 12m"],
        ascending=[True, False, False],
    )
    for row in ordered[[column for column in columns if column in ordered]].to_dict("records"):
        item = {}
        for key, value in row.items():
            if key in ("Primeira compra", "Última compra"):
                item[key] = pd.Timestamp(value).date().isoformat() if pd.notna(value) else None
            elif key == "Cod Cliente":
                item[key] = str(value).removesuffix(".0") if pd.notna(value) else ""
            elif isinstance(value, (int, float)) and key not in ("Dias sem comprar", "Pedidos 12m"):
                item[key] = _number(value)
            elif pd.isna(value):
                item[key] = None
            else:
                item[key] = value.item() if hasattr(value, "item") else value
        records.append(item)
    return {
        "data_referencia": pd.Timestamp(end_date).date().isoformat(),
        "regras": {
            "novo_dias": 90,
            "ativo_dias": 90,
            "em_risco_dias": 180,
            "descricao": "Novo: primeira compra nos últimos 90 dias; ativo: última compra há até 90 dias; em risco: 91 a 180 dias; inativo: acima de 180 dias.",
        },
        "contagens": counts,
        "clientes": records,
    }


def _inventory_payload(stock, sales, months=3):
    """Cruza a fotografia do ERP com vendas por código usando a rotina oficial."""
    if stock is None or stock.empty:
        return {"meses_giro": months, "itens": [], "grupos": [], "resumo": {}}
    analysis = build_inventory_analysis(stock, sales, months=months, abc_measure="Peso")
    if analysis.empty:
        return {"meses_giro": months, "itens": [], "grupos": [], "resumo": {}}
    start = analysis.attrs.get("start_date")
    end = analysis.attrs.get("end_date")
    items = []
    for row in analysis.to_dict("records"):
        days = row.get("Dias de estoque")
        items.append({
            "codigo": str(row.get("Produto Codigo", "")).removesuffix(".0"),
            "produto": str(row.get("Produto", "") or ""),
            "grupo": str(row.get("Grupo Produto", "Não mapeado") or "Não mapeado"),
            "saldo_kg": _number(row.get("Saldo Total", 0)),
            "reserva_kg": _number(row.get("Reserva Total", 0)),
            "disponivel_kg": _number(row.get("Estoque disponível (kg)", 0)),
            "vendas_historicas_kg": _number(row.get("Vendas históricas (kg)", 0)),
            "faturamento_historico": _number(row.get("Faturamento histórico (R$)", 0)),
            "pedidos_historicos": int(row.get("Pedidos históricos", 0) or 0),
            "venda_media_diaria_kg": _number(row.get("Venda média diária (kg)", 0)),
            "dias_estoque": _number(days) if pd.notna(days) else None,
            "giro": str(row.get("Giro", "Sem giro")),
            "curva_abc": str(row.get("Curva ABC", "C")),
            "cobertura": str(row.get("Cobertura", "Sem estoque e sem giro")),
            "excesso_potencial_kg": _number(row.get("Excesso potencial (kg)", 0)),
            "reposicao_30_dias_kg": _number(row.get("Reposição para 30 dias (kg)", 0)),
        })
    coverage = analysis["Cobertura"].value_counts().to_dict()
    valid_days = pd.to_numeric(analysis["Dias de estoque"], errors="coerce").dropna()
    group_rows = []
    for group, frame in analysis.groupby("Grupo Produto", dropna=False):
        group_rows.append({
            "nome": str(group),
            "produtos": int(len(frame)),
            "saldo_kg": _number(frame["Saldo Total"].sum()),
            "reserva_kg": _number(frame["Reserva Total"].sum()),
            "disponivel_kg": _number(frame["Estoque disponível (kg)"].sum()),
            "vendas_kg": _number(frame["Vendas históricas (kg)"].sum()),
            "alto_giro": int(frame["Giro"].eq("Alto giro").sum()),
        })
    group_rows.sort(key=lambda item: item["disponivel_kg"], reverse=True)
    return {
        "meses_giro": months,
        "periodo_giro": {
            "inicio": pd.Timestamp(start).date().isoformat() if start is not None else None,
            "fim": pd.Timestamp(end).date().isoformat() if end is not None else None,
            "dias_calendario": int(analysis.attrs.get("calendar_days", 0)),
        },
        "resumo": {
            "produtos": int(len(analysis)),
            "saldo_kg": _number(analysis["Saldo Total"].sum()),
            "reserva_kg": _number(analysis["Reserva Total"].sum()),
            "disponivel_kg": _number(analysis["Estoque disponível (kg)"].sum()),
            "produtos_alto_giro": int(analysis["Giro"].eq("Alto giro").sum()),
            "produtos_sem_giro": int(analysis["Giro"].eq("Sem giro").sum()),
            "produtos_ruptura": int(analysis["Cobertura"].eq("Ruptura").sum()),
            "dias_estoque_mediana": _number(valid_days.median()) if not valid_days.empty else None,
            "faixas_cobertura": {str(key): int(value) for key, value in coverage.items()},
        },
        "grupos": group_rows,
        "itens": items,
    }


def _load_flow():
    """Lê a trilha agregável do funil, sem publicar linhas de pedido."""
    if not os.path.exists(FLOW_PATH):
        return pd.DataFrame()
    try:
        flow = pd.read_csv(FLOW_PATH, compression="gzip", low_memory=False)
        for column in flow.columns:
            if column.startswith("Data "):
                flow[column] = pd.to_datetime(flow[column], errors="coerce")
        for column in ("Peso", "Valor"):
            if column in flow:
                flow[column] = pd.to_numeric(flow[column], errors="coerce")
        return flow
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()


def _flow_payload(flow, start, end):
    if flow.empty:
        return {"etapas": [], "prazos": [], "cobertura": 0}
    events = [
        ("Orçamentos emitidos", "Data Orçamento"),
        ("Pedidos emitidos", "Data Pedido"),
        ("Pedidos liberados", "Data Liberação"),
        ("OP emitidas", "Data Emissão OP"),
        ("OP confirmadas", "Data Confirmação OP"),
        ("Ordens de serviço", "Data OS"),
        ("Cargas montadas", "Data Montagem Carga"),
        ("Notas emitidas", "Data Emissão NF"),
        ("Saídas realizadas", "Data Saída"),
    ]
    etapas = []
    for label, column in events:
        if column not in flow:
            continue
        scoped = flow[flow[column].between(start, end, inclusive="both")]
        if scoped.empty:
            continue
        etapas.append({
            "etapa": label,
            "data": column,
            "registros": int(len(scoped)),
            "peso": _number(scoped["Peso"].sum()) if "Peso" in scoped else 0,
            "valor": _number(scoped["Valor"].sum()) if "Valor" in scoped else 0,
        })
    transitions = [
        ("Pedido → liberação", "Data Pedido", "Data Liberação"),
        ("Liberação → OS", "Data Liberação", "Data OS"),
        ("OS → montagem", "Data OS", "Data Montagem Carga"),
        ("Montagem → NF", "Data Montagem Carga", "Data Emissão NF"),
        ("NF → saída", "Data Emissão NF", "Data Saída"),
    ]
    prazos = []
    for label, origin, destination in transitions:
        if origin not in flow or destination not in flow:
            continue
        days = (flow[destination] - flow[origin]).dt.total_seconds() / 86400
        days = days[days.between(0, 365)]
        if not days.empty:
            prazos.append({"etapa": label, "dias_medianos": _number(days.median()), "amostra": int(len(days))})
    dated = flow[[column for column in flow.columns if column.startswith("Data ")]]
    coverage = dated.notna().any(axis=1).mean() if not dated.empty else 0
    return {"etapas": etapas, "prazos": prazos, "cobertura": _number(coverage)}


def _unified_snapshot(overview, commercial, funnel, flow_dates, monthly, panels):
    """Tabela agregada para a página HTML; não inclui linhas privadas da base."""
    rows = [{
        "Fonte": "Resumo do período", "Recorte": "Período atual", "Item": "Faturamento realizado",
        "Faturamento (R$)": overview.get("faturamento", 0), "Peso (kg)": overview.get("peso", 0),
        "Margem (R$)": overview.get("margem", 0), "Margem %": overview.get("margem_pct", 0),
        "Clientes": overview.get("clientes", 0), "Produtos": overview.get("produtos", 0),
    }]
    rows.extend([
        {"Fonte": "Metas e carteira", "Recorte": "Período atual", "Item": "Meta de faturamento", "Meta (R$)": commercial.get("meta_valor")},
        {"Fonte": "Metas e carteira", "Recorte": "Período atual", "Item": "Meta de peso", "Meta (kg)": commercial.get("meta_peso")},
        {"Fonte": "Metas e carteira", "Recorte": "Período atual", "Item": "Pedidos liberados", "Valor da carteira (R$)": commercial.get("pedidos_liberados_valor"), "Peso da carteira (kg)": commercial.get("pedidos_liberados_peso")},
        {"Fonte": "Metas e carteira", "Recorte": "Período atual", "Item": "A faturar", "Valor da carteira (R$)": commercial.get("pedidos_nao_faturados_valor"), "Peso da carteira (kg)": commercial.get("pedidos_nao_faturados_peso")},
    ])
    for row in funnel:
        rows.append({"Fonte": "Funil", "Recorte": row.get("tipo", "etapa").title(), "Item": row.get("etapa"), "Valor da carteira (R$)": row.get("valor"), "Peso da carteira (kg)": row.get("peso")})
    for row in flow_dates.get("etapas", []):
        rows.append({"Fonte": "Eventos por data", "Recorte": "Período atual", "Item": row.get("etapa"), "Registros": row.get("registros"), "Valor da carteira (R$)": row.get("valor"), "Peso da carteira (kg)": row.get("peso")})
    for row in flow_dates.get("prazos", []):
        rows.append({"Fonte": "Prazos do processo", "Recorte": "Mediana", "Item": row.get("etapa"), "Prazo mediano (dias)": row.get("dias_medianos"), "Registros": row.get("amostra")})
    for row in monthly:
        rows.append({"Fonte": "Evolução mensal", "Recorte": row.get("mes"), "Item": "Resultado mensal", "Faturamento (R$)": row.get("faturamento"), "Peso (kg)": row.get("peso"), "Margem (R$)": row.get("margem"), "Margem %": row.get("margem_pct")})
    for source, values in panels.items():
        for row in values:
            rows.append({"Fonte": source.title(), "Recorte": "Período atual", "Item": row.get("nome"), "Faturamento (R$)": row.get("faturamento"), "Peso (kg)": row.get("peso"), "Margem (R$)": row.get("margem"), "Margem %": row.get("margem_pct"), "Clientes": row.get("clientes"), "Produtos": row.get("produtos")})
    return rows



def _monthly_sales_payload(history, last_date, months=12):
    """Agrega vendas por mês e recortes, preservando IDs distintos para filtros."""
    start = pd.Timestamp(last_date).to_period("M").start_time - pd.DateOffset(months=max(int(months), 1) - 1)
    source = history[pd.to_datetime(history["Data"], errors="coerce").between(start, last_date, inclusive="both")].copy()
    source["Data"] = pd.to_datetime(source["Data"], errors="coerce")
    source["mes"] = source["Data"].dt.to_period("M").astype(str)
    dimensions = {"vendedor": "Vendedor", "grupo": "Grupo Produto", "segmento": "Segmento Cliente", "cidade": "Município"}
    for column in dimensions.values():
        if column not in source:
            source[column] = "Não mapeado"
        source[column] = source[column].fillna("Não mapeado").astype(str)
    if "Cod Cliente" not in source:
        source["Cod Cliente"] = ""
    if "Produto Codigo" not in source:
        source["Produto Codigo"] = source.get("Produto", "")
    if "Produto" not in source:
        source["Produto"] = source["Produto Codigo"]
    source["_cliente_id"] = source["Cod Cliente"].fillna("").astype(str).str.removesuffix(".0")
    source["_produto_id"] = source["Produto Codigo"].fillna("").astype(str).str.removesuffix(".0")
    cut_columns = ["mes", *dimensions.keys()]
    grouped = source.groupby(cut_columns, dropna=False).agg(
        faturamento=("Faturamento", "sum"),
        peso=("Peso", "sum"),
        margem=("Margem", "sum"),
        clientes_ids=("_cliente_id", lambda values: sorted(set(value for value in values if value))),
        produtos_ids=("_produto_id", lambda values: sorted(set(value for value in values if value))),
    ).reset_index()
    recortes = []
    for row in grouped.to_dict(orient="records"):
        recortes.append({
            **{key: str(row[key]) for key in cut_columns},
            "faturamento": _number(row["faturamento"]),
            "peso": _number(row["peso"]),
            "margem": _number(row["margem"]),
            "clientes_ids": row["clientes_ids"],
            "produtos_ids": row["produtos_ids"],
        })
    sku_columns = ["mes", "vendedor", "grupo", "Produto Codigo", "Produto"]
    sku_group = source.groupby(sku_columns, dropna=False).agg(
        faturamento=("Faturamento", "sum"), peso=("Peso", "sum")
    ).reset_index()
    skus = [{
        "mes": str(row["mes"]), "vendedor": str(row["vendedor"]), "grupo": str(row["grupo"]),
        "codigo": str(row["Produto Codigo"]).removesuffix(".0"), "produto": str(row["Produto"]),
        "faturamento": _number(row["faturamento"]), "peso": _number(row["peso"]),
    } for row in sku_group.to_dict(orient="records")]
    return recortes, skus


def _monthly_customer_payload(history, last_date, months=12):
    """Publica retratos da carteira no fim de cada mês para permitir filtros históricos."""
    final_month = pd.Timestamp(last_date).to_period("M")
    first_month = final_month - max(int(months), 1) + 1
    snapshots = []
    for period in pd.period_range(first_month, final_month, freq="M"):
        end = min(period.end_time.normalize(), pd.Timestamp(last_date).normalize())
        available = history[pd.to_datetime(history["Data"], errors="coerce").le(end)]
        snapshot = _customer_payload(available, end)
        snapshots.append({"mes": str(period), **snapshot})
    return snapshots


def build_payload(data, stock=None):
    data = data.dropna(subset=["Data"]).copy()
    last_date = data["Data"].max().normalize()
    month_start = last_date.replace(day=1)
    current = data[(data["Data"] >= month_start) & (data["Data"] <= last_date)]
    previous_start = month_start - pd.DateOffset(years=1)
    previous_end = last_date - pd.DateOffset(years=1)
    previous = data[(data["Data"] >= previous_start) & (data["Data"] <= previous_end)]
    current_metrics = _metrics(current)
    previous_metrics = _metrics(previous)
    current_metrics["variacao_faturamento_pct"] = _number(
        current_metrics["faturamento"] / previous_metrics["faturamento"] - 1
    ) if previous_metrics["faturamento"] else 0
    current_metrics["delta_margem_pp"] = _number(
        (current_metrics["margem_pct"] - previous_metrics["margem_pct"]) * 100
    )
    indicators = _load_indicators()
    flow = _load_flow()
    commercial = {
        "meta_valor": _number(indicators.get("meta_valor", 0)),
        "meta_peso": _number(indicators.get("meta_peso", 0)),
        "pedidos_liberados_valor": _number(indicators.get("pedidos_liberados_valor", 0)),
        "pedidos_liberados_peso": _number(indicators.get("pedidos_liberados_peso", 0)),
        "pedidos_nao_faturados_valor": _number(indicators.get("pedidos_nao_faturados_valor", 0)),
        "pedidos_nao_faturados_peso": _number(indicators.get("pedidos_nao_faturados_peso", 0)),
    }
    commercial["atingimento_valor_pct"] = _number(current_metrics["faturamento"] / commercial["meta_valor"]) if commercial["meta_valor"] else None
    commercial["atingimento_peso_pct"] = _number(current_metrics["peso"] / commercial["meta_peso"]) if commercial["meta_peso"] else None
    funnel = [
        {"etapa": "Orçamentos em aberto", "valor": _optional_number(indicators, "orcamentos_abertos_valor"), "peso": _optional_number(indicators, "orcamentos_abertos_peso"), "tipo": "comercial"},
        {"etapa": "Pedidos pendentes", "valor": _optional_number(indicators, "pedidos_pendentes_valor"), "peso": None, "tipo": "comercial"},
        {"etapa": "Liberados pelo crédito", "valor": _optional_number(indicators, "pedidos_liberados_credito_valor"), "peso": None, "tipo": "comercial"},
        {"etapa": "Aguardando OS", "valor": None, "peso": _optional_number(indicators, "aguardando_os_peso"), "tipo": "operacao"},
        {"etapa": "Aguardando kit", "valor": None, "peso": _optional_number(indicators, "aguardando_kit_peso"), "tipo": "operacao"},
        {"etapa": "Aguardando carga CIF", "valor": None, "peso": _optional_number(indicators, "aguardando_carga_cif_peso"), "tipo": "operacao"},
        {"etapa": "Aguardando carga FOB", "valor": None, "peso": _optional_number(indicators, "aguardando_carga_fob_peso"), "tipo": "operacao"},
        {"etapa": "Aguardando faturamento (total)", "valor": None, "peso": _optional_number(indicators, "aguardando_faturamento_peso"), "tipo": "operacao", "agregado": True},
        {"etapa": "Aguardando faturamento CIF", "valor": None, "peso": _optional_number(indicators, "aguardando_faturamento_cif_peso"), "tipo": "operacao"},
        {"etapa": "Aguardando faturamento FOB", "valor": None, "peso": _optional_number(indicators, "aguardando_faturamento_fob_peso"), "tipo": "operacao"},
        {"etapa": "Faturado no período", "valor": _optional_number(indicators, "pedidos_faturados_valor") if _optional_number(indicators, "pedidos_faturados_valor") is not None else current_metrics["faturamento"], "peso": current_metrics["peso"], "tipo": "resultado"},
    ]

    monthly = data[data["Data"] >= month_start - pd.DateOffset(months=11)].copy()
    monthly["mes"] = monthly["Data"].dt.to_period("M").astype(str)
    monthly = monthly.groupby("mes", as_index=False).agg(
        faturamento=("Faturamento", "sum"), peso=("Peso", "sum"), margem=("Margem", "sum")
    )
    monthly["margem_pct"] = monthly["margem"] / monthly["faturamento"].replace(0, pd.NA)
    monthly_source = data[data["Data"] >= month_start - pd.DateOffset(months=11)].copy()
    monthly_source["mes"] = monthly_source["Data"].dt.to_period("M").astype(str)
    monthly_ids = monthly_source.groupby("mes").agg(
        clientes_ids=("Cod Cliente", lambda values: sorted(set(values.dropna().astype(str)))),
        produtos_ids=("Produto Codigo", lambda values: sorted(set(values.dropna().astype(str)))),
    ).reset_index()
    monthly = monthly.merge(monthly_ids, on="mes", how="left")
    monthly_records = []
    for item in monthly.to_dict(orient="records"):
        monthly_records.append({
            key: (value if key in ("mes", "clientes_ids", "produtos_ids") else _number(value))
            for key, value in item.items()
        })
    monthly_recortes, monthly_skus = _monthly_sales_payload(data, last_date, months=12)
    monthly_customers = _monthly_customer_payload(data, last_date, months=12)
    panels = {
        "segmentos": _breakdown(current, "Segmento Cliente"),
        "produtos": _breakdown(current, "Grupo Produto"),
        "vendedores": _breakdown(current, "Vendedor"),
        "cidades": _breakdown(current, "Município"),
    }
    flow_dates = _flow_payload(flow, month_start, last_date)
    customer_status = _customer_payload(data, last_date)
    inventory = _inventory_payload(stock, data, months=3)
    return {
        "versao": 3,
        "atualizado_em": datetime.now().astimezone().isoformat(),
        "periodo": {"inicio": month_start.date().isoformat(), "fim": last_date.date().isoformat()},
        "overview": current_metrics,
        "metas_e_pedidos": commercial,
        "funil_acompanhamento": funnel,
        "rastreabilidade_datas": flow_dates,
        "mensal": monthly_records,
        "mensal_recortes": monthly_recortes,
        "mensal_skus": monthly_skus,
        "paineis": panels,
        "clientes_carteira": customer_status,
        "clientes_mensais": monthly_customers,
        "estoque": inventory,
        "consulta_unificada": _unified_snapshot(current_metrics, commercial, funnel, flow_dates, monthly_records, panels),
    }


def main():
    payload = build_payload(load_data(), load_stock())
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not upload_bytes(content, OUTPUT_PATH, "application/json; charset=utf-8"):
        raise RuntimeError("Supabase não está configurado para publicar o resumo HTML.")
    print(f"Resumo HTML publicado em {OUTPUT_PATH} ({len(content):,} bytes).")


if __name__ == "__main__":
    main()

