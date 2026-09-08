"""Painel comercial simplificado, comparável e controlado por permissões."""

import html

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.analytics import group_metrics, metrics
from src.assistant import answer
from src.auth import render_user_admin


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


def _seller_view(data, show_chart, show_table, can_export):
    st.subheader("Visão por vendedor")
    view = _summary(data, "Vendedor", data["Faturamento"].sum())
    if view.empty:
        st.info("Sem vendedores no período.")
        return
    show_chart(_compact_bar(view, "Vendedor", "Vendedores por faturamento"))
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
    if "view_daily" in permissions:
        pages.append(("Performance diária", "view_daily"))
    if "view_sellers" in permissions:
        pages.append(("Vendedores", "view_sellers"))
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
    elif permission == "view_daily":
        _daily(data, history, end_date, brl, brl2, pct, show_chart, show_table)
    elif permission == "view_sellers":
        _seller_view(data, show_chart, show_table, can_export)
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
        render_user_admin(current_user)
