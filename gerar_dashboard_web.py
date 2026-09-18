"""Gera o extrato agregado usado pelo Command Center HTML.

O arquivo não contém pedidos, notas, preços por cliente nem outras linhas da
base. Ele permanece no bucket privado e é entregue apenas pela Edge Function
para usuários autenticados no Supabase.
"""

import json
import os
from datetime import datetime

import pandas as pd

from src.cloud_storage import upload_bytes
from src.data import load_data


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


def build_payload(data):
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
    monthly_records = [{key: (_number(value) if key != "mes" else value) for key, value in item.items()}
                       for item in monthly.to_dict(orient="records")]
    panels = {
        "segmentos": _breakdown(current, "Segmento Cliente"),
        "produtos": _breakdown(current, "Grupo Produto"),
        "vendedores": _breakdown(current, "Vendedor"),
        "cidades": _breakdown(current, "Município"),
    }
    flow_dates = _flow_payload(flow, month_start, last_date)
    return {
        "versao": 1,
        "atualizado_em": datetime.now().astimezone().isoformat(),
        "periodo": {"inicio": month_start.date().isoformat(), "fim": last_date.date().isoformat()},
        "overview": current_metrics,
        "metas_e_pedidos": commercial,
        "funil_acompanhamento": funnel,
        "rastreabilidade_datas": flow_dates,
        "mensal": monthly_records,
        "paineis": panels,
        "consulta_unificada": _unified_snapshot(current_metrics, commercial, funnel, flow_dates, monthly_records, panels),
    }


def main():
    payload = build_payload(load_data())
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not upload_bytes(content, OUTPUT_PATH, "application/json; charset=utf-8"):
        raise RuntimeError("Supabase não está configurado para publicar o resumo HTML.")
    print(f"Resumo HTML publicado em {OUTPUT_PATH} ({len(content):,} bytes).")


if __name__ == "__main__":
    main()
