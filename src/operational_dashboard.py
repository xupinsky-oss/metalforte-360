"""Visões operacionais enxutas do METALFORTE 360."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analytics import compare_periods, group_metrics, metrics
from src.assistant import answer


def _polish_chart(chart, *, height=None, x_title=None, y_title=None):
    """Padroniza os gráficos para leitura rápida e sem ruído visual."""
    chart.update_layout(
        height=height,
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12, color="#243447"),
        title=dict(font=dict(size=16, color="#243447"), x=0, xanchor="left"),
        margin=dict(l=18, r=72, t=58, b=42),
        showlegend=False,
        hoverlabel=dict(bgcolor="#243447", font_color="white"),
    )
    if x_title is not None:
        chart.update_xaxes(title=x_title)
    if y_title is not None:
        chart.update_yaxes(title=y_title)
    chart.update_xaxes(showgrid=True, gridcolor="#E5E7EB", zeroline=False)
    chart.update_yaxes(showgrid=False, zeroline=False)
    return chart


def _classification_columns(data):
    candidates = [
        "Segmento Cliente", "Grupo Cliente", "Classificação Cliente",
        "Classificacao Cliente", "Tipo Cliente", "Ramo Atividade",
        "Curva Cliente",
    ]
    return [column for column in candidates if column in data.columns]


def _summary(data, dimension, total):
    if data.empty or dimension not in data.columns:
        return pd.DataFrame()
    result = group_metrics(data, dimension).rename(columns={
        "faturamento": "Faturamento", "margem": "Margem",
        "margem_pct": "Margem %", "peso": "Peso (kg)",
        "clientes": "Clientes", "produtos": "Produtos",
        "preco_kg": "Preço médio / kg", "nfs": "Notas fiscais",
    })
    result["Participação %"] = result["Faturamento"] / total if total else 0
    return result.sort_values("Faturamento", ascending=False)


def _compact_bar(view, dimension, title, color="#F36A2D", limit=10):
    """Ranking enxuto: barras ordenadas, rótulos diretos e sem legenda redundante."""
    ranked = view.head(limit).sort_values("Faturamento")
    chart = px.bar(
        ranked, x="Faturamento", y=dimension, orientation="h",
        title=title, color_discrete_sequence=[color],
        text=ranked["Faturamento"].map(lambda value: f"R$ {value / 1_000_000:.1f} mi" if abs(value) >= 1_000_000 else f"R$ {value / 1_000:.0f} mil"),
        hover_data={"Peso (kg)": ":,.0f", "Participação %": ":.2%", "Margem %": ":.2%", "Clientes": ":,.0f"},
    )
    chart.update_traces(textposition="outside", cliponaxis=False, marker_line_width=0)
    _polish_chart(chart, height=max(330, 32 * len(ranked) + 100), x_title="Faturamento (R$)", y_title="")
    chart.update_xaxes(rangemode="tozero")
    return chart


def _breakdown_panel(data, dimension, title, total, show_chart, show_table):
    view = _summary(data, dimension, total)
    st.markdown(f"### {title}")
    if view.empty:
        st.info("Sem informações para este recorte no período selecionado.")
        return
    chart_col, table_col = st.columns([1.15, 1], gap="large")
    detail = view[[dimension, "Faturamento", "Participação %", "Peso (kg)", "Margem %", "Clientes", "Produtos"]]
    with chart_col:
        show_chart(_compact_bar(view, dimension, f"Top 10 por faturamento"))
    with table_col:
        st.caption("Valores exatos e indicadores complementares")
        show_table(detail.head(10), height=420, width="stretch", hide_index=True)
    if len(detail) > 10:
        with st.expander(f"Ver todos os {dimension.lower()}s ({len(detail):,})".replace(",", ".")):
            show_table(detail, height=480, width="stretch", hide_index=True)


def _command_center(data, history, start_date, end_date, last_load, brl, pct, pp, show_chart, show_table):
    st.subheader("Command Center Comercial")
    st.caption(
        f"Visão operacional de {start_date.strftime('%d/%m/%Y')} a "
        f"{end_date.strftime('%d/%m/%Y')} • última carga: {last_load}"
    )
    current = metrics(data)
    comparison = compare_periods(history, start_date, end_date, "Vendedor", 1000)
    previous = comparison["previous_metrics"]
    revenue_growth = (current["revenue"] / previous["revenue"] - 1) if previous["revenue"] else 0
    margin_delta = (current["margin_pct"] - previous["margin_pct"]) * 100

    cards = st.columns(6)
    cards[0].metric("Faturamento", brl(current["revenue"]), delta=f"{revenue_growth:+.1%}".replace(".", ","))
    cards[1].metric("Peso faturado", f"{current['weight']:,.0f} kg".replace(",", "."))
    cards[2].metric("Margem", brl(current["margin"]), delta=pp(margin_delta))
    cards[3].metric("Margem %", pct(current["margin_pct"]))
    cards[4].metric("Clientes", f"{current['clients']:,}".replace(",", "."))
    cards[5].metric("Preço médio/kg", brl(current["price_kg"]))

    st.markdown("### Evolução mensal")
    monthly_start = pd.Timestamp(end_date).to_period("M").start_time - pd.DateOffset(months=11)
    monthly = history[
        (history["Data"] >= monthly_start)
        & (history["Data"] < pd.Timestamp(end_date) + pd.Timedelta(days=1))
    ].dropna(subset=["Data"]).copy()
    if monthly.empty:
        st.info("Sem dados mensais para o período selecionado.")
    else:
        monthly["Mês"] = monthly["Data"].dt.to_period("M").dt.to_timestamp()
        monthly = monthly.groupby("Mês", as_index=False).agg(
            Faturamento=("Faturamento", "sum"), Peso=("Peso", "sum"), Margem=("Margem", "sum")
        )
        monthly["Margem %"] = monthly["Margem"] / monthly["Faturamento"].replace(0, pd.NA)
        monthly["Mês referência"] = monthly["Mês"].dt.strftime("%m/%Y")
        metric = st.segmented_control(
            "Exibir faturamento em", ["R$", "kg"], default="R$", key="command_monthly_metric",
        )
        value_column = "Faturamento" if metric == "R$" else "Peso"
        unit_label = "Faturamento (R$)" if metric == "R$" else "Peso faturado (kg)"
        chart_col, table_col = st.columns([1.45, 1], gap="large")
        with chart_col:
            chart = go.Figure()
            chart.add_bar(
                x=monthly["Mês"], y=monthly[value_column], name=unit_label,
                marker_color="#F36A2D", marker_line_width=0,
                hovertemplate="%{x|%m/%Y}<br>" + unit_label + ": %{y:,.0f}<extra></extra>",
            )
            chart.add_scatter(
                x=monthly["Mês"], y=monthly["Margem %"], name="Margem %",
                yaxis="y2", mode="lines+markers",
                line=dict(color="#243447", width=3), marker=dict(size=7, color="#243447"),
                hovertemplate="%{x|%m/%Y}<br>Margem: %{y:.2%}<extra></extra>",
            )
            chart.update_layout(
                title=f"{unit_label} e margem mensal",
                height=390, barmode="group", showlegend=True,
                legend=dict(orientation="h", y=1.12, x=0),
                yaxis=dict(title=unit_label, rangemode="tozero"),
                yaxis2=dict(title="Margem %", overlaying="y", side="right", tickformat=".1%", showgrid=False),
            )
            _polish_chart(chart, height=390, x_title="", y_title=unit_label)
            chart.update_layout(showlegend=True, legend=dict(orientation="h", y=1.12, x=0))
            chart.update_xaxes(dtick="M1", tickformat="%b/%y")
            show_chart(chart)
        with table_col:
            st.caption("Resumo mensal para conferência")
            show_table(
                monthly[["Mês referência", "Faturamento", "Peso", "Margem %"]].sort_values("Mês referência", ascending=False),
                height=390, width="stretch", hide_index=True,
            )

    total = current["revenue"]
    customer_classes = _classification_columns(data)
    if customer_classes:
        customer_class = st.selectbox(
            "Classificação do cliente", customer_classes,
            help="Segmento e Tipologia vêm do cadastro do cliente no GoodData; Curva Cliente representa somente valor A/B/C.",
            key="command_customer_classification",
        )
        _breakdown_panel(data, customer_class, "Painel por grupo de clientes", total, show_chart, show_table)
        st.caption(f"Classificação utilizada diretamente da base: {customer_class}.")
    else:
        st.markdown("### Painel por grupo de clientes")
        st.warning("A carga não possui uma classificação de cliente. Inclua Grupo/Segmento/Tipo Cliente na origem GoodData.")
    _breakdown_panel(data, "Grupo Produto", "Painel por grupo de produtos", total, show_chart, show_table)
    _breakdown_panel(data, "Vendedor", "Painel por vendedor", total, show_chart, show_table)
    _breakdown_panel(data, "Município", "Painel por cidade", total, show_chart, show_table)


def _daily(data, history, start_date, end_date, brl, pct, show_chart, show_table):
    st.subheader("Performance do Dia")
    day = pd.Timestamp(end_date)
    today = history[history["Data"].dt.normalize() == day]
    prior = history[history["Data"].dt.normalize() == day - pd.Timedelta(days=1)]
    tm, pm = metrics(today), metrics(prior)
    cards = st.columns(5)
    cards[0].metric("Faturamento do dia", brl(tm["revenue"]), delta=brl(tm["revenue"] - pm["revenue"]))
    cards[1].metric("Peso do dia", f"{tm['weight']:,.0f} kg".replace(",", "."))
    cards[2].metric("Margem %", pct(tm["margin_pct"]))
    cards[3].metric("Clientes compradores", f"{tm['clients']:,}".replace(",", "."))
    cards[4].metric("Notas fiscais", f"{tm['invoices']:,}".replace(",", "."))
    daily = data.groupby(data["Data"].dt.normalize()).agg(Faturamento=("Faturamento", "sum"), Peso=("Peso", "sum"), Margem=("Margem", "sum")).reset_index(names="Data")
    if not daily.empty:
        daily["Margem %"] = daily["Margem"] / daily["Faturamento"].replace(0, pd.NA)
        chart_col, table_col = st.columns([1.4, 1], gap="large")
        with chart_col:
            chart = px.line(daily, x="Data", y="Faturamento", markers=True, title="Ritmo diário de faturamento")
            chart.update_traces(line=dict(color="#F36A2D", width=3), marker=dict(size=7))
            _polish_chart(chart, height=380, x_title="", y_title="Faturamento (R$)")
            show_chart(chart)
        with table_col:
            st.caption("Fechamento diário do período")
            show_table(daily.sort_values("Data", ascending=False), height=380, width="stretch", hide_index=True)
    for dimension in ("Vendedor", "Cliente", "Grupo Produto"):
        view = _summary(today, dimension, tm["revenue"])
        if not view.empty:
            st.markdown(f"### Resultado do dia por {dimension.lower()}")
            show_table(view.head(100), height=330, width="stretch", hide_index=True)


def _seller_view(data, history, start_date, end_date, brl, pct, pp, show_chart, show_table):
    st.subheader("Visão por Vendedor")
    comparison = compare_periods(history, start_date, end_date, "Vendedor", 1000)
    current = _summary(comparison["current"], "Vendedor", comparison["current_metrics"]["revenue"])
    previous = group_metrics(comparison["previous"], "Vendedor")[["Vendedor", "faturamento", "margem_pct"]].rename(columns={"faturamento": "Faturamento anterior", "margem_pct": "Margem % anterior"}) if not comparison["previous"].empty else pd.DataFrame(columns=["Vendedor", "Faturamento anterior", "Margem % anterior"])
    team = current.merge(previous, on="Vendedor", how="outer").fillna(0)
    team["Variação %"] = (team["Faturamento"] - team["Faturamento anterior"]) / team["Faturamento anterior"].replace(0, pd.NA)
    team["Δ Margem p.p."] = (team["Margem %"] - team["Margem % anterior"]) * 100
    team["Performance"] = np.select(
        [(team["Variação %"] >= 0) & (team["Δ Margem p.p."] >= 0), (team["Variação %"] >= 0), (team["Δ Margem p.p."] >= 0)],
        ["Crescimento rentável", "Crescimento com pressão", "Queda com margem protegida"], default="Queda com pressão",
    )
    chart_col, table_col = st.columns([1.15, 1], gap="large")
    with chart_col:
        show_chart(_compact_bar(team, "Vendedor", "Top 10 vendedores por faturamento", color="#2F8FD8"))
    with table_col:
        st.caption("Performance e comparação com o período anterior")
        show_table(team.head(10), height=420, width="stretch", hide_index=True)
    with st.expander(f"Ver equipe completa ({len(team):,} vendedores)".replace(",", ".")):
        show_table(team, height=520, width="stretch", hide_index=True)
    st.download_button("Exportar vendedores", team.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), "performance_vendedores.csv", "text/csv", width="stretch")


def _pivot(data, show_table):
    st.subheader("Tabela Dinâmica")
    dimensions = [c for c in ["Vendedor", "Cliente", "Grupo Produto", "Tipo Produto", "Produto", "Filial", "UF", "Município", "Curva Cliente", "Mes"] if c in data.columns]
    c1, c2 = st.columns(2)
    rows = c1.multiselect("Linhas", dimensions, default=dimensions[:1])
    metrics_selected = c2.multiselect("Métricas", ["Faturamento", "Peso", "Margem", "Clientes", "Produtos", "Notas fiscais"], default=["Faturamento", "Peso", "Margem"])
    if not rows:
        st.info("Selecione pelo menos uma dimensão.")
        return
    aggregations = {"Faturamento": ("Faturamento", "sum"), "Peso": ("Peso", "sum"), "Margem": ("Margem", "sum"), "Clientes": ("Cliente", "nunique"), "Produtos": ("Produto", "nunique"), "Notas fiscais": ("NF", "nunique")}
    selected = {name: aggregations[name] for name in metrics_selected}
    result = data.groupby(rows, dropna=False).agg(**selected).reset_index() if selected else data[rows].drop_duplicates()
    if "Faturamento" in result and "Margem" in result:
        result["Margem %"] = result["Margem"] / result["Faturamento"].replace(0, pd.NA)
    show_table(result, height=620, width="stretch", hide_index=True)
    st.download_button("Exportar tabela dinâmica", result.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), "tabela_dinamica.csv", "text/csv", width="stretch")


def _yoy(data, history, start_date, end_date, show_chart, show_table):
    st.subheader("Comparativo com o mesmo período do ano anterior")
    dimension = st.selectbox("Analisar por", ["Vendedor", "Cliente", "Grupo Produto", "Produto", "UF", "Município"])
    current = data
    prior_start, prior_end = pd.Timestamp(start_date) - pd.DateOffset(years=1), pd.Timestamp(end_date) - pd.DateOffset(years=1)
    previous = history[(history["Data"] >= prior_start) & (history["Data"] < prior_end + pd.Timedelta(days=1))]
    cur = group_metrics(current, dimension).set_index(dimension)[["faturamento", "margem"]]
    prev = group_metrics(previous, dimension).set_index(dimension)[["faturamento", "margem"]]
    result = cur.join(prev, how="outer", lsuffix=" atual", rsuffix=" anterior").fillna(0).reset_index()
    result["Δ Faturamento"] = result["faturamento atual"] - result["faturamento anterior"]
    result["Variação %"] = result["Δ Faturamento"] / result["faturamento anterior"].replace(0, pd.NA)
    result["Margem % atual"] = result["margem atual"] / result["faturamento atual"].replace(0, pd.NA)
    result = result.sort_values("Δ Faturamento", ascending=False)
    ranked = result.reindex(result["Δ Faturamento"].abs().sort_values(ascending=False).index).head(12).sort_values("Δ Faturamento")
    colors = np.where(ranked["Δ Faturamento"] >= 0, "#2F8FD8", "#F3B28F")
    chart = go.Figure(go.Bar(
        x=ranked["Δ Faturamento"], y=ranked[dimension], orientation="h",
        marker_color=colors,
        text=ranked["Δ Faturamento"].map(lambda value: f"{value / 1_000:+.0f} mil"), textposition="outside",
        customdata=ranked[["faturamento atual", "faturamento anterior", "Variação %"]],
        hovertemplate="%{y}<br>Variação: R$ %{x:,.0f}<br>Atual: R$ %{customdata[0]:,.0f}<br>Ano anterior: R$ %{customdata[1]:,.0f}<br>Variação: %{customdata[2]:.2%}<extra></extra>",
    ))
    _polish_chart(chart, height=470, x_title="Variação de faturamento (R$)", y_title="")
    chart.update_layout(title="Movimentações de faturamento vs. ano anterior")
    chart.update_xaxes(zeroline=True, zerolinewidth=1.5, zerolinecolor="#64748B")
    chart_col, table_col = st.columns([1.15, 1], gap="large")
    with chart_col:
        show_chart(chart)
    with table_col:
        st.caption("Valores atuais, anteriores e variação")
        show_table(result.head(12), height=470, width="stretch", hide_index=True)
    with st.expander(f"Ver comparativo completo ({len(result):,} registros)".replace(",", ".")):
        show_table(result, height=550, width="stretch", hide_index=True)


def render(data, history, start_date, end_date, last_load, brl, pct, pp, show_chart, show_table):
    """Renderiza somente as páginas operacionais autorizadas."""
    tabs = st.tabs(["Command Center", "Performance do Dia", "Visão por Vendedor", "Tabela Dinâmica", "Comparativo YoY", "Assistente IA"])
    with tabs[0]:
        _command_center(data, history, start_date, end_date, last_load, brl, pct, pp, show_chart, show_table)
    with tabs[1]:
        _daily(data, history, start_date, end_date, brl, pct, show_chart, show_table)
    with tabs[2]:
        _seller_view(data, history, start_date, end_date, brl, pct, pp, show_chart, show_table)
    with tabs[3]:
        _pivot(data, show_table)
    with tabs[4]:
        _yoy(data, history, start_date, end_date, show_chart, show_table)
    with tabs[5]:
        st.subheader("Assistente IA analítica")
        st.caption(f"Contexto: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')} • última carga: {last_load}")
        if "chat" not in st.session_state:
            st.session_state.chat = []
        for role, message in st.session_state.chat:
            with st.chat_message(role):
                st.markdown(message)
        question = st.chat_input("Ex.: quais vendedores e grupos mais contribuíram para o resultado?")
        if question:
            response = answer(question, data, history, start_date, end_date)
            st.session_state.chat.extend([("user", question), ("assistant", response)])
            st.rerun()
