"""Métricas de carteira, precificação e rentabilidade comercial.

As funções deste módulo não alteram a base e preservam os valores observados.
Percentuais e preços médios são sempre recalculados a partir de seus componentes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


PRICE_EXCLUSION_PATTERN = r"TELHA|ISOT[ÉE]RM|SERRALHERIA"


def _empty_like(columns):
    return pd.DataFrame(columns=columns)


def _client_key(data):
    if "Cod Cliente" not in data:
        return data["Cliente"].astype("string").fillna("Não informado")
    code = data["Cod Cliente"].astype("string").str.strip()
    name = data["Cliente"].astype("string").fillna("Não informado")
    return code.where(code.notna() & code.ne(""), name)


def _quintile_score(values):
    """Converte uma medida crescente em nota de 1 a 5, preservando empates."""
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").fillna(0).clip(lower=0)
    if numeric.empty:
        return pd.Series(dtype="int64", index=numeric.index)
    percentile = numeric.rank(method="average", pct=True)
    return np.ceil(percentile * 5).clip(1, 5).astype(int)


def rfmv_class(total_scores):
    """Aplica as faixas comerciais D/C/B/A sobre a nota total de 0 a 20."""
    scores = pd.to_numeric(pd.Series(total_scores), errors="coerce").fillna(0).clip(0, 20)
    classes = np.select(
        [scores.le(5), scores.le(10), scores.le(15)],
        ["D", "C", "B"], default="A",
    )
    return pd.Series(classes, index=scores.index, dtype="string")


def customer_rfmv(history, end_date, *, months=12, relationship_start_year=2024):
    """Classifica clientes por relacionamento, frequência, faturamento e volume.

    ``R`` conta anos com pelo menos seis pedidos e normaliza essa permanência na
    janela disponível desde 2024. ``F``, ``M`` e ``V`` usam quintis da carteira
    nos últimos ``months`` meses. Todas as notas variam de 1 a 5.
    """
    columns = [
        "Cod Cliente", "Cliente", "Vendedor", "Segmento Cliente", "Última compra",
        "Dias sem comprar", "Anos elegíveis", "Anos disponíveis", "Pedidos 12m",
        "Faturamento 12m", "KG 12m", "Nota R", "Nota F", "Nota M", "Nota V",
        "Nota RFMV", "Classe RFMV", "Código RFMV",
    ]
    required = {"Data", "Cliente", "Faturamento", "Peso", "NF"}
    if history.empty or not required.issubset(history.columns):
        return _empty_like(columns)

    end = pd.Timestamp(end_date).normalize()
    source = history.copy()
    source["Data"] = pd.to_datetime(source["Data"], errors="coerce")
    for column in ("Faturamento", "Peso"):
        source[column] = pd.to_numeric(source[column], errors="coerce").fillna(0)
    source = source[
        source["Data"].notna() & source["Data"].le(end) & source["Faturamento"].gt(0)
    ].copy()
    if source.empty:
        return _empty_like(columns)

    source["_cliente_key"] = _client_key(source)
    source["_ano"] = source["Data"].dt.year
    source = source.sort_values(["_cliente_key", "Data"])
    latest = source.groupby("_cliente_key", dropna=False).tail(1).set_index("_cliente_key")
    last_purchase = source.groupby("_cliente_key", dropna=False)["Data"].max()

    start = end.to_period("M").start_time - pd.DateOffset(months=max(int(months), 1) - 1)
    recent = source[source["Data"].between(start, end, inclusive="both")]
    measures = recent.groupby("_cliente_key", dropna=False).agg(
        **{
            "Pedidos 12m": ("NF", "nunique"),
            "Faturamento 12m": ("Faturamento", "sum"),
            "KG 12m": ("Peso", "sum"),
        }
    )

    orders_by_year = source.groupby(["_cliente_key", "_ano"], dropna=False)["NF"].nunique()
    eligible_years = orders_by_year.ge(6).groupby(level=0).sum().astype(int)
    available_years = max(1, end.year - int(relationship_start_year) + 1)

    result = pd.DataFrame(index=latest.index)
    result["Cod Cliente"] = latest["Cod Cliente"] if "Cod Cliente" in latest else latest.index
    for column in ("Cliente", "Vendedor", "Segmento Cliente"):
        result[column] = latest[column] if column in latest else "Não informado"
    result["Última compra"] = last_purchase
    result["Dias sem comprar"] = (end - result["Última compra"].dt.normalize()).dt.days.clip(lower=0)
    result["Anos elegíveis"] = eligible_years.reindex(result.index).fillna(0).astype(int)
    result["Anos disponíveis"] = available_years
    result = result.join(measures, how="left")
    for column in ("Pedidos 12m", "Faturamento 12m", "KG 12m"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)

    relationship_ratio = result["Anos elegíveis"].clip(upper=available_years).div(available_years)
    result["Nota R"] = (1 + np.rint(relationship_ratio * 4)).clip(1, 5).astype(int)
    result["Nota F"] = _quintile_score(result["Pedidos 12m"]).to_numpy()
    result["Nota M"] = _quintile_score(result["Faturamento 12m"]).to_numpy()
    result["Nota V"] = _quintile_score(result["KG 12m"]).to_numpy()
    result["Nota RFMV"] = result[["Nota R", "Nota F", "Nota M", "Nota V"]].sum(axis=1).astype(int)
    result["Classe RFMV"] = rfmv_class(result["Nota RFMV"])
    result["Código RFMV"] = (
        "R" + result["Nota R"].astype(str)
        + "-F" + result["Nota F"].astype(str)
        + "-M" + result["Nota M"].astype(str)
        + "-V" + result["Nota V"].astype(str)
    )
    result = result.reset_index(drop=True)
    return result[columns].sort_values(["Classe RFMV", "Nota RFMV", "Faturamento 12m"], ascending=[True, False, False])


def portfolio_health(history, end_date, *, inactivity_days=180):
    """Consolida a carteira pelo vendedor da compra mais recente até ``end_date``.

    Cobertura 90d usa toda a carteira como denominador. Cliente novo é aquele cuja
    primeira compra ocorreu nos 90 dias anteriores à data final.
    """
    summary_columns = [
        "Vendedor", "Carteira total", "Cobertos 90d", "Cobertura 90d",
        "Novos", "Em risco", "Inativos", "Faturamento 12m", "Margem 12m",
        "Margem % 12m", "KG 12m", "Preço médio/kg 12m",
    ]
    detail_columns = [
        "Cod Cliente", "Cliente", "Vendedor", "Segmento Cliente", "UF", "Município",
        "Primeira compra", "Última compra", "Dias sem comprar", "Status",
        "Faturamento 12m", "KG 12m", "Margem 12m", "Margem % 12m",
        "Preço médio/kg 12m", "Pedidos 12m",
    ]
    if history.empty or "Data" not in history:
        return _empty_like(summary_columns), _empty_like(detail_columns)

    end = pd.Timestamp(end_date).normalize()
    source = history.copy()
    source["Data"] = pd.to_datetime(source["Data"], errors="coerce")
    source = source[source["Data"].notna() & source["Data"].le(end)].copy()
    source = source[pd.to_numeric(source["Faturamento"], errors="coerce").fillna(0).gt(0)]
    if source.empty:
        return _empty_like(summary_columns), _empty_like(detail_columns)

    source["_cliente_key"] = _client_key(source)
    source = source.sort_values(["_cliente_key", "Data"])
    latest = source.groupby("_cliente_key", dropna=False).tail(1).set_index("_cliente_key")
    first = source.groupby("_cliente_key", dropna=False)["Data"].min()
    last = source.groupby("_cliente_key", dropna=False)["Data"].max()

    start_12m = end - pd.DateOffset(months=12) + pd.Timedelta(days=1)
    recent = source[source["Data"].ge(start_12m)].copy()
    aggregated = recent.groupby("_cliente_key", dropna=False).agg(
        **{
            "Faturamento 12m": ("Faturamento", "sum"),
            "KG 12m": ("Peso", "sum"),
            "Margem 12m": ("Margem", "sum"),
            "Pedidos 12m": ("NF", "nunique"),
        }
    )

    detail = pd.DataFrame(index=latest.index)
    detail["Cod Cliente"] = latest["Cod Cliente"] if "Cod Cliente" in latest else latest.index
    for column in ("Cliente", "Vendedor", "Segmento Cliente", "UF", "Município"):
        detail[column] = latest[column] if column in latest else "Não informado"
    detail["Primeira compra"] = first
    detail["Última compra"] = last
    detail = detail.join(aggregated, how="left")
    for column in ("Faturamento 12m", "KG 12m", "Margem 12m", "Pedidos 12m"):
        detail[column] = pd.to_numeric(detail[column], errors="coerce").fillna(0)
    detail["Dias sem comprar"] = (end - detail["Última compra"].dt.normalize()).dt.days.clip(lower=0)
    is_new = detail["Primeira compra"].ge(end - pd.Timedelta(days=89))
    detail["Status"] = np.select(
        [is_new, detail["Dias sem comprar"].le(90), detail["Dias sem comprar"].le(inactivity_days)],
        ["Novo", "Ativo", "Em risco"], default="Inativo",
    )
    detail["Margem % 12m"] = detail["Margem 12m"].div(detail["Faturamento 12m"].replace(0, np.nan))
    detail["Preço médio/kg 12m"] = detail["Faturamento 12m"].div(detail["KG 12m"].replace(0, np.nan))
    detail = detail.reset_index(drop=True)

    rows = []
    for seller, frame in detail.groupby("Vendedor", dropna=False):
        revenue = float(frame["Faturamento 12m"].sum())
        margin = float(frame["Margem 12m"].sum())
        weight = float(frame["KG 12m"].sum())
        covered = int(frame["Dias sem comprar"].le(90).sum())
        total = int(len(frame))
        rows.append({
            "Vendedor": seller,
            "Carteira total": total,
            "Cobertos 90d": covered,
            "Cobertura 90d": covered / total if total else np.nan,
            "Novos": int(frame["Status"].eq("Novo").sum()),
            "Em risco": int(frame["Status"].eq("Em risco").sum()),
            "Inativos": int(frame["Status"].eq("Inativo").sum()),
            "Faturamento 12m": revenue,
            "Margem 12m": margin,
            "Margem % 12m": margin / revenue if revenue else np.nan,
            "KG 12m": weight,
            "Preço médio/kg 12m": revenue / weight if weight else np.nan,
        })
    summary = pd.DataFrame(rows, columns=summary_columns).sort_values("Faturamento 12m", ascending=False)
    detail = detail[detail_columns].sort_values(["Status", "Faturamento 12m"], ascending=[True, False])
    return summary, detail


def weighted_quantile(values, weights, quantile):
    """Percentil ponderado determinístico, ignorando pesos inválidos ou não positivos."""
    values = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    weights = pd.to_numeric(pd.Series(weights), errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return np.nan
    values, weights = values[valid], weights[valid]
    order = np.argsort(values, kind="mergesort")
    values, weights = values[order], weights[order]
    midpoint = (np.cumsum(weights) - 0.5 * weights) / weights.sum()
    return float(np.interp(float(quantile), midpoint, values))


def _comparable_price_rows(history, end_date, months, *, exclude_unreliable=True):
    end = pd.Timestamp(end_date).normalize()
    start = end.to_period("M").start_time - pd.DateOffset(months=max(int(months), 1) - 1)
    frame = history.copy()
    frame["Data"] = pd.to_datetime(frame["Data"], errors="coerce")
    frame = frame[frame["Data"].between(start, end, inclusive="both")].copy()
    frame["Faturamento"] = pd.to_numeric(frame["Faturamento"], errors="coerce")
    frame["Peso"] = pd.to_numeric(frame["Peso"], errors="coerce")
    frame = frame[frame["Faturamento"].gt(0) & frame["Peso"].gt(0)].copy()
    if exclude_unreliable and not frame.empty:
        text_columns = [column for column in ("Produto", "Grupo Produto", "Subgrupo Produto", "Tipo Produto") if column in frame]
        if text_columns:
            combined = frame[text_columns].fillna("").astype(str).agg(" ".join, axis=1).str.upper()
            frame = frame[~combined.str.contains(PRICE_EXCLUSION_PATTERN, regex=True, na=False)].copy()
    frame["_preco_kg"] = frame["Faturamento"].div(frame["Peso"].replace(0, np.nan))
    return frame, start, end


def price_reference_matrix(history, end_date, product_dimension, *, months=12, exclude_unreliable=True):
    """Referência de preço por dimensão de produto e segmento de cliente."""
    columns = [
        product_dimension, "Segmento Cliente", "Faturamento", "KG", "Margem %",
        "Preço médio/kg", "P25 preço/kg", "Preço referência/kg", "P75 preço/kg",
        "Preço referência 3m/kg", "Clientes", "Pedidos", "Amostra confiável",
    ]
    if history.empty or product_dimension not in history or "Segmento Cliente" not in history:
        return _empty_like(columns)
    frame, _, _ = _comparable_price_rows(history, end_date, months, exclude_unreliable=exclude_unreliable)
    short, _, _ = _comparable_price_rows(history, end_date, 3, exclude_unreliable=exclude_unreliable)
    if frame.empty:
        return _empty_like(columns)

    group_columns = [product_dimension, "Segmento Cliente"]
    short_reference = {}
    if not short.empty:
        for key, group in short.groupby(group_columns, dropna=False):
            short_reference[key] = weighted_quantile(group["_preco_kg"], group["Peso"], 0.50)

    rows = []
    for key, group in frame.groupby(group_columns, dropna=False):
        revenue = float(group["Faturamento"].sum())
        weight = float(group["Peso"].sum())
        margin = float(pd.to_numeric(group["Margem"], errors="coerce").fillna(0).sum())
        clients = int(group["Cliente"].nunique())
        invoices = int(group["NF"].nunique())
        rows.append({
            product_dimension: key[0],
            "Segmento Cliente": key[1],
            "Faturamento": revenue,
            "KG": weight,
            "Margem %": margin / revenue if revenue else np.nan,
            "Preço médio/kg": revenue / weight if weight else np.nan,
            "P25 preço/kg": weighted_quantile(group["_preco_kg"], group["Peso"], 0.25),
            "Preço referência/kg": weighted_quantile(group["_preco_kg"], group["Peso"], 0.50),
            "P75 preço/kg": weighted_quantile(group["_preco_kg"], group["Peso"], 0.75),
            "Preço referência 3m/kg": short_reference.get(key, np.nan),
            "Clientes": clients,
            "Pedidos": invoices,
            "Amostra confiável": "Sim" if clients >= 3 and invoices >= 5 else "Amostra pequena",
        })
    return pd.DataFrame(rows, columns=columns).sort_values("Faturamento", ascending=False)


def margin_volume_quadrants(data, dimension, *, margin_floor=0.14):
    """Agrupa entidades e classifica os quadrantes de volume e margem."""
    columns = [
        dimension, "Faturamento", "Volume t", "Margem R$", "Margem %",
        "Preço médio/kg", "Clientes", "Pedidos", "Quadrante",
    ]
    if data.empty or dimension not in data:
        return _empty_like(columns), np.nan
    frame = data.copy()
    for column in ("Faturamento", "Peso", "Margem"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    grouped = frame.groupby(dimension, dropna=False).agg(
        **{
            "Faturamento": ("Faturamento", "sum"),
            "Peso": ("Peso", "sum"),
            "Margem R$": ("Margem", "sum"),
            "Clientes": ("Cliente", "nunique"),
            "Pedidos": ("NF", "nunique"),
        }
    ).reset_index()
    grouped = grouped[grouped["Faturamento"].gt(0) & grouped["Peso"].gt(0)].copy()
    if grouped.empty:
        return _empty_like(columns), np.nan
    grouped["Volume t"] = grouped["Peso"] / 1000
    grouped["Margem %"] = grouped["Margem R$"].div(grouped["Faturamento"].replace(0, np.nan))
    grouped["Preço médio/kg"] = grouped["Faturamento"].div(grouped["Peso"].replace(0, np.nan))
    volume_cut = float(grouped["Volume t"].median())
    high_volume = grouped["Volume t"].ge(volume_cut)
    healthy_margin = grouped["Margem %"].ge(float(margin_floor))
    grouped["Quadrante"] = np.select(
        [high_volume & healthy_margin, ~high_volume & healthy_margin, high_volume & ~healthy_margin],
        ["Proteger", "Desenvolver", "Reprecificar"], default="Rever",
    )
    return grouped[columns].sort_values("Faturamento", ascending=False), volume_cut


def iqr_inlier_mask(series, *, log_scale=False, whisker=1.5):
    """Marca valores dentro da faixa interquartil sem remover a fonte original."""
    values = pd.to_numeric(series, errors="coerce")
    transformed = np.log10(values.where(values > 0)) if log_scale else values
    finite = transformed.replace([np.inf, -np.inf], np.nan).notna()
    sample = transformed[finite]
    if len(sample) < 8:
        return finite
    q1, q3 = sample.quantile([0.25, 0.75])
    spread = q3 - q1
    if not np.isfinite(spread) or spread <= 0:
        return finite
    lower, upper = q1 - whisker * spread, q3 + whisker * spread
    return finite & transformed.between(lower, upper, inclusive="both")
