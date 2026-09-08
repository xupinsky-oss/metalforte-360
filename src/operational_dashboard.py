"""Painel comercial simplificado, comparável e controlado por permissões."""

import html

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.analytics import group_metrics, metrics
from src.assistant import answer
from src.auth import render_user_admin
from src.commercial_intelligence import (
    actionable_insights,
    commercial_metrics,
    customer_portfolio,
    entity_comparison,
    product_curve,
    purchase_seasonality,
    reference_period,
)


def _polish_chart(chart, *, height=380, x_title=None, y_title=None):
    chart.update_layout(
        height=height, template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Arial, sans-serif", size=12, color="#243447"),
        title=dict(font=dict(size=16, color="#243447"), x=0, xanchor="left"),
        margin=dict(l=18, r=58, t=58, b=42), hoverlabel=dict(bgcolor="#243447", font_color="white"),
    )
    if x_title is not None:
        chart.update_xaxes(title=x_title)
    if y_title is not None:
        chart.update_yaxes(title=y_title)
    chart.update_xaxes(showgrid=True, gridcolor="#E5E7EB", zeroline=False)
    chart.update_yaxes(showgrid=False, zeroline=False)
    return chart


def _positive_clients(data):
    """Clientes com faturamento líquido positivo no período."""
    if data.empty:
        return 0
    return int((data.groupby("Cliente", dropna=False)["Faturamento"].sum() > 0).sum())


def _period_metrics(data):
    result = metrics(data)
    result["positive_clients"] = _positive_clients(data)
    return result


def _shifted_period(history, start_date, end_date, *, months=0, years=0):
    offset = pd.DateOffset(months=months, years=years)
    start = pd.Timestamp(start_date) - offset
    end = pd.Timestamp(end_date) - offset
    return history[(history["Data"] >= start) & (history["Data"] < end + pd.Timedelta(days=1))]


def _relative(current, reference):
    if not reference or pd.isna(reference):
        return None
    return current / reference - 1


def _comparison_text(value, *, points=False):
    if value is None or pd.isna(value):
        return "sem base"
    suffix = " p.p." if points else "%"
    number = value if points else value * 100
    return f"{number:+.2f}{suffix}".replace(".", ",")


def _metric_card(label, value, month_change, year_change, *, points=False):
    month_class = "up" if (month_change or 0) >= 0 else "down"
    year_class = "up" if (year_change or 0) >= 0 else "down"
    st.markdown(
        f"""
        <div class="mf-kpi">
          <div class="mf-kpi-label">{html.escape(label)}</div>
          <div class="mf-kpi-value">{html.escape(value)}</div>
          <div class="mf-kpi-compare"><span class="{month_class}">Mês ant. {_comparison_text(month_change, points=points)}</span></div>
          <div class="mf-kpi-compare"><span class="{year_class}">Ano ant. {_comparison_text(year_change, points=points)}</span></div>
        </div>
        """, unsafe_allow_html=True,
    )


def _monthly_summary(data):
    if data.empty:
        return pd.DataFrame()
    source = data.dropna(subset=["Data"]).copy()
    source["Mês"] = source["Data"].dt.to_period("M").dt.to_timestamp()
    totals = source.groupby("Mês", as_index=False).agg(
        Faturamento=("Faturamento", "sum"), Peso=("Peso", "sum"), Margem=("Margem", "sum")
    )
    clients = source.groupby(["Mês", "Cliente"], dropna=False)["Faturamento"].sum().gt(0).groupby(level=0).sum()
    totals["Preço médio/kg"] = totals["Faturamento"] / totals["Peso"].replace(0, pd.NA)
    totals["Margem %"] = totals["Margem"] / totals["Faturamento"].replace(0, pd.NA)
    totals["Clientes positivados"] = totals["Mês"].map(clients).fillna(0).astype(int)
    totals["Mês referência"] = totals["Mês"].dt.strftime("%m/%Y")
    return totals.sort_values("Mês")


def _summary(data, dimension, total):
    if data.empty or dimension not in data.columns:
        return pd.DataFrame()
    view = group_metrics(data, dimension).rename(columns={
        "faturamento": "Faturamento", "margem": "Margem", "margem_pct": "Margem %",
        "peso": "Peso (kg)", "clientes": "Clientes positivados", "produtos": "Produtos",
        "preco_kg": "Preço médio/kg", "nfs": "Notas fiscais",
    })
    positive = data.groupby([dimension, "Cliente"], dropna=False)["Faturamento"].sum().gt(0).groupby(level=0).sum()
    view["Clientes positivados"] = view[dimension].map(positive).fillna(0).astype(int)
    view["Participação %"] = view["Faturamento"] / total if total else 0
    return view.sort_values("Faturamento", ascending=False)


def _compact_bar(view, dimension, title, limit=10):
    ranked = view.head(limit).sort_values("Faturamento")
    chart = px.bar(
        ranked, x="Faturamento", y=dimension, orientation="h", title=title,
        color_discrete_sequence=["#F36A2D"],
        hover_data={"Preço médio/kg": ":.2f", "Margem %": ":.2%", "Clientes positivados": ":,.0f"},
    )
    chart.update_traces(marker_line_width=0)
    return _polish_chart(chart, height=max(330, 31 * len(ranked) + 100), x_title="Faturamento (R$)", y_title="")


def _command_center(data, history, start_date, end_date, last_load, brl, brl2, pct, show_chart, show_table):
    st.markdown("""
    <style>
    .mf-kpi{background:#fff;border:1px solid #DCE3EC;border-radius:12px;padding:1rem;min-height:154px;box-shadow:0 3px 14px rgba(23,32,51,.05)}
    .mf-kpi-label{font-size:.86rem;font-weight:700;color:#52647A}.mf-kpi-value{font-size:1.65rem;font-weight:800;color:#172033;margin:.3rem 0 .55rem}
    .mf-kpi-compare{font-size:.79rem;line-height:1.45}.mf-kpi-compare .up{color:#177245}.mf-kpi-compare .down{color:#B33A2B}
    </style>
    """, unsafe_allow_html=True)
    st.subheader("Visão executiva")
    st.caption(
        f"{pd.Timestamp(start_date).strftime('%d/%m/%Y')} a {pd.Timestamp(end_date).strftime('%d/%m/%Y')} • "
        f"comparações usam o mesmo intervalo deslocado em 1 mês e 1 ano • carga: {last_load}"
    )
    current = _period_metrics(data)
    prior_month = _period_metrics(_shifted_period(history, start_date, end_date, months=1))
    prior_year = _period_metrics(_shifted_period(history, start_date, end_date, years=1))

    cards = st.columns(5)
    definitions = [
        ("Faturamento", brl(current["revenue"]), "revenue", False),
        ("Preço médio/kg", brl2(current["price_kg"]), "price_kg", False),
        ("Margem %", pct(current["margin_pct"]), "margin_pct", True),
        ("Clientes positivados", f"{current['positive_clients']:,}".replace(",", "."), "positive_clients", False),
        ("Peso faturado", f"{current['weight']:,.0f} kg".replace(",", "."), "weight", False),
    ]
    for column, (label, value, key, points) in zip(cards, definitions):
        if points:
            mom = (current[key] - prior_month[key]) * 100
            yoy = (current[key] - prior_year[key]) * 100
        else:
            mom = _relative(current[key], prior_month[key])
            yoy = _relative(current[key], prior_year[key])
        with column:
            _metric_card(label, value, mom, yoy, points=points)

    st.markdown("### Tendência mensal")
    monthly_start = pd.Timestamp(end_date).to_period("M").start_time - pd.DateOffset(months=11)
    monthly = _monthly_summary(history[(history["Data"] >= monthly_start) & (history["Data"] < pd.Timestamp(end_date) + pd.Timedelta(days=1))])
    if monthly.empty:
        st.info("Sem dados mensais para o período.")
    else:
        selected = st.segmented_control(
            "Indicador", ["Faturamento", "Preço médio/kg", "Margem %", "Clientes positivados"],
            default="Faturamento", key="executive_trend_metric",
        )
        chart = px.line(monthly, x="Mês", y=selected, markers=True, title=f"{selected} nos últimos 12 meses")
        chart.update_traces(line=dict(color="#F36A2D", width=3), marker=dict(size=7))
        if selected == "Margem %":
            chart.update_yaxes(tickformat=".2%")
        elif selected == "Preço médio/kg":
            chart.update_yaxes(tickprefix="R$ ", tickformat=",.2f")
        elif selected == "Faturamento":
            chart.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
        _polish_chart(chart, height=370, x_title="", y_title=selected)
        chart.update_xaxes(dtick="M1", tickformat="%b/%y")
        show_chart(chart)
        with st.expander("Conferir valores mensais"):
            show_table(
                monthly[["Mês referência", "Faturamento", "Preço médio/kg", "Margem %", "Clientes positivados"]]
                .iloc[::-1], height=390, width="stretch", hide_index=True,
            )

    st.markdown("### Detalhamento")
    dimensions = [column for column in ("Vendedor", "Grupo Produto", "Segmento Cliente", "UF", "Município") if column in data.columns]
    dimension = st.selectbox("Analisar por", dimensions, key="executive_breakdown")
    view = _summary(data, dimension, current["revenue"])
    if view.empty:
        st.info("Sem informações para o detalhamento selecionado.")
    else:
        show_chart(_compact_bar(view, dimension, f"Top 10 por {dimension.lower()}"))
        with st.expander("Ver tabela do detalhamento"):
            show_table(
                view[[dimension, "Faturamento", "Participação %", "Preço médio/kg", "Margem %", "Clientes positivados"]],
                height=480, width="stretch", hide_index=True,
            )


def _daily(data, history, end_date, brl, brl2, pct, show_chart, show_table):
    st.subheader("Performance diária")
    day = pd.Timestamp(end_date)
    today = history[history["Data"].dt.normalize() == day]
    previous_dates = history.loc[history["Data"].dt.normalize() < day, "Data"].dropna()
    prior_day = previous_dates.max().normalize() if not previous_dates.empty else day - pd.Timedelta(days=1)
    prior = history[history["Data"].dt.normalize() == prior_day]
    current, before = _period_metrics(today), _period_metrics(prior)
    cards = st.columns(4)
    cards[0].metric("Faturamento", brl(current["revenue"]), _comparison_text(_relative(current["revenue"], before["revenue"])))
    cards[1].metric("Preço médio/kg", brl2(current["price_kg"]), _comparison_text(_relative(current["price_kg"], before["price_kg"])))
    cards[2].metric("Margem %", pct(current["margin_pct"]), _comparison_text((current["margin_pct"] - before["margin_pct"]) * 100, points=True))
    cards[3].metric("Clientes positivados", current["positive_clients"], _comparison_text(_relative(current["positive_clients"], before["positive_clients"])))
    st.caption(f"Comparação com o último dia disponível: {prior_day.strftime('%d/%m/%Y')}.")
    daily = data.groupby(data["Data"].dt.normalize()).agg(Faturamento=("Faturamento", "sum"), Margem=("Margem", "sum")).reset_index(names="Data")
    if not daily.empty:
        chart = px.line(daily, x="Data", y="Faturamento", markers=True, title="Ritmo diário de faturamento")
        chart.update_traces(line=dict(color="#F36A2D", width=3))
        show_chart(_polish_chart(chart, x_title="", y_title="Faturamento (R$)"))
        with st.expander("Conferir fechamento diário"):
            daily["Margem %"] = daily["Margem"] / daily["Faturamento"].replace(0, pd.NA)
            show_table(daily.sort_values("Data", ascending=False), height=420, width="stretch", hide_index=True)


def _reference_selector(key):
    options = {
        "Período anterior": "period",
        "Mês anterior": "month",
        "Ano anterior": "year",
    }
    label = st.selectbox("Referência de comparação", list(options), key=key)
    return options[label], label.lower()


def _comparison_cards(current, reference, brl, brl2, pct):
    cards = st.columns(5)
    definitions = [
        ("Faturamento", brl(current["revenue"]), "revenue", False),
        ("KG faturado", f"{current['weight']:,.0f} kg".replace(",", "."), "weight", False),
        ("Margem %", pct(current["margin_pct"]), "margin_pct", True),
        ("Preço médio/kg", brl2(current["price_kg"]), "price_kg", False),
        ("Clientes positivados", f"{current['positive_clients']:,}".replace(",", "."), "positive_clients", False),
    ]
    for column, (label, value, key, points) in zip(cards, definitions):
        if points:
            delta = (current[key] - reference[key]) * 100
            shown = _comparison_text(delta, points=True)
        else:
            delta = _relative(current[key], reference[key])
            shown = _comparison_text(delta)
        column.metric(label, value, shown)


def _client_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export):
    st.subheader("Inteligência de clientes")
    available = sorted(history["Cliente"].dropna().astype(str).unique().tolist())
    c1, c2 = st.columns([1.7, 1])
    selected = c1.selectbox("Cliente", ["Todos os clientes"] + available, key="client_page_scope")
    mode, reference_label = _reference_selector("client_reference")
    current = data if selected == "Todos os clientes" else data[data["Cliente"].astype(str) == selected]
    client_history = history if selected == "Todos os clientes" else history[history["Cliente"].astype(str) == selected]
    reference, ref_start, ref_end = reference_period(client_history, start_date, end_date, mode)
    st.caption(
        f"Comparação com {reference_label}: {ref_start.strftime('%d/%m/%Y')} a {ref_end.strftime('%d/%m/%Y')}."
    )
    _comparison_cards(commercial_metrics(current), commercial_metrics(reference), brl, brl2, pct)

    if selected != "Todos os clientes":
        before_end = client_history[client_history["Data"] <= pd.Timestamp(end_date)]
        last_purchase = before_end["Data"].max() if not before_end.empty else pd.NaT
        info = st.columns(4)
        info[0].metric("Última compra", last_purchase.strftime("%d/%m/%Y") if pd.notna(last_purchase) else "—")
        info[1].metric("Dias sem comprar", int((pd.Timestamp(end_date) - last_purchase.normalize()).days) if pd.notna(last_purchase) else "—")
        info[2].metric("Mix de produtos", current["Produto"].nunique())
        info[3].metric("Pedidos", current["NF"].nunique())

    st.markdown("### Histórico e sazonalidade de compra")
    window_start = pd.Timestamp(end_date).to_period("M").start_time - pd.DateOffset(months=11)
    last_12m = client_history[(client_history["Data"] >= window_start) & (client_history["Data"] <= pd.Timestamp(end_date))].copy()
    if not last_12m.empty:
        last_12m["Mês"] = last_12m["Data"].dt.to_period("M").dt.to_timestamp()
        monthly = last_12m.groupby("Mês", as_index=False).agg(
            Faturamento=("Faturamento", "sum"), KG=("Peso", "sum"), Margem=("Margem", "sum"),
        )
        monthly["Margem %"] = monthly["Margem"] / monthly["Faturamento"].replace(0, pd.NA)
        chart = px.bar(monthly, x="Mês", y="Faturamento", title="Compras nos últimos 12 meses")
        chart.update_traces(marker_color="#F36A2D")
        show_chart(_polish_chart(chart, x_title="", y_title="Faturamento (R$)"))

    matrix, cadence = purchase_seasonality(
        client_history, end_date, None if selected == "Todos os clientes" else [selected]
    )
    if not matrix.empty:
        if selected == "Todos os clientes":
            top_clients = matrix.sum(axis=1).nlargest(25).index
            heat = matrix.loc[top_clients]
        else:
            heat = matrix
        heat_chart = px.imshow(
            heat, aspect="auto", color_continuous_scale=["#F4F6F8", "#F36A2D"],
            labels={"x": "Mês", "y": "Cliente", "color": "Faturamento"},
            title="Janela de compra por cliente",
        )
        show_chart(_polish_chart(heat_chart, height=max(260, 28 * len(heat) + 120), x_title="", y_title=""))
    if not cadence.empty:
        with st.expander("Ver frequência e janela de recompra"):
            show_table(cadence.sort_values(["Janela vencida", "Dias sem comprar"], ascending=False), height=420, width="stretch", hide_index=True)

    st.markdown("### Carteira e movimentação")
    portfolio = customer_portfolio(current, client_history, start_date, end_date, mode)
    if selected == "Todos os clientes" and not portfolio.empty:
        columns = [column for column in [
            "Cliente", "Vendedor", "Canal", "UF", "Município", "Última compra", "Dias sem comprar",
            "Faturamento atual", "Faturamento referência", "Variação faturamento %",
            "KG atual", "Margem % atual", "Preço médio atual", "Mix atual", "Situação",
        ] if column in portfolio]
        show_table(portfolio[columns], height=560, width="stretch", hide_index=True)
    else:
        st.markdown("### Produtos comprados")
        products = entity_comparison(current, reference, "Produto")
        if not products.empty:
            show_table(products, height=500, width="stretch", hide_index=True)
        detail_columns = [column for column in ["Data", "NF", "Produto", "Grupo Produto", "Faturamento", "Peso", "Margem", "Margem %", "Preço Real Kg"] if column in current]
        with st.expander("Ver histórico de compras"):
            show_table(current[detail_columns].sort_values("Data", ascending=False), height=520, width="stretch", hide_index=True)
    if can_export and not portfolio.empty:
        st.download_button("Exportar carteira", portfolio.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), "clientes.csv", "text/csv")


def _product_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export):
    st.subheader("Inteligência de produtos")
    available = sorted(history["Produto"].dropna().astype(str).unique().tolist())
    selected = st.selectbox("Produto", ["Todos os produtos"] + available, key="product_page_scope")
    mode, reference_label = _reference_selector("product_reference")
    current = data if selected == "Todos os produtos" else data[data["Produto"].astype(str) == selected]
    product_history = history if selected == "Todos os produtos" else history[history["Produto"].astype(str) == selected]
    reference, ref_start, ref_end = reference_period(product_history, start_date, end_date, mode)
    st.caption(f"Comparação com {reference_label}: {ref_start.strftime('%d/%m/%Y')} a {ref_end.strftime('%d/%m/%Y')}.")
    _comparison_cards(commercial_metrics(current), commercial_metrics(reference), brl, brl2, pct)

    comparison = entity_comparison(current, reference, "Produto")
    if comparison.empty:
        st.info("Sem produtos no recorte selecionado.")
        return
    if selected == "Todos os produtos":
        curve = product_curve(current)
        st.markdown("### Curva e mix de produtos")
        chart = px.bar(
            curve.head(20).sort_values("Faturamento atual"), x="Faturamento atual", y="Produto",
            color="Curva", orientation="h", title="Top produtos e classificação ABC",
            color_discrete_map={"A": "#F36A2D", "B": "#2F8FD8", "C": "#AAB4C0"},
        )
        show_chart(_polish_chart(chart, height=620, x_title="Faturamento (R$)", y_title=""))
        curve_counts = curve.groupby("Curva").agg(
            Produtos=("Produto", "nunique"), Faturamento=("Faturamento atual", "sum"),
            KG=("KG atual", "sum"),
        ).reset_index()
        show_table(curve_counts, width="stretch", hide_index=True)

    st.markdown("### Performance por produto e categoria")
    dimension = st.segmented_control(
        "Agrupar por", [column for column in ["Produto", "Grupo Produto", "Tipo Produto"] if column in current],
        default="Produto", key="product_dimension",
    )
    view = entity_comparison(current, reference, dimension)
    chart_data = view.head(15).sort_values("Faturamento atual")
    chart = px.bar(chart_data, x="Faturamento atual", y=dimension, orientation="h", title=f"Faturamento por {dimension.lower()}")
    chart.update_traces(marker_color="#F36A2D")
    show_chart(_polish_chart(chart, height=520, x_title="Faturamento (R$)", y_title=""))
    show_table(view, height=560, width="stretch", hide_index=True)
    if can_export:
        st.download_button("Exportar produtos", view.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), "produtos.csv", "text/csv")


def _insights_view(data, history, start_date, end_date, brl, show_table, can_export):
    st.subheader("Insights e oportunidades")
    st.caption("Filas de ação calculadas com o mesmo período do ano anterior e a janela de compra dos últimos 12 meses.")
    insights = actionable_insights(data, history, start_date, end_date)
    reactivation = insights["reactivation"]
    declines = insights["declines"]
    seasonality = insights["seasonality"]
    mix = insights["mix"]
    cards = st.columns(4)
    cards[0].metric("Clientes para reativar", len(reactivation), brl(reactivation["Potencial R$"].sum()) if not reactivation.empty else brl(0))
    cards[1].metric("Clientes em queda", len(declines), brl(declines["Potencial R$"].sum()) if not declines.empty else brl(0))
    cards[2].metric("Janelas vencidas", len(seasonality))
    cards[3].metric("Oportunidades de mix", len(mix))

    tabs = st.tabs(["Reativação", "Possíveis quedas", "Sazonalidade", "Recuperação de mix"])
    selections = [
        (reactivation, ["Cliente", "Vendedor", "UF", "Última_compra", "Dias sem comprar", "Faturamento referência", "Potencial R$", "Ação"]),
        (declines, ["Cliente", "Vendedor", "UF", "Faturamento atual", "Faturamento referência", "Variação faturamento %", "Margem % atual", "Δ Margem p.p.", "Potencial R$", "Ação"]),
        (seasonality, ["Cliente", "Vendedor", "UF", "Última compra", "Dias sem comprar", "Cadência mediana (dias)", "Faturamento 12m", "Ação"]),
        (mix, ["Cliente", "Vendedor", "Faturamento atual", "Mix atual", "Mix referência", "Produtos a recuperar", "Potencial R$", "Ação"]),
    ]
    for tab, (frame, columns) in zip(tabs, selections):
        with tab:
            if frame.empty:
                st.success("Nenhuma ocorrência relevante encontrada neste recorte.")
            else:
                visible = [column for column in columns if column in frame]
                show_table(frame[visible], height=560, width="stretch", hide_index=True)
                if can_export:
                    file_name = f"insights_{visible[0].lower().replace(' ', '_')}.csv"
                    st.download_button("Exportar lista", frame[visible].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), file_name, "text/csv", key=f"export_{file_name}")


def _seller_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export):
    st.subheader("Painel de indicadores por vendedor")
    available = sorted(history["Vendedor"].dropna().astype(str).unique().tolist())
    selected = st.selectbox("Vendedor", ["Todos os vendedores"] + available, key="seller_page_scope")
    mode, reference_label = _reference_selector("seller_reference")
    current = data if selected == "Todos os vendedores" else data[data["Vendedor"].astype(str) == selected]
    seller_history = history if selected == "Todos os vendedores" else history[history["Vendedor"].astype(str) == selected]
    reference, ref_start, ref_end = reference_period(seller_history, start_date, end_date, mode)
    st.caption(f"Comparação com {reference_label}: {ref_start.strftime('%d/%m/%Y')} a {ref_end.strftime('%d/%m/%Y')}.")
    _comparison_cards(commercial_metrics(current), commercial_metrics(reference), brl, brl2, pct)
    view = entity_comparison(current, reference, "Vendedor")
    if view.empty:
        st.info("Sem vendedores no período.")
        return
    st.markdown("### Performance diária")
    daily = current.groupby(current["Data"].dt.normalize()).agg(
        Faturamento=("Faturamento", "sum"), KG=("Peso", "sum"), Margem=("Margem", "sum"),
        Clientes=("Cliente", "nunique"),
    ).reset_index(names="Data")
    daily["Margem %"] = daily["Margem"] / daily["Faturamento"].replace(0, pd.NA)
    if not daily.empty:
        chart = px.line(daily, x="Data", y="Faturamento", markers=True, title="Ritmo diário do vendedor")
        chart.update_traces(line=dict(color="#F36A2D", width=3))
        show_chart(_polish_chart(chart, x_title="", y_title="Faturamento (R$)"))
    st.markdown("### Comparação da equipe")
    show_table(view, height=520, width="stretch", hide_index=True)
    if can_export:
        st.download_button(
            "Exportar vendedores", view.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "performance_vendedores.csv", "text/csv", width="stretch",
        )


def _pivot(data, show_table, can_export):
    st.subheader("Tabela dinâmica")
    dimensions = [column for column in ("Vendedor", "Cliente", "Grupo Produto", "Produto", "Filial", "UF", "Município") if column in data.columns]
    c1, c2 = st.columns(2)
    rows = c1.multiselect("Linhas", dimensions, default=dimensions[:1])
    selected_metrics = c2.multiselect("Métricas", ["Faturamento", "Peso", "Margem", "Clientes"], default=["Faturamento", "Margem"])
    if not rows:
        st.info("Selecione pelo menos uma dimensão.")
        return
    definitions = {"Faturamento": ("Faturamento", "sum"), "Peso": ("Peso", "sum"), "Margem": ("Margem", "sum"), "Clientes": ("Cliente", "nunique")}
    result = data.groupby(rows, dropna=False).agg(**{name: definitions[name] for name in selected_metrics}).reset_index()
    if "Faturamento" in result and "Margem" in result:
        result["Margem %"] = result["Margem"] / result["Faturamento"].replace(0, pd.NA)
    show_table(result, height=620, width="stretch", hide_index=True)
    if can_export:
        st.download_button("Exportar tabela", result.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), "tabela_dinamica.csv", "text/csv", width="stretch")


def _yoy(data, history, start_date, end_date, show_chart, show_table):
    st.subheader("Comparativo com o ano anterior")
    dimensions = [column for column in ("Vendedor", "Cliente", "Grupo Produto", "UF", "Município") if column in data.columns]
    dimension = st.selectbox("Analisar por", dimensions, key="yoy_dimension")
    previous = _shifted_period(history, start_date, end_date, years=1)
    current_view = _summary(data, dimension, data["Faturamento"].sum()).set_index(dimension)
    prior_view = _summary(previous, dimension, previous["Faturamento"].sum()).set_index(dimension)
    result = current_view[["Faturamento", "Margem %", "Preço médio/kg", "Clientes positivados"]].join(
        prior_view[["Faturamento", "Margem %", "Preço médio/kg", "Clientes positivados"]], how="outer", lsuffix=" atual", rsuffix=" ano anterior"
    ).fillna(0).reset_index()
    result["Variação faturamento %"] = np.where(
        result["Faturamento ano anterior"] != 0,
        result["Faturamento atual"] / result["Faturamento ano anterior"] - 1, np.nan,
    )
    result = result.sort_values("Faturamento atual", ascending=False)
    chart = px.bar(result.head(12), x=dimension, y=["Faturamento atual", "Faturamento ano anterior"], barmode="group", title="Faturamento atual x ano anterior")
    show_chart(_polish_chart(chart, height=430, x_title="", y_title="Faturamento (R$)"))
    show_table(result, height=520, width="stretch", hide_index=True)


def render(data, history, start_date, end_date, last_load, brl, brl2, pct, pp, show_chart, show_table, *, permissions, current_user):
    """Exibe somente as páginas explicitamente liberadas ao usuário."""
    pages = []
    if "view_overview" in permissions:
        pages.append(("Visão executiva", "view_overview"))
    if "view_clients" in permissions:
        pages.append(("Clientes", "view_clients"))
    if "view_products" in permissions:
        pages.append(("Produtos", "view_products"))
    if "view_daily" in permissions:
        pages.append(("Performance diária", "view_daily"))
    if "view_sellers" in permissions:
        pages.append(("Vendedores", "view_sellers"))
    if "view_insights" in permissions:
        pages.append(("Insights", "view_insights"))
    if "view_pivot" in permissions:
        pages.append(("Tabela dinâmica", "view_pivot"))
    if "view_yoy" in permissions:
        pages.append(("Comparativo anual", "view_yoy"))
    if "use_assistant" in permissions:
        pages.append(("Assistente analítico", "use_assistant"))
    if "manage_users" in permissions:
        pages.append(("Usuários", "manage_users"))
    if not pages:
        st.error("Seu usuário não possui permissão para nenhuma visão. Procure um administrador.")
        return

    labels = [label for label, _ in pages]
    selected = st.segmented_control("Navegação", labels, default=labels[0], key="mf_page")
    permission = dict(pages)[selected]
    can_export = "export_data" in permissions
    if permission == "view_overview":
        _command_center(data, history, start_date, end_date, last_load, brl, brl2, pct, show_chart, show_table)
    elif permission == "view_clients":
        _client_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export)
    elif permission == "view_products":
        _product_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export)
    elif permission == "view_daily":
        _daily(data, history, end_date, brl, brl2, pct, show_chart, show_table)
    elif permission == "view_sellers":
        _seller_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export)
    elif permission == "view_insights":
        _insights_view(data, history, start_date, end_date, brl, show_table, can_export)
    elif permission == "view_pivot":
        _pivot(data, show_table, can_export)
    elif permission == "view_yoy":
        _yoy(data, history, start_date, end_date, show_chart, show_table)
    elif permission == "use_assistant":
        st.subheader("Assistente analítico")
        st.caption("Respostas calculadas a partir do período e dos filtros atuais.")
        if "chat" not in st.session_state:
            st.session_state.chat = []
        for role, message in st.session_state.chat:
            with st.chat_message(role):
                st.markdown(message)
        question = st.chat_input("Ex.: quais vendedores mais contribuíram para o resultado?")
        if question:
            response = answer(question, data, history, start_date, end_date)
            st.session_state.chat.extend([("user", question), ("assistant", response)])
            st.rerun()
    elif permission == "manage_users":
        render_user_admin(
            current_user,
            seller_options=sorted(history["Vendedor"].dropna().astype(str).unique().tolist()),
        )
