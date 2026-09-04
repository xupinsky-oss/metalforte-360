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

    monthly = data[data["Data"] >= month_start - pd.DateOffset(months=11)].copy()
    monthly["mes"] = monthly["Data"].dt.to_period("M").astype(str)
    monthly = monthly.groupby("mes", as_index=False).agg(
        faturamento=("Faturamento", "sum"), peso=("Peso", "sum"), margem=("Margem", "sum")
    )
    monthly["margem_pct"] = monthly["margem"] / monthly["faturamento"].replace(0, pd.NA)
    monthly_records = [{key: (_number(value) if key != "mes" else value) for key, value in item.items()}
                       for item in monthly.to_dict(orient="records")]
    return {
        "versao": 1,
        "atualizado_em": datetime.now().astimezone().isoformat(),
        "periodo": {"inicio": month_start.date().isoformat(), "fim": last_date.date().isoformat()},
        "overview": current_metrics,
        "mensal": monthly_records,
        "paineis": {
            "segmentos": _breakdown(current, "Segmento Cliente"),
            "produtos": _breakdown(current, "Grupo Produto"),
            "vendedores": _breakdown(current, "Vendedor"),
            "cidades": _breakdown(current, "Município"),
        },
    }


def main():
    payload = build_payload(load_data())
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not upload_bytes(content, OUTPUT_PATH, "application/json; charset=utf-8"):
        raise RuntimeError("Supabase não está configurado para publicar o resumo HTML.")
    print(f"Resumo HTML publicado em {OUTPUT_PATH} ({len(content):,} bytes).")


if __name__ == "__main__":
    main()
