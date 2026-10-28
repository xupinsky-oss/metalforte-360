"""Cruzamento do estoque atual com o histórico de vendas por produto."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.product_groups import normalize_product_group


STOCK_NUMERIC_COLUMNS = [
    "Saldo BR", "Reserva BR", "Saldo Polo", "Reserva Polo", "Saldo SC",
    "Reserva SC", "Saldo Total", "Reserva Total", "Agd Estoque BR",
    "Agd Estoque POLO", "Agd Estoque SC",
]


def _product_key(series):
    return pd.to_numeric(series, errors="coerce").astype("Int64").astype("string")


def _stock_number(series):
    """Aceita número nativo e exportações pt-BR sem trocar milhar por decimal."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0.0)
    text = series.astype("string").str.replace("\u00a0", "", regex=False).str.strip()
    both = text.str.contains(".", regex=False, na=False) & text.str.contains(",", regex=False, na=False)
    comma = text.str.contains(",", regex=False, na=False) & ~both
    text.loc[both] = text.loc[both].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    text.loc[comma] = text.loc[comma].str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce").fillna(0.0)


def prepare_stock(frame):
    """Normaliza a fotografia do relatório 19745161 sem alterar seus saldos."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    aliases = {
        "Código": "Produto Codigo",
        "DescriÃ§Ã£o Produto": "Descrição Produto",
        "Descri��o Produto": "Descrição Produto",
        "Armaz�m": "Armazém",
        "C�digo": "Produto Codigo",
    }
    result = result.rename(columns={key: value for key, value in aliases.items() if key in result})
    required = {"Grupo", "Produto Codigo", "Descrição Produto", "Saldo Total", "Reserva Total"}
    missing = sorted(required.difference(result.columns))
    if missing:
        raise ValueError(f"Relatório de estoque sem colunas obrigatórias: {missing}")
    result["Produto Codigo"] = _product_key(result["Produto Codigo"])
    result["Grupo"] = result["Grupo"].map(normalize_product_group)
    for column in STOCK_NUMERIC_COLUMNS:
        if column not in result:
            result[column] = 0.0
        result[column] = _stock_number(result[column])
    result["Estoque disponível (kg)"] = result["Saldo Total"] - result["Reserva Total"]
    result["Aguardando estoque (kg)"] = result[[
        "Agd Estoque BR", "Agd Estoque POLO", "Agd Estoque SC"
    ]].sum(axis=1)
    return result.dropna(subset=["Produto Codigo"])


def _curve_abc(values):
    positive = pd.to_numeric(values, errors="coerce").fillna(0).clip(lower=0)
    total = float(positive.sum())
    if total <= 0:
        return pd.Series("C", index=values.index, dtype="string")
    cumulative_before = (positive.cumsum() - positive) / total
    curve = pd.Series("C", index=values.index, dtype="string")
    curve.loc[cumulative_before < 0.95] = "B"
    curve.loc[cumulative_before < 0.80] = "A"
    return curve


def build_inventory_analysis(stock, sales, *, months=3, abc_measure="Peso"):
    """Calcula ABC, velocidade de giro e dias de estoque no grão produto."""
    stock = prepare_stock(stock)
    if sales is None:
        sales = pd.DataFrame()
    history = sales.copy()
    if history.empty or "Data" not in history:
        end_date = pd.Timestamp.today().normalize()
        start_date = end_date - pd.DateOffset(months=months) + pd.Timedelta(days=1)
        window = history
    else:
        history["Data"] = pd.to_datetime(history["Data"], errors="coerce")
        end_date = history["Data"].max().normalize()
        start_date = end_date - pd.DateOffset(months=months) + pd.Timedelta(days=1)
        window = history[(history["Data"] >= start_date) & (history["Data"] <= end_date)].copy()
    calendar_days = max(1, int((end_date - start_date).days) + 1)

    if not window.empty:
        window["Produto Codigo"] = _product_key(window["Produto Codigo"])
        sales_by_product = window.groupby("Produto Codigo", dropna=False).agg(
            **{
                "Produto vendas": ("Produto", "first"),
                "Grupo vendas": ("Grupo Produto", "first"),
                "Subgrupo Produto": ("Subgrupo Produto", "first"),
                "Tipo Produto": ("Tipo Produto", "first"),
                "Faturamento histórico (R$)": ("Faturamento", "sum"),
                "Vendas históricas (kg)": ("Peso", "sum"),
                "Pedidos históricos": ("Pedido", "nunique"),
            }
        ).reset_index()
    else:
        sales_by_product = pd.DataFrame(columns=[
            "Produto Codigo", "Produto vendas", "Grupo vendas", "Subgrupo Produto",
            "Tipo Produto", "Faturamento histórico (R$)", "Vendas históricas (kg)",
            "Pedidos históricos",
        ])

    if stock.empty:
        stock_by_product = pd.DataFrame(columns=["Produto Codigo"])
    else:
        aggregations = {column: "sum" for column in STOCK_NUMERIC_COLUMNS}
        aggregations.update({
            "Estoque disponível (kg)": "sum",
            "Aguardando estoque (kg)": "sum",
            "Descrição Produto": "first",
            "Grupo": "first",
        })
        stock_by_product = stock.groupby("Produto Codigo", dropna=False).agg(aggregations).reset_index()

    result = stock_by_product.merge(sales_by_product, on="Produto Codigo", how="outer")
    empty_text = pd.Series(pd.NA, index=result.index, dtype="string")
    stock_product = result["Descrição Produto"] if "Descrição Produto" in result else empty_text
    sales_product = result["Produto vendas"] if "Produto vendas" in result else empty_text
    stock_group = result["Grupo"] if "Grupo" in result else empty_text
    sales_group = result["Grupo vendas"] if "Grupo vendas" in result else empty_text
    result["Produto"] = stock_product.combine_first(sales_product)
    result["Grupo Produto"] = stock_group.combine_first(sales_group)
    result["Grupo Produto"] = result["Grupo Produto"].fillna("Não mapeado").map(normalize_product_group)
    for column in (
        "Saldo Total", "Reserva Total", "Estoque disponível (kg)",
        "Aguardando estoque (kg)", "Faturamento histórico (R$)",
        "Vendas históricas (kg)", "Pedidos históricos",
    ):
        if column not in result:
            result[column] = 0.0
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)

    measure_column = "Faturamento histórico (R$)" if abc_measure == "Faturamento" else "Vendas históricas (kg)"
    result = result.sort_values(measure_column, ascending=False, kind="stable").reset_index(drop=True)
    result["Curva ABC"] = _curve_abc(result[measure_column])
    result["Giro"] = result["Curva ABC"].map({"A": "Alto giro", "B": "Giro médio", "C": "Baixo giro"})
    result.loc[result[measure_column] <= 0, "Giro"] = "Sem giro"
    result["Venda média diária (kg)"] = result["Vendas históricas (kg)"] / calendar_days
    available_positive = result["Estoque disponível (kg)"].clip(lower=0)
    result["Dias de estoque"] = available_positive / result["Venda média diária (kg)"].replace(0, np.nan)
    result["Cobertura"] = "Sem estoque e sem giro"
    has_sales = result["Venda média diária (kg)"] > 0
    result.loc[(~has_sales) & (result["Estoque disponível (kg)"] > 0), "Cobertura"] = "Sem giro"
    result.loc[has_sales & (result["Estoque disponível (kg)"] <= 0), "Cobertura"] = "Ruptura"
    positive_stock = result["Estoque disponível (kg)"] > 0
    result.loc[has_sales & positive_stock & result["Dias de estoque"].le(30), "Cobertura"] = "Baixo (≤30 dias)"
    result.loc[has_sales & positive_stock & result["Dias de estoque"].gt(30) & result["Dias de estoque"].le(90), "Cobertura"] = "Adequado (31–90 dias)"
    result.loc[has_sales & positive_stock & result["Dias de estoque"].gt(90), "Cobertura"] = "Alto (>90 dias)"
    result["Excesso potencial (kg)"] = (
        result["Estoque disponível (kg)"] - result["Venda média diária (kg)"] * 90
    ).clip(lower=0)
    result["Reposição para 30 dias (kg)"] = (
        result["Venda média diária (kg)"] * 30 - result["Estoque disponível (kg)"]
    ).clip(lower=0)
    result.attrs.update({"start_date": start_date, "end_date": end_date, "calendar_days": calendar_days})
    return result
