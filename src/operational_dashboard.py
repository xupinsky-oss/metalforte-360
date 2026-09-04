"""Visões operacionais enxutas do METALFORTE 360."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analytics import compare_periods, group_metrics, metrics
from src.assistant import answer


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


def _breakdown_panel(data, dimension, title, total, show_chart, show_table):
    view = _summary(data, dimension, total)
    st.markdown(f"### {title}")
    if view.empty:
        st.info("Sem informações para este recorte no período selecionado.")
        return
    chart = px.bar(
        view.head(20).sort_values("Faturamento"), x="Faturamento", y=dimension,
        orientation="h", color="Margem %", color_continuous_scale="RdYlGn",
        title=f"Faturamento por {dimension.lower()}",
        hover_data={"Peso (kg)": ":,.0f", "Participação %": ":.2%", "Margem %": ":.2%"},
    )
    show_chart(chart)
    show_table(
        view[[dimension, "Faturamento", "Participação %", "Peso (kg)", "Margem", "Margem %", "Clientes", "Produtos"]],
        height=390, width="stretch", hide_index=True,
    )


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
        c1, c2, c3 = st.columns(3)
        with c1:
            show_chart(px.bar(monthly, x="Mês", y="Faturamento", title="Faturamento mensal", color_discrete_sequence=["#F36A2D"]))
        with c2:
            show_chart(px.bar(monthly, x="Mês", y="Peso", title="Peso faturado mensal (kg)", color_discrete_sequence=["#2F8FD8"]))
        with c3:
            show_chart(px.line(monthly, x="Mês", y="Margem %", markers=True, title="Margem mensal (%)", color_discrete_sequence=["#34B27B"]))

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
        show_chart(px.line(daily, x="Data", y="Faturamento", markers=True, title="Ritmo diário de faturamento"))
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
    show_chart(px.bar(team.head(30).sort_values("Participação %"), x="Participação %", y="Vendedor", orientation="h", color="Margem %", color_continuous_scale="RdYlGn", title="Participação dos vendedores"))
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
    show_chart(px.bar(result.head(20).sort_values("Δ Faturamento"), x="Δ Faturamento", y=dimension, orientation="h", title="Variação versus ano anterior"))
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
