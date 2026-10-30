"""Transformações comerciais reutilizadas pelas páginas do painel.

As funções deste módulo não conhecem Streamlit. Isso mantém os cálculos
testáveis e garante que cartões, gráficos e tabelas usem a mesma regra.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def safe_div(numerator, denominator):
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def reference_period(history, start_date, end_date, mode="period"):
    """Retorna um intervalo comparável usando a mesma duração inclusiva."""
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if mode == "month":
        ref_start = start - pd.DateOffset(months=1)
        ref_end = end - pd.DateOffset(months=1)
    elif mode == "year":
        ref_start = start - pd.DateOffset(years=1)
        ref_end = end - pd.DateOffset(years=1)
    else:
        days = (end - start).days + 1
        ref_end = start - pd.Timedelta(days=1)
        ref_start = ref_end - pd.Timedelta(days=days - 1)
    data = history[
        (history["Data"] >= ref_start)
        & (history["Data"] < ref_end + pd.Timedelta(days=1))
    ]
    return data, ref_start, ref_end


def commercial_metrics(data):
    """Medidas oficiais para qualquer recorte comercial."""
    if data.empty:
        return {
            "revenue": 0.0, "weight": 0.0, "margin": 0.0,
            "margin_pct": 0.0, "price_kg": 0.0, "positive_clients": 0,
            "product_mix": 0, "orders": 0, "ticket": 0.0,
        }
    revenue = float(data["Faturamento"].sum())
    weight = float(data["Peso"].sum())
    margin = float(data["Margem"].sum())
    orders = int(data["NF"].nunique()) if "NF" in data else len(data)
    positive = int(
        (data.groupby("Cliente", dropna=False)["Faturamento"].sum() > 0).sum()
    )
    return {
        "revenue": revenue,
        "weight": weight,
        "margin": margin,
        "margin_pct": safe_div(margin, revenue),
        "price_kg": safe_div(revenue, weight),
        "positive_clients": positive,
        "product_mix": int(data["Produto"].nunique()),
        "orders": orders,
        "ticket": safe_div(revenue, orders),
    }


def _entity_summary(data, dimension, suffix):
    columns = [
        dimension, f"Faturamento {suffix}", f"KG {suffix}",
        f"Margem {suffix}", f"Pedidos {suffix}", f"Mix {suffix}",
    ]
    if data.empty or dimension not in data:
        return pd.DataFrame(columns=columns)
    result = data.groupby(dimension, dropna=False).agg(**{
        f"Faturamento {suffix}": ("Faturamento", "sum"),
        f"KG {suffix}": ("Peso", "sum"),
        f"Margem {suffix}": ("Margem", "sum"),
        f"Pedidos {suffix}": ("NF", "nunique"),
        f"Mix {suffix}": ("Produto", "nunique"),
    }).reset_index()
    return result


def entity_comparison(current, reference, dimension):
    """Compara entidades com faturamento, KG, margem, preço e mix."""
    result = _entity_summary(current, dimension, "atual").merge(
        _entity_summary(reference, dimension, "referência"),
        on=dimension, how="outer",
    )
    if result.empty:
        return result
    numeric = [column for column in result if column != dimension]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    for suffix in ("atual", "referência"):
        result[f"Margem % {suffix}"] = (
            result[f"Margem {suffix}"]
            / result[f"Faturamento {suffix}"].replace(0, np.nan)
        )
        result[f"Preço médio {suffix}"] = (
            result[f"Faturamento {suffix}"]
            / result[f"KG {suffix}"].replace(0, np.nan)
        )
    result["Δ Faturamento"] = result["Faturamento atual"] - result["Faturamento referência"]
    result["Variação faturamento %"] = (
        result["Δ Faturamento"]
        / result["Faturamento referência"].replace(0, np.nan)
    )
    result["Δ KG"] = result["KG atual"] - result["KG referência"]
    result["Δ Margem p.p."] = (
        result["Margem % atual"] - result["Margem % referência"]
    ) * 100
    result["Δ Preço médio %"] = (
        result["Preço médio atual"]
        / result["Preço médio referência"].replace(0, np.nan) - 1
    )
    result["Situação"] = np.select(
        [
            (result["Faturamento atual"] == 0) & (result["Faturamento referência"] > 0),
            (result["Faturamento referência"] == 0) & (result["Faturamento atual"] > 0),
            result["Variação faturamento %"] <= -0.20,
            result["Variação faturamento %"] >= 0.20,
        ],
        ["Sem compra", "Novo", "Queda", "Crescimento"],
        default="Estável",
    )
    return result.sort_values("Faturamento atual", ascending=False)


def customer_three_month_trend(history, end_date):
    """Compara faturamento por cliente nos últimos 3 meses com os 3 anteriores.

    As janelas são intervalos móveis inclusivos ancorados na data final, não
    meses-calendário completos. Isso permite analisar períodos parciais sem
    trazer dias posteriores à seleção.
    """
    columns = [
        "Cliente", "Faturamento últimos 3m", "Faturamento 3m anteriores",
        "Variação faturamento 3m %", "Tendência 3m",
    ]
    if history.empty or not {"Data", "Cliente", "Faturamento"}.issubset(history.columns):
        return pd.DataFrame(columns=columns)

    end = pd.Timestamp(end_date).normalize()
    recent_start = end - pd.DateOffset(months=3) + pd.Timedelta(days=1)
    window_days = (end - recent_start).days + 1
    prior_end = recent_start - pd.Timedelta(days=1)
    prior_start = prior_end - pd.Timedelta(days=window_days - 1)
    source = history[["Data", "Cliente", "Faturamento"]].copy()
    source["Data"] = pd.to_datetime(source["Data"], errors="coerce")
    source["Faturamento"] = pd.to_numeric(source["Faturamento"], errors="coerce").fillna(0)
    source = source[source["Data"].notna() & source["Data"].lt(end + pd.Timedelta(days=1))].copy()
    if source.empty:
        return pd.DataFrame(columns=columns)

    universe = source[["Cliente"]].dropna().drop_duplicates()
    recent = source[source["Data"].between(recent_start, end + pd.Timedelta(days=1), inclusive="left")]
    prior = source[source["Data"].between(prior_start, prior_end + pd.Timedelta(days=1), inclusive="left")]
    recent = recent.groupby("Cliente", dropna=False)["Faturamento"].sum().rename("Faturamento últimos 3m")
    prior = prior.groupby("Cliente", dropna=False)["Faturamento"].sum().rename("Faturamento 3m anteriores")
    result = universe.merge(recent, on="Cliente", how="left").merge(prior, on="Cliente", how="left")
    for column in columns[1:3]:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    baseline = result["Faturamento 3m anteriores"]
    latest = result["Faturamento últimos 3m"]
    result["Variação faturamento 3m %"] = (latest - baseline).div(baseline.where(baseline.gt(0)))
    result["Tendência 3m"] = np.select(
        [
            baseline.gt(0) & latest.le(0),
            baseline.gt(0) & result["Variação faturamento 3m %"].le(-0.20),
            baseline.gt(0) & result["Variação faturamento 3m %"].ge(0.20),
            baseline.gt(0),
            baseline.le(0) & latest.gt(0),
        ],
        ["Parou recentemente", "Queda 3m", "Alta 3m", "Estável 3m", "Entrada recente"],
        default="Sem faturamento recente",
    )
    return result[columns]


def customer_direction_classification(annual_change, recent_change, recent_trend):
    """Combina a leitura anual com o momentum recente sem ocultar divergências."""
    annual = pd.to_numeric(annual_change, errors="coerce")
    recent = pd.to_numeric(recent_change, errors="coerce")
    trend = pd.Series(recent_trend, index=annual.index).fillna("").astype(str)
    annual_down = annual.le(-0.20)
    annual_up = annual.ge(0.20)
    recent_down = recent.le(-0.20) | trend.eq("Parou recentemente")
    recent_up = recent.ge(0.20) | trend.eq("Entrada recente")
    annual_missing = annual.isna()
    recent_missing = trend.eq("Sem faturamento recente")
    return pd.Series(
        np.select(
            [
                annual_down & recent_down,
                annual_down & recent_up,
                annual_down & recent_missing,
                annual_down & ~recent_down & ~recent_up & ~annual_missing,
                annual_up & recent_down,
                annual_up & recent_up,
                annual_up & recent_missing,
                recent_down & annual_missing,
                recent_up & annual_missing,
                recent_missing & annual_missing,
                recent_down,
                recent_up,
            ],
            [
                "Queda persistente", "Recuperação recente", "Queda anual · sem faturamento recente",
                "Queda anual · recente estável", "Alerta de reversão", "Crescimento consistente",
                "Alerta: sem faturamento recente", "Queda recente · sem base anual",
                "Entrada recente · sem base anual", "Sem leitura recente", "Queda recente",
                "Aceleração recente",
            ],
            default="Estável / sem alerta",
        ),
        index=annual.index,
    )


def customer_directional_signals(history, start_date, end_date):
    """Une a variação anual do período selecionado ao momentum móvel de 3 meses."""
    columns = [
        "Cliente", "Variação faturamento ano %", "Faturamento últimos 3m",
        "Faturamento 3m anteriores", "Variação faturamento 3m %", "Tendência 3m",
        "Classificação comercial",
    ]
    if history.empty or not {"Data", "Cliente", "Faturamento"}.issubset(history.columns):
        return pd.DataFrame(columns=columns)
    source = history.copy()
    source["Data"] = pd.to_datetime(source["Data"], errors="coerce")
    current = source[source["Data"].between(
        pd.Timestamp(start_date), pd.Timestamp(end_date) + pd.Timedelta(days=1), inclusive="left"
    )]
    previous_year, _, _ = reference_period(source, start_date, end_date, "year")
    annual = entity_comparison(current, previous_year, "Cliente")
    annual = annual[["Cliente", "Variação faturamento %"]].rename(
        columns={"Variação faturamento %": "Variação faturamento ano %"}
    ) if not annual.empty else pd.DataFrame(columns=columns[:2])
    recent = customer_three_month_trend(source, end_date)
    result = annual.merge(recent, on="Cliente", how="outer")
    if result.empty:
        return pd.DataFrame(columns=columns)
    result["Classificação comercial"] = customer_direction_classification(
        result["Variação faturamento ano %"],
        result["Variação faturamento 3m %"],
        result["Tendência 3m"],
    )
    return result[columns]


def customer_portfolio(current, history, start_date, end_date, reference_mode="year"):
    reference, _, _ = reference_period(history, start_date, end_date, reference_mode)
    history_until = history[history["Data"] < pd.Timestamp(end_date) + pd.Timedelta(days=1)]
    if history_until.empty or "Cliente" not in history_until:
        return pd.DataFrame()

    # A carteira e uma dimensao historica: clientes sem compra no periodo atual
    # ou na referencia continuam pertencendo ao vendedor e precisam permanecer
    # visiveis no overview. As metricas aditivas desses clientes sao zero; taxas
    # sem denominador continuam indefinidas (NaN).
    universe = history_until[["Cliente"]].dropna().drop_duplicates()
    comparison = entity_comparison(current, reference, "Cliente")
    result = universe.merge(comparison, on="Cliente", how="left")
    additive = [
        "Faturamento atual", "KG atual", "Margem atual", "Pedidos atual", "Mix atual",
        "Faturamento referência", "KG referência", "Margem referência",
        "Pedidos referência", "Mix referência", "Δ Faturamento", "Δ KG",
    ]
    for column in additive:
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    if "Situação" in result:
        result["Situação"] = result["Situação"].fillna("Sem compra no recorte")
    context_columns = {
        "Vendedor": ("Vendedor", "last"),
        "UF": ("UF", "last"),
        "Município": ("Município", "last"),
        "Última compra": ("Data", "max"),
    }
    if "Canal" in history_until:
        context_columns["Canal"] = ("Canal", "last")
    if "Cluster PIVOT" in history_until:
        context_columns["Cluster PIVOT"] = ("Cluster PIVOT", "last")
    context = history_until.sort_values("Data").groupby("Cliente", dropna=False).agg(
        **context_columns
    ).reset_index()
    result = result.merge(context, on="Cliente", how="left")
    result["Dias sem comprar"] = (
        pd.Timestamp(end_date).normalize() - result["Última compra"].dt.normalize()
    ).dt.days.clip(lower=0)
    result["Potencial de recuperação"] = result["Faturamento referência"].sub(
        result["Faturamento atual"]
    ).clip(lower=0)
    return result.sort_values(
        ["Potencial de recuperação", "Faturamento atual"], ascending=[False, False]
    )


def purchase_seasonality(history, end_date, clients=None, months=12):
    """Matriz cliente x mês e cadência histórica de compra."""
    end = pd.Timestamp(end_date).to_period("M").end_time.normalize()
    start = (end.to_period("M") - (months - 1)).start_time
    history_until = history[history["Data"] <= end].copy()
    if clients:
        history_until = history_until[history_until["Cliente"].astype(str).isin(set(map(str, clients)))]
    history_until["Cliente"] = history_until["Cliente"].astype(str)
    universe = sorted(history_until["Cliente"].dropna().astype(str).unique().tolist())
    source = history_until[history_until["Data"] >= start].copy()
    month_index = pd.date_range(start=start, end=end, freq="MS")
    if not universe:
        return pd.DataFrame(), pd.DataFrame()
    if source.empty:
        matrix = pd.DataFrame(0.0, index=universe, columns=month_index)
    else:
        source["Mês"] = source["Data"].dt.to_period("M").dt.to_timestamp()
        matrix = source.groupby(["Cliente", "Mês"])["Faturamento"].sum().unstack(fill_value=0)
        matrix = matrix.reindex(index=universe, columns=month_index, fill_value=0)
    matrix.columns = [column.strftime("%m/%Y") for column in matrix.columns]
    purchases = history_until[history_until["Faturamento"] > 0].groupby("Cliente")["Data"].apply(
        lambda values: sorted(pd.Series(values).dt.normalize().drop_duplicates().tolist())
    )
    rows = []
    for client in universe:
        dates = purchases.get(client, [])
        intervals = (
            pd.Series(pd.to_datetime(dates)).diff().dropna().dt.days
            if len(dates) > 1 else pd.Series(dtype="float64")
        )
        cadence = float(intervals.median()) if not intervals.empty else np.nan
        last = max(dates) if dates else pd.NaT
        days_since = int((pd.Timestamp(end_date).normalize() - last).days) if pd.notna(last) else np.nan
        rows.append({
            "Cliente": client,
            "Meses ativos (12m)": int((matrix.loc[client] > 0).sum()),
            "Última compra": last,
            "Dias sem comprar": days_since,
            "Cadência mediana (dias)": cadence,
            "Janela vencida": bool(pd.notna(cadence) and cadence >= 7 and days_since > cadence * 1.25),
        })
    return matrix, pd.DataFrame(rows)


def product_curve(current):
    result = entity_comparison(current, current.iloc[0:0], "Produto")
    if result.empty:
        return result
    positive = result["Faturamento atual"].clip(lower=0)
    total = positive.sum()
    result = result.sort_values("Faturamento atual", ascending=False)
    result["Participação %"] = positive / total if total else 0
    result["Participação acumulada %"] = result["Participação %"].cumsum()
    prior_share = result["Participação acumulada %"] - result["Participação %"]
    result["Curva"] = np.select(
        [prior_share < 0.70, prior_share < 0.90],
        ["A", "B"], default="C",
    )
    return result


def actionable_insights(current, history, start_date, end_date):
    """Filas de reativação, queda, sazonalidade e recuperação de mix."""
    previous_year, _, _ = reference_period(history, start_date, end_date, "year")
    clients = entity_comparison(current, previous_year, "Cliente")
    if clients.empty:
        empty = pd.DataFrame()
        return {"reactivation": empty, "declines": empty, "seasonality": empty, "mix": empty}

    context_source = history[history["Data"] <= pd.Timestamp(end_date)].sort_values("Data")
    context_columns=[column for column in (
        "Vendedor", "UF", "Data", "Cod Cliente", "Telefone", "E-mail",
    ) if column in context_source]
    context = context_source.groupby("Cliente", dropna=False)[context_columns].last().reset_index()
    context=context.rename(columns={"Data":"Última_compra"})
    clients = clients.merge(context, on="Cliente", how="left")
    signals = customer_directional_signals(history, start_date, end_date)
    clients = clients.merge(signals, on="Cliente", how="left")
    clients["Dias sem comprar"] = (
        pd.Timestamp(end_date).normalize() - clients["Última_compra"].dt.normalize()
    ).dt.days.clip(lower=0)
    clients["Potencial R$"] = clients["Faturamento referência"].sub(
        clients["Faturamento atual"]
    ).clip(lower=0)

    reactivation = clients[
        (clients["Faturamento referência"] > 0) & (clients["Faturamento atual"] <= 0)
    ].copy()
    reactivation["Ação"] = "Reativar cliente"
    reactivation = reactivation.sort_values("Potencial R$", ascending=False)

    declines = clients[
        (clients["Faturamento atual"] > 0)
        & (clients["Faturamento referência"] > 0)
        & (clients["Variação faturamento %"] <= -0.20)
    ].copy()
    declines["Ação"] = "Recuperar volume"
    declines = declines.sort_values("Potencial R$", ascending=False)

    _, cadence = purchase_seasonality(history, end_date)
    seasonality = cadence[cadence["Janela vencida"]].copy() if not cadence.empty else cadence
    if not seasonality.empty:
        seasonality = seasonality.merge(context[["Cliente", "Vendedor", "UF"]], on="Cliente", how="left")
        seasonality = seasonality.merge(
            signals[["Cliente", "Faturamento últimos 3m", "Faturamento 3m anteriores",
                     "Variação faturamento 3m %", "Tendência 3m", "Classificação comercial"]],
            on="Cliente", how="left",
        )
        value = history[
            (history["Data"] >= pd.Timestamp(end_date) - pd.DateOffset(months=12))
            & (history["Data"] <= pd.Timestamp(end_date))
        ].groupby("Cliente")["Faturamento"].sum().rename("Faturamento 12m")
        seasonality = seasonality.merge(value, on="Cliente", how="left")
        seasonality["Ação"] = "Contatar: janela de recompra vencida"
        seasonality = seasonality.sort_values("Faturamento 12m", ascending=False)

    mix = clients[
        (clients["Faturamento atual"] > 0)
        & (clients["Mix atual"] < clients["Mix referência"])
    ].copy()
    mix["Produtos a recuperar"] = mix["Mix referência"] - mix["Mix atual"]
    mix["Ação"] = "Recuperar mix histórico"
    mix = mix.sort_values(["Produtos a recuperar", "Potencial R$"], ascending=False)
    return {
        "reactivation": reactivation,
        "declines": declines,
        "seasonality": seasonality,
        "mix": mix,
    }
