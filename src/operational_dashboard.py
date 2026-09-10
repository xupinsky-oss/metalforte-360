"""Painel comercial simplificado, comparável e controlado por permissões."""

import html

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.analytics import group_metrics, metrics
from src.assistant import answer
from src.auth import render_user_admin
from src.targets import allocate_target, target_scope
from src.commercial_intelligence import (
    actionable_insights,
    commercial_metrics,
    customer_portfolio,
    entity_comparison,
    product_curve,
    purchase_seasonality,
    reference_period,
)


PANEL_HELP = {
    "overview": "Consolida o período e os filtros ativos. Faturamento é a soma líquida; preço médio é faturamento dividido por KG; margem % é margem dividida por faturamento; positivados são clientes com faturamento líquido positivo. As referências usam o mesmo intervalo deslocado.",
    "daily": "Agrupa os movimentos pela data de faturamento. A comparação usa o último dia disponível anterior, evitando comparar com um dia sem carga.",
    "clients": "Consolida compras por cliente no período selecionado. Histórico, última compra e janela de recompra usam a série disponível até a data final; a sazonalidade considera os últimos 12 meses.",
    "products": "Agrupa faturamento, KG, margem e preço médio por produto ou categoria. A Curva ABC é calculada pela participação acumulada no faturamento: A até 70%, B até 90% e C no restante.",
    "insights": "Gera filas acionáveis por cliente. Reativação e queda comparam o período ao mesmo intervalo do ano anterior; sazonalidade usa a cadência mediana de compras dos últimos 12 meses; recuperação de mix compara a quantidade de produtos do período com a referência anual.",
    "sellers": "Consolida os indicadores por vendedor no período e aplica a referência escolhida. Positivação conta clientes com faturamento líquido positivo.",
    "targets": "Compara o realizado às metas oficiais mensais. KG vem do relatório 044 no grão vendedor × grupo; o total R$ vem do relatório 045 e é conciliado nesse grão. Cliente e produto são alocações proporcionais ao histórico dos 12 meses anteriores.",
    "pivot": "Agrupa os registros filtrados pelas dimensões escolhidas e soma faturamento, peso e margem; clientes são contados de forma distinta. Margem % é margem dividida pelo faturamento.",
    "yoy": "Compara o período selecionado com as mesmas datas deslocadas em um ano, preservando a duração e os filtros atuais.",
    "assistant": "Responde somente com base nos dados do período e filtros ativos; não consulta fontes externas e não altera a base.",
}


INSIGHT_HELP = {
    "reactivation": "Clientes que compraram no mesmo período do ano anterior e ainda não faturaram no período atual. O potencial é a diferença positiva entre faturamento de referência e atual.",
    "declines": "Clientes ativos nos dois períodos cuja queda de faturamento é de 20% ou mais. O potencial é a parcela necessária para recuperar o nível do ano anterior.",
    "seasonality": "Clientes cuja última compra ultrapassou 125% da cadência mediana entre compras. A cadência exige ao menos duas datas de compra e mínimo de 7 dias.",
    "mix": "Clientes ativos cujo número de produtos distintos ficou abaixo do mesmo período do ano anterior. Produtos a recuperar é a diferença entre o mix de referência e o atual.",
}


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


def _metric_card_html(label, value, comparisons=()):
    comparison_html = []
    for comparison_label, reference_value, change, points in comparisons:
        direction = "neutral" if change is None or pd.isna(change) else ("up" if change >= 0 else "down")
        arrow = "" if direction == "neutral" else ("↑ " if direction == "up" else "↓ ")
        comparison_html.append(
            f'<div class="mf-kpi-compare"><span class="mf-kpi-ref">{html.escape(comparison_label)}: '
            f'{html.escape(reference_value)}</span><span class="mf-kpi-delta {direction}">'
            f'{arrow}{html.escape(_comparison_text(change, points=points))}</span></div>'
        )
    # Mantenha o fragmento sem recuo: quatro espaços no início de uma linha
    # fazem o Markdown tratar os cartões seguintes como bloco de código.
    return (
        '<div class="mf-kpi">'
        f'<div class="mf-kpi-label">{html.escape(label)}</div>'
        f'<div class="mf-kpi-value">{html.escape(value)}</div>'
        f'{"".join(comparison_html)}'
        '</div>'
    )


def _metric_cards(cards):
    st.markdown(
        '<div class="mf-kpi-grid">' + ''.join(
            _metric_card_html(label, value, comparisons) for label, value, comparisons in cards
        ) + '</div>',
        unsafe_allow_html=True,
    )


def _quantity(value):
    return f"{value:,.0f}".replace(",", ".")


def _metric_value(key, value, brl, brl2, pct):
    if key == "revenue":
        return brl(value)
    if key == "weight":
        return f"{_quantity(value)} kg"
    if key == "margin_pct":
        return pct(value)
    if key == "price_kg":
        return brl2(value)
    if key == "positive_clients":
        return _quantity(value)
    return _quantity(value)


def _inject_kpi_styles():
    st.markdown("""
    <style>
    .mf-kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:.8rem;margin:.45rem 0 1rem}
    .mf-kpi{background:#fff;border:1px solid #DCE3EC;border-radius:12px;padding:1rem;min-height:162px;box-shadow:0 3px 14px rgba(23,32,51,.05)}
    .mf-kpi-label{font-size:.86rem;font-weight:700;color:#52647A}.mf-kpi-value{font-size:1.65rem;font-weight:800;color:#172033;margin:.3rem 0 .55rem}
    .mf-kpi-compare{display:flex;align-items:center;justify-content:space-between;gap:.35rem;font-size:.72rem;line-height:1.55;white-space:nowrap}
    .mf-kpi-ref{color:#64748B}.mf-kpi-delta{font-weight:700}.mf-kpi-delta.up{color:#177245}.mf-kpi-delta.down{color:#B33A2B}.mf-kpi-delta.neutral{color:#64748B}
    </style>
    """, unsafe_allow_html=True)


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
    st.subheader("Visão executiva", help=PANEL_HELP["overview"])
    st.caption(
        f"{pd.Timestamp(start_date).strftime('%d/%m/%Y')} a {pd.Timestamp(end_date).strftime('%d/%m/%Y')} • "
        f"comparações usam o mesmo intervalo deslocado em 1 mês e 1 ano • carga: {last_load}"
    )
    current = _period_metrics(data)
    prior_month = _period_metrics(_shifted_period(history, start_date, end_date, months=1))
    prior_year = _period_metrics(_shifted_period(history, start_date, end_date, years=1))

    definitions = [
        ("Faturamento", brl(current["revenue"]), "revenue", False),
        ("Preço médio/kg", brl2(current["price_kg"]), "price_kg", False),
        ("Margem %", pct(current["margin_pct"]), "margin_pct", True),
        ("Clientes positivados", f"{current['positive_clients']:,}".replace(",", "."), "positive_clients", False),
        ("KG faturado", f"{current['weight']:,.0f} kg".replace(",", "."), "weight", False),
    ]
    cards = []
    for label, value, key, points in definitions:
        if points:
            mom = (current[key] - prior_month[key]) * 100
            yoy = (current[key] - prior_year[key]) * 100
        else:
            mom = _relative(current[key], prior_month[key])
            yoy = _relative(current[key], prior_year[key])
        cards.append((label, value, [
            ("Mês ant.", _metric_value(key, prior_month[key], brl, brl2, pct), mom, points),
            ("Ano ant.", _metric_value(key, prior_year[key], brl, brl2, pct), yoy, points),
        ]))
    _metric_cards(cards)

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
            chart.update_yaxes(tickprefix="R$ ", tickformat=",.2f")
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
    st.subheader("Performance diária", help=PANEL_HELP["daily"])
    day = pd.Timestamp(end_date)
    today = history[history["Data"].dt.normalize() == day]
    previous_dates = history.loc[history["Data"].dt.normalize() < day, "Data"].dropna()
    prior_day = previous_dates.max().normalize() if not previous_dates.empty else day - pd.Timedelta(days=1)
    prior = history[history["Data"].dt.normalize() == prior_day]
    current, before = _period_metrics(today), _period_metrics(prior)
    daily_definitions = [
        ("Faturamento", "revenue", False), ("Preço médio/kg", "price_kg", False),
        ("Margem %", "margin_pct", True), ("Clientes positivados", "positive_clients", False),
    ]
    cards = []
    for label, key, points in daily_definitions:
        change = ((current[key] - before[key]) * 100) if points else _relative(current[key], before[key])
        cards.append(
            (label, _metric_value(key, current[key], brl, brl2, pct), [
                ("Dia ant.", _metric_value(key, before[key], brl, brl2, pct), change, points)
            ])
        )
    _metric_cards(cards)
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


def _comparison_cards(current, reference, reference_label, brl, brl2, pct):
    definitions = [
        ("Faturamento", brl(current["revenue"]), "revenue", False),
        ("KG faturado", f"{current['weight']:,.0f} kg".replace(",", "."), "weight", False),
        ("Margem %", pct(current["margin_pct"]), "margin_pct", True),
        ("Preço médio/kg", brl2(current["price_kg"]), "price_kg", False),
        ("Clientes positivados", f"{current['positive_clients']:,}".replace(",", "."), "positive_clients", False),
    ]
    cards = []
    for label, value, key, points in definitions:
        if points:
            delta = (current[key] - reference[key]) * 100
        else:
            delta = _relative(current[key], reference[key])
        cards.append(
            (label, value, [
                (reference_label.capitalize(), _metric_value(key, reference[key], brl, brl2, pct), delta, points)
            ])
        )
    _metric_cards(cards)


def _client_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export):
    st.subheader("Inteligência de clientes", help=PANEL_HELP["clients"])
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
    _comparison_cards(commercial_metrics(current), commercial_metrics(reference), reference_label, brl, brl2, pct)

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
    st.subheader("Inteligência de produtos", help=PANEL_HELP["products"])
    available = sorted(history["Produto"].dropna().astype(str).unique().tolist())
    selected = st.selectbox("Produto", ["Todos os produtos"] + available, key="product_page_scope")
    mode, reference_label = _reference_selector("product_reference")
    current = data if selected == "Todos os produtos" else data[data["Produto"].astype(str) == selected]
    product_history = history if selected == "Todos os produtos" else history[history["Produto"].astype(str) == selected]
    reference, ref_start, ref_end = reference_period(product_history, start_date, end_date, mode)
    st.caption(f"Comparação com {reference_label}: {ref_start.strftime('%d/%m/%Y')} a {ref_end.strftime('%d/%m/%Y')}.")
    _comparison_cards(commercial_metrics(current), commercial_metrics(reference), reference_label, brl, brl2, pct)

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
    st.subheader("Insights e oportunidades", help=PANEL_HELP["insights"])
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
        ("reactivation", reactivation, ["Cliente", "Vendedor", "UF", "Última_compra", "Dias sem comprar", "Faturamento referência", "Potencial R$", "Ação"]),
        ("declines", declines, ["Cliente", "Vendedor", "UF", "Faturamento atual", "Faturamento referência", "Variação faturamento %", "Margem % atual", "Δ Margem p.p.", "Potencial R$", "Ação"]),
        ("seasonality", seasonality, ["Cliente", "Vendedor", "UF", "Última compra", "Dias sem comprar", "Cadência mediana (dias)", "Faturamento 12m", "Ação"]),
        ("mix", mix, ["Cliente", "Vendedor", "Faturamento atual", "Mix atual", "Mix referência", "Produtos a recuperar", "Potencial R$", "Ação"]),
    ]
    for tab, (insight_key, frame, columns) in zip(tabs, selections):
        with tab:
            st.caption(f"ⓘ Metodologia: {INSIGHT_HELP[insight_key]}")
            if frame.empty:
                st.success("Nenhuma ocorrência relevante encontrada neste recorte.")
            else:
                visible = [column for column in columns if column in frame]
                show_table(frame[visible], height=560, width="stretch", hide_index=True)
                if can_export:
                    file_name = f"insights_{insight_key}.csv"
                    st.download_button("Exportar lista", frame[visible].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), file_name, "text/csv", key=f"export_insights_{insight_key}")


def _seller_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export):
    st.subheader("Painel de indicadores por vendedor", help=PANEL_HELP["sellers"])
    available = sorted(history["Vendedor"].dropna().astype(str).unique().tolist())
    selected = st.selectbox("Vendedor", ["Todos os vendedores"] + available, key="seller_page_scope")
    mode, reference_label = _reference_selector("seller_reference")
    current = data if selected == "Todos os vendedores" else data[data["Vendedor"].astype(str) == selected]
    seller_history = history if selected == "Todos os vendedores" else history[history["Vendedor"].astype(str) == selected]
    reference, ref_start, ref_end = reference_period(seller_history, start_date, end_date, mode)
    st.caption(f"Comparação com {reference_label}: {ref_start.strftime('%d/%m/%Y')} a {ref_end.strftime('%d/%m/%Y')}.")
    _comparison_cards(commercial_metrics(current), commercial_metrics(reference), reference_label, brl, brl2, pct)
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
    st.subheader("Tabela dinâmica", help=PANEL_HELP["pivot"])
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
    st.subheader("Comparativo com o ano anterior", help=PANEL_HELP["yoy"])
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


def _targets_view(data, history, targets, start_date, end_date, brl, pct, show_chart, show_table, filters, can_export, indicators=None):
    st.subheader("Metas e orçamento", help=PANEL_HELP["targets"])
    st.caption("ⓘ A competência da meta é independente do calendário de faturamento. Para meses futuros, o realizado permanece zerado até ocorrer faturamento.")
    targets = targets.copy() if targets is not None else pd.DataFrame()
    if targets.empty or "Competência" not in targets:
        st.info("A meta oficial ainda não foi publicada. Execute primeiro a atualização em homologação.")
        return
    targets["Competência"] = pd.to_datetime(targets["Competência"], errors="coerce").dt.to_period("M").dt.start_time
    available = sorted(pd.Timestamp(value) for value in targets["Competência"].dropna().unique())
    if not available:
        st.info("A base de metas não possui competências válidas.")
        return
    labels = [value.strftime("%m/%Y") for value in available]
    label_to_date = dict(zip(labels, available))
    current_month = pd.Timestamp.today().to_period("M").start_time
    default_date = current_month if current_month in available else max(
        (value for value in available if value <= current_month), default=available[-1]
    )
    default_label = default_date.strftime("%m/%Y")
    selected_range = st.select_slider(
        "Competências da meta", options=labels, value=(default_label, default_label),
        help="Selecione um mês ou arraste as extremidades para analisar metas anteriores e futuras.",
        key="target_competence_range",
    )
    selected_start, selected_end = selected_range if isinstance(selected_range, (tuple, list)) else (selected_range, selected_range)
    target_start, target_end = label_to_date[selected_start], label_to_date[selected_end]
    scoped = target_scope(
        targets, target_start, target_end,
        sellers=(filters or {}).get("sellers"), groups=(filters or {}).get("groups"),
    )
    if scoped.empty:
        st.info("A meta oficial ainda não foi publicada para o período e escopo selecionados. Execute primeiro a atualização em homologação.")
        return

    previous_count = sum(value < current_month for value in available)
    future_count = sum(value > current_month for value in available)
    st.caption(
        f"Cobertura oficial: {labels[0]} a {labels[-1]} • {previous_count} competência(s) anterior(es) • "
        f"{future_count} futura(s)."
    )
    actual_source = history.copy()
    actual_source = actual_source[
        (actual_source["Data"] >= target_start) & (actual_source["Data"] < target_end + pd.DateOffset(months=1))
    ]
    selected_client = (filters or {}).get("client")
    client_query = (filters or {}).get("client_text")
    product_query = (filters or {}).get("product_text")
    if selected_client:
        actual_source = actual_source[actual_source["Cliente"].astype(str) == str(selected_client)]
    if client_query:
        actual_source = actual_source[actual_source["Cliente"].astype(str).str.contains(client_query, case=False, na=False)]
    if product_query:
        actual_source = actual_source[actual_source["Produto"].astype(str).str.contains(product_query, case=False, na=False)]

    target_value = float(scoped["Meta R$"].sum())
    target_kg = float(scoped["Meta KG"].sum())
    actual_value = float(actual_source["Faturamento"].sum()) if not actual_source.empty else 0.0
    actual_kg = float(actual_source["Peso"].sum()) if not actual_source.empty else 0.0
    value_attainment = actual_value / target_value if target_value else 0.0
    kg_attainment = actual_kg / target_kg if target_kg else 0.0
    cards = st.columns(4)
    cards[0].metric("Meta faturamento", brl(target_value), f"Realizado {brl(actual_value)}")
    cards[1].metric("Atingimento R$", pct(value_attainment), f"Saldo {brl(actual_value-target_value)}")
    cards[2].metric("Meta KG", f"{_quantity(target_kg)} kg", f"Realizado {_quantity(actual_kg)} kg")
    cards[3].metric("Atingimento KG", pct(kg_attainment), f"Saldo {_quantity(actual_kg-target_kg)} kg")

    competence = scoped["Competência"].dropna().sort_values().dt.strftime("%m/%Y").unique().tolist()
    st.caption(f"Competência(s): {', '.join(competence)} • Fontes: Rel.044 (KG) e Rel.045 (R$).")
    indicators = indicators or {}
    st.markdown("### Pendências comerciais")
    st.caption("ⓘ Totais oficiais da carteira na última carga. Estes indicadores são globais e não seguem o detalhamento por cliente ou produto.")
    _metric_cards([
        ("Pedidos liberados", brl(float(indicators.get("pedidos_liberados_valor", 0) or 0)), ()),
        ("Peso liberado", f"{_quantity(float(indicators.get('pedidos_liberados_peso', 0) or 0))} kg", ()),
        ("Pedidos a faturar", brl(float(indicators.get("pedidos_nao_faturados_valor", 0) or 0)), ()),
        ("Peso a faturar", f"{_quantity(float(indicators.get('pedidos_nao_faturados_peso', 0) or 0))} kg", ()),
    ])
    dimension = st.segmented_control(
        "Detalhar por", ["Vendedor", "Grupo Produto", "Cliente", "Produto"],
        default="Vendedor", key="target_dimension",
    )
    allocation, unallocated = allocate_target(scoped, history, dimension)
    if dimension == "Cliente":
        selected = (filters or {}).get("client")
        query = (filters or {}).get("client_text")
        if selected:
            allocation = allocation[allocation["Cliente"].astype(str) == str(selected)]
        if query:
            allocation = allocation[allocation["Cliente"].astype(str).str.contains(query, case=False, na=False)]
    elif dimension == "Produto":
        query = (filters or {}).get("product_text")
        if query:
            allocation = allocation[allocation["Produto"].astype(str).str.contains(query, case=False, na=False)]

    if actual_source.empty or dimension not in actual_source:
        actual = pd.DataFrame(columns=[dimension, "Realizado R$", "Realizado KG"])
    else:
        actual = actual_source.groupby(dimension, dropna=False, as_index=False).agg(
            **{"Realizado R$": ("Faturamento", "sum"), "Realizado KG": ("Peso", "sum")}
        )
    view = allocation.merge(actual, on=dimension, how="outer").fillna(0)
    view["Atingimento R$ %"] = view["Realizado R$"] / view["Meta R$"].replace(0, pd.NA)
    view["Saldo R$"] = view["Realizado R$"] - view["Meta R$"]
    view["Atingimento KG %"] = view["Realizado KG"] / view["Meta KG"].replace(0, pd.NA)
    view["Saldo KG"] = view["Realizado KG"] - view["Meta KG"]
    view = view.sort_values("Meta R$", ascending=False)

    if dimension in ("Cliente", "Produto"):
        st.info(
            "Este detalhamento é uma alocação gerencial: R$ usa a participação positiva de faturamento e KG usa a participação positiva de peso nos 12 meses anteriores, dentro de cada vendedor × grupo."
        )
        if unallocated["Meta R$"] or unallocated["Meta KG"]:
            st.warning(f"Sem histórico para alocar: {brl(unallocated['Meta R$'])} e {_quantity(unallocated['Meta KG'])} kg.")
    if view.empty:
        st.info("Não há linhas para o detalhamento escolhido.")
        return
    chart_data = view.head(15).sort_values("Meta R$")
    chart = px.bar(
        chart_data, x=["Meta R$", "Realizado R$"], y=dimension, orientation="h", barmode="group",
        title=f"Meta x realizado por {dimension.lower()}", color_discrete_sequence=["#94A3B8", "#F36A2D"],
    )
    show_chart(_polish_chart(chart, height=max(390, 31 * len(chart_data) + 130), x_title="Valor (R$)", y_title=""))
    show_table(view, height=560, width="stretch", hide_index=True)
    if can_export:
        st.download_button(
            "Exportar metas", view.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "metas_orcamento.csv", "text/csv", width="stretch",
        )


def render(data, history, start_date, end_date, last_load, brl, brl2, pct, pp, show_chart, show_table, *, permissions, current_user, targets=None, target_history=None, target_filters=None, commercial_indicators=None):
    """Exibe somente as páginas explicitamente liberadas ao usuário."""
    _inject_kpi_styles()
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
    if "view_targets" in permissions:
        pages.append(("Metas", "view_targets"))
    if "view_insights" in permissions:
        pages.append(("Insights", "view_insights"))
    if "view_pivot" in permissions:
        pages.append(("Tabela dinâmica", "view_pivot"))
    if "view_yoy" in permissions:
        pages.append(("Comparativo anual", "view_yoy"))
    if "use_assistant" in permissions:
        pages.append(("Assistente analítico", "use_assistant"))
    if "manage_users" in permissions:
        pages.append(("Gestão de acessos", "manage_users"))
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
    elif permission == "view_targets":
        _targets_view(data, target_history if target_history is not None else history, targets, start_date, end_date, brl, pct, show_chart, show_table, target_filters, can_export, commercial_indicators)
    elif permission == "view_insights":
        _insights_view(data, history, start_date, end_date, brl, show_table, can_export)
    elif permission == "view_pivot":
        _pivot(data, show_table, can_export)
    elif permission == "view_yoy":
        _yoy(data, history, start_date, end_date, show_chart, show_table)
    elif permission == "use_assistant":
        st.subheader("Assistente analítico", help=PANEL_HELP["assistant"])
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
