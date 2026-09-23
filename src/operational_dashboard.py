"""Painel comercial simplificado, comparável e controlado por permissões."""

import html
import json
import gzip
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.analytics import group_metrics, metrics
from src.assistant import answer, SUGGESTED_QUESTIONS
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
    "targets": "Compara o realizado às metas oficiais mensais. KG vem do relatório 044 no grão vendedor × grupo; o total R$ vem do relatório 045 e é conciliado nesse grão. Cliente e produto recebem alocações proporcionais ao peso faturado nos 3 meses-calendário anteriores.",
    "funnel": "A posição atual coloca cada pedido ou OP somente na etapa mais avançada já registrada, sem acumular o mesmo volume em caixas anteriores. Etapas comerciais exibem R$; operação/logística exibem kg. A aba de movimentações por data é histórica e pode registrar o mesmo documento em mais de uma etapa.",
    "heatmap": "Mostra a atividade mensal em formato de mapa de intensidade. Para cliente, positivação indica faturamento líquido mensal positivo; para produto e canal, conta clientes distintos com faturamento líquido positivo. Células cinza representam ausência de positivação ou faturamento líquido não positivo.",
    "map": "Consolida a carteira por município. Clientes totais usam o histórico até a data final; clientes ativos possuem faturamento líquido positivo no período. Potencial usa o faturamento positivo do mesmo período do ano anterior e potencial não atendido é a diferença positiva para o faturamento atual.",
    "pivot": "Agrupa os registros filtrados pelas dimensões escolhidas e soma faturamento, peso e margem; clientes são contados de forma distinta. Margem % é margem dividida pelo faturamento.",
    "unified": "Reúne, sem misturar grãos, os registros faturados, metas, eventos do funil e indicadores. Cada linha informa sua fonte; valores de meta, faturamento e funil permanecem em colunas próprias para evitar dupla contagem.",
    "yoy": "Compara o período selecionado com as mesmas datas deslocadas em um ano, preservando a duração e os filtros atuais.",
    "assistant": "Responde somente com base nos dados do período e filtros ativos; não consulta fontes externas e não altera a base.",
}


INSIGHT_HELP = {
    "reactivation": "Clientes que compraram no mesmo período do ano anterior e ainda não faturaram no período atual. O potencial é a diferença positiva entre faturamento de referência e atual.",
    "declines": "Clientes ativos nos dois períodos cuja queda de faturamento é de 20% ou mais. O potencial é a parcela necessária para recuperar o nível do ano anterior.",
    "seasonality": "Clientes cuja última compra ultrapassou 125% da cadência mediana entre compras. A cadência exige ao menos duas datas de compra e mínimo de 7 dias.",
    "mix": "Clientes ativos cujo número de produtos distintos ficou abaixo do mesmo período do ano anterior. Produtos a recuperar é a diferença entre o mix de referência e o atual.",
}


MUNICIPAL_COORDINATES = Path(__file__).resolve().parents[1] / "municipios_centroides.csv"
MUNICIPAL_GEOJSON = Path(__file__).resolve().parents[1] / "municipios_brasil.geojson.gz"
IBGE_UF_CODES = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
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
    .mf-flow{display:grid;grid-template-columns:repeat(6,minmax(150px,1fr));gap:.65rem;margin:.8rem 0 1.25rem;overflow-x:auto;padding:.2rem .05rem .65rem}
    .mf-stage{position:relative;background:#fff;border:1px solid #DCE3EC;border-top:4px solid #F36A2D;border-radius:12px;padding:.8rem;min-height:180px;box-shadow:0 3px 12px rgba(23,32,51,.05)}
    .mf-stage:not(:last-child)::after{content:"›";position:absolute;right:-.55rem;top:4.2rem;z-index:2;width:1rem;height:1rem;border-radius:50%;background:#fff;color:#F36A2D;font-size:1.35rem;font-weight:800;line-height:.78rem;text-align:center}
    .mf-stage-number{font-size:.68rem;font-weight:800;color:#C54112;text-transform:uppercase;letter-spacing:.06em}.mf-stage-title{font-size:1rem;font-weight:800;color:#172033;margin:.15rem 0 .1rem}.mf-stage-ref{font-size:.65rem;line-height:1.25;color:#718096;min-height:2.1rem;margin-bottom:.25rem}
    .mf-stage-line{border-top:1px solid #EDF1F5;padding:.42rem 0}.mf-stage-label{display:flex;align-items:flex-start;gap:.32rem;font-size:.72rem;line-height:1.25;color:#52647A}.mf-stage-value{font-size:.92rem;font-weight:800;color:#172033;margin-top:.16rem}
    .mf-stage-meta{font-size:.66rem;line-height:1.25;color:#748195;margin-top:.12rem}.mf-stage-dot{flex:0 0 auto;color:#20A36A}
    .mf-stage-line.empty .mf-stage-dot{color:#D89A20}.mf-stage-line.empty .mf-stage-value{font-size:.76rem;font-weight:650;color:#7B6A3A}
    .mf-stage-line.missing .mf-stage-dot{color:#AAB4C2}.mf-stage-line.missing .mf-stage-value{font-size:.76rem;font-weight:650;color:#8591A2}
    @media(max-width:1100px){.mf-flow{grid-template-columns:repeat(3,minmax(190px,1fr))}.mf-stage:nth-child(3)::after{display:none}}
    @media(min-width:700px) and (max-width:1400px){[data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.75rem!important}[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{flex:1 1 min(100%,260px)!important;width:auto!important;min-width:min(100%,220px)!important}}
    @media(max-width:699px){.mf-flow{grid-template-columns:repeat(6,minmax(210px,1fr))}.mf-stage:nth-child(3)::after{display:block}}
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


def _monthly_activity_matrix(history, dimension, metric, end_date, months=12, limit=20):
    """Matriz completa entidade × mês, preservando meses sem atividade como zero estrutural."""
    if history is None or history.empty or dimension not in history.columns:
        return pd.DataFrame(), pd.Series(dtype="float64")
    end = pd.Timestamp(end_date)
    end_month = end.to_period("M").start_time
    start_month = end_month - pd.DateOffset(months=max(int(months), 1) - 1)
    month_axis = pd.date_range(start_month, end_month, freq="MS")
    source = history[
        (history["Data"] >= start_month) & (history["Data"] < end + pd.Timedelta(days=1))
    ].dropna(subset=["Data", dimension]).copy()
    if source.empty:
        return pd.DataFrame(columns=month_axis), pd.Series(dtype="float64")
    source[dimension] = source[dimension].astype(str)
    source["Mês"] = source["Data"].dt.to_period("M").dt.to_timestamp()
    groups = [dimension, "Mês"]
    revenue = source.groupby(groups, dropna=False)["Faturamento"].sum()
    revenue_matrix = revenue.unstack(fill_value=0).reindex(columns=month_axis, fill_value=0)
    if metric == "Faturamento":
        matrix = revenue_matrix
        ranking = revenue_matrix.sum(axis=1)
    elif metric == "Preço médio/kg":
        weight = source.groupby(groups, dropna=False)["Peso"].sum()
        weight_matrix = weight.unstack().reindex(columns=month_axis)
        matrix = revenue_matrix.div(weight_matrix.replace(0, np.nan))
        ranking = revenue_matrix.sum(axis=1)
    elif metric == "Margem %":
        margin = source.groupby(groups, dropna=False)["Margem"].sum()
        margin_matrix = margin.unstack().reindex(columns=month_axis)
        matrix = margin_matrix.div(revenue_matrix.replace(0, np.nan))
        ranking = revenue_matrix.sum(axis=1)
    elif dimension == "Cliente":
        matrix = revenue_matrix.gt(0).astype(int)
        ranking = matrix.sum(axis=1)
    else:
        client_revenue = source.groupby([dimension, "Mês", "Cliente"], dropna=False)["Faturamento"].sum()
        positive = client_revenue.gt(0).groupby(level=[0, 1]).sum()
        matrix = positive.unstack(fill_value=0).reindex(columns=month_axis, fill_value=0).astype(int)
        ranking = matrix.sum(axis=1)
    selected = ranking.sort_values(ascending=False).head(max(int(limit), 1)).index
    matrix = matrix.reindex(selected)
    return matrix, ranking.reindex(selected)


def _short_label(value, length=30):
    value = str(value)
    return value if len(value) <= length else value[:length - 1] + "…"


def _month_label(value):
    names = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
    month = pd.Timestamp(value)
    return f"{names[month.month - 1]}/{month.strftime('%y')}"


def _activity_heatmap_chart(matrix, dimension, metric):
    display = matrix.copy()
    full_labels = [str(value) for value in display.index]
    display.index = [_short_label(value) for value in full_labels]
    display.columns = [_month_label(value) for value in display.columns]
    color_scale = [[0, "#EEF1F5"], [0.01, "#FFE2D4"], [0.48, "#F59668"], [1, "#C54112"]]
    finite_values = display.to_numpy(dtype=float)
    finite_values = finite_values[np.isfinite(finite_values)]
    positive_max = max(float(finite_values.max()), 1.0) if finite_values.size else 1.0
    labels = {
        "Faturamento": "Faturamento (R$)",
        "Preço médio/kg": "Preço médio/kg (R$)",
        "Margem %": "Margem %",
        "Positivação": "Positivação",
    }
    chart = px.imshow(
        display, aspect="auto", color_continuous_scale=color_scale,
        range_color=(0, positive_max) if metric != "Margem %" else None,
        color_continuous_midpoint=0 if metric == "Margem %" else None,
        labels={"x": "Mês", "y": dimension, "color": labels[metric]},
    )
    full_names = np.repeat(np.array(full_labels, dtype=object)[:, None], len(display.columns), axis=1)
    if metric == "Faturamento":
        hover = "<b>%{customdata}</b><br>%{x}<br>Faturamento: R$ %{z:,.2f}<extra></extra>"
        chart.update_coloraxes(colorbar_title="R$", colorbar_tickprefix="R$ ", colorbar_tickformat="~s")
    elif metric == "Preço médio/kg":
        hover = "<b>%{customdata}</b><br>%{x}<br>Preço médio/kg: R$ %{z:,.2f}<extra></extra>"
        chart.update_coloraxes(colorbar_title="R$/kg", colorbar_tickprefix="R$ ", colorbar_tickformat=".2f")
    elif metric == "Margem %":
        chart.update_coloraxes(colorscale=[[0, "#C93C3C"], [.5, "#F3F5F7"], [1, "#168553"]])
        hover = "<b>%{customdata}</b><br>%{x}<br>Margem: %{z:.2%}<extra></extra>"
        chart.update_coloraxes(colorbar_title="Margem", colorbar_tickformat=".2%")
    else:
        unit = "Clientes positivados" if dimension != "Cliente" else "Positivado"
        hover = f"<b>%{{customdata}}</b><br>%{{x}}<br>{unit}: %{{z:,.0f}}<extra></extra>"
        text = np.where(display.to_numpy() > 0, "●", "")
        chart.update_traces(text=text, texttemplate="%{text}", textfont=dict(color="#7B2B11", size=11))
        chart.update_coloraxes(colorbar_title="Clientes" if dimension != "Cliente" else "Ativo")
    chart.update_traces(customdata=full_names, hovertemplate=hover, xgap=4, ygap=4)
    _polish_chart(chart, height=max(300, 30 * len(display) + 145), x_title="", y_title="")
    chart.update_layout(
        title=f"{metric} mensal por {dimension.lower()}",
        margin=dict(l=155, r=40, t=58, b=52),
        coloraxis_colorbar=dict(thickness=12, len=.72),
    )
    chart.update_xaxes(side="top", showgrid=False, tickangle=0)
    chart.update_yaxes(showgrid=False, autorange="reversed")
    return chart


def _monthly_activity_view(history, end_date, brl, show_chart, show_table, can_export):
    st.subheader("Mapa mensal de atividade", help=PANEL_HELP["heatmap"])
    st.caption("Visual em formato batalha naval: cada célula representa uma entidade em um mês. A janela termina na data final selecionada e respeita todos os filtros laterais.")
    controls = st.columns([1.35, 1, 1])
    metric = controls[0].segmented_control(
        "Indicador", ["Positivação", "Faturamento", "Preço médio/kg", "Margem %"],
        default="Positivação", key="activity_metric",
    )
    months = controls[1].selectbox("Janela", [6, 12, 18, 24], index=1, format_func=lambda value: f"{value} meses", key="activity_months")
    limit = controls[2].selectbox("Entidades", [10, 15, 20, 30, 50], index=2, format_func=lambda value: f"Top {value}", key="activity_limit")
    tabs = st.tabs(["Clientes", "Produtos", "Canais"])
    for tab, (label, dimension) in zip(tabs, (("Clientes", "Cliente"), ("Produtos", "Produto"), ("Canais", "Canal"))):
        with tab:
            if dimension not in history.columns:
                st.info(f"A dimensão {dimension.lower()} não está disponível na base atual.")
                continue
            matrix, _ = _monthly_activity_matrix(history, dimension, metric, end_date, months, limit)
            if matrix.empty:
                st.info("Sem dados para montar o mapa mensal com os filtros atuais.")
                continue
            positive_cells = int(
                matrix.notna().sum().sum()
                if metric in {"Preço médio/kg", "Margem %"}
                else (matrix > 0).sum().sum()
            )
            total_cells = int(matrix.size)
            latest = matrix.iloc[:, -1]
            summary = st.columns(3)
            summary[0].metric("Entidades exibidas", _quantity(len(matrix)))
            summary[1].metric("Células com atividade", f"{positive_cells / total_cells * 100:.2f}%".replace(".", ","))
            if metric == "Faturamento":
                summary[2].metric("Último mês", brl(float(latest.sum())))
            elif metric in {"Preço médio/kg", "Margem %"}:
                latest_month = pd.Timestamp(matrix.columns[-1])
                latest_source = history[
                    (history["Data"].dt.to_period("M").dt.to_timestamp() == latest_month)
                    & history[dimension].astype(str).isin(matrix.index.astype(str))
                ]
                revenue = float(latest_source["Faturamento"].sum())
                if metric == "Preço médio/kg":
                    weight = float(latest_source["Peso"].sum())
                    value = revenue / weight if weight else 0
                    summary[2].metric("Preço médio no último mês", brl(value))
                else:
                    margin = float(latest_source["Margem"].sum())
                    value = margin / revenue if revenue else 0
                    summary[2].metric("Margem no último mês", f"{value * 100:.2f}%".replace(".", ","))
            elif dimension == "Cliente":
                summary[2].metric("Positivados no último mês", _quantity(int(latest.sum())))
            else:
                summary[2].metric("Soma de positivação no último mês", _quantity(int(latest.sum())), help="Soma por entidade; o mesmo cliente pode comprar mais de um produto ou canal.")
            show_chart(_activity_heatmap_chart(matrix, dimension, metric))
            st.caption(
                "ⓘ Cliente positivado = faturamento líquido mensal maior que zero. "
                + ("As células mostram 1 para mês positivado e cinza para mês sem positivação." if dimension == "Cliente" and metric == "Positivação" else
                   "As células mostram clientes distintos positivados em cada mês." if metric == "Positivação" else
                   "Preço médio é o faturamento dividido pelo peso faturado; células sem peso ficam vazias." if metric == "Preço médio/kg" else
                   "Margem % é a margem em reais dividida pelo faturamento; a escala separa margens negativas e positivas." if metric == "Margem %" else
                   "A intensidade representa o faturamento líquido positivo do mês; células cinza incluem valores zerados ou negativos. Valores exatos aparecem ao tocar ou passar o cursor.")
            )
            with st.expander("Conferir valores do mapa"):
                exact = matrix.copy()
                exact.columns = [pd.Timestamp(column).strftime("%m/%Y") for column in exact.columns]
                exact.index.name = dimension
                exact = exact.reset_index()
                show_table(exact, height=520, width="stretch", hide_index=True)
                if can_export:
                    st.download_button(
                        f"Exportar mapa de {label.lower()}",
                        exact.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                        f"mapa_mensal_{dimension.lower()}.csv", "text/csv", key=f"export_activity_{dimension}_{metric}",
                        width="stretch",
                    )


def _geo_key(value):
    text = unicodedata.normalize("NFKD", "" if pd.isna(value) else str(value))
    return "".join(character for character in text if not unicodedata.combining(character)).strip().upper()


@st.cache_data(show_spinner=False)
def _municipal_coordinates():
    """Códigos e centroides públicos usados para conciliar município, UF e malha."""
    if not MUNICIPAL_COORDINATES.exists():
        return pd.DataFrame(columns=["_municipio_key", "UF", "Código IBGE", "Latitude", "Longitude"])
    coordinates = pd.read_csv(
        MUNICIPAL_COORDINATES,
        usecols=["codigo_ibge", "nome", "latitude", "longitude", "codigo_uf"],
        dtype={"codigo_ibge": "string"},
    ).rename(columns={
        "codigo_ibge": "Código IBGE", "latitude": "Latitude", "longitude": "Longitude",
    })
    coordinates["Código IBGE"] = coordinates["Código IBGE"].str.replace(r"\.0$", "", regex=True).str.zfill(7)
    coordinates["UF"] = pd.to_numeric(coordinates["codigo_uf"], errors="coerce").map(IBGE_UF_CODES)
    coordinates["_municipio_key"] = coordinates["nome"].map(_geo_key)
    return coordinates[["_municipio_key", "UF", "Código IBGE", "Latitude", "Longitude"]].dropna()


@st.cache_data(show_spinner=False)
def _municipal_geojson():
    """Malha municipal pública; nunca contém dados comerciais ou credenciais."""
    if not MUNICIPAL_GEOJSON.exists():
        return {"type": "FeatureCollection", "features": []}
    with gzip.open(MUNICIPAL_GEOJSON, "rt", encoding="utf-8") as source:
        return json.load(source)


def _municipal_color_settings(frame, selected):
    """Escala legível e robusta a outliers, preservando o valor real no hover."""
    values = pd.to_numeric(frame[selected], errors="coerce")
    finite = values[np.isfinite(values)]
    if finite.empty:
        return [[0, "#6BAED6"], [1, "#08306B"]], None, None
    if selected == "Margem %":
        limit = float(finite.abs().quantile(.95))
        limit = limit if np.isfinite(limit) and limit > 0 else max(float(finite.abs().max()), .01)
        scale = [[0, "#8E1421"], [.42, "#E6614C"], [.5, "#F4D35E"], [.58, "#5DBB73"], [1, "#075B32"]]
        return scale, (-limit, limit), 0
    upper = float(finite.quantile(.95))
    upper = upper if np.isfinite(upper) and upper > 0 else max(float(finite.max()), 1.0)
    # O primeiro tom já é deliberadamente mais escuro que o fundo do painel.
    scale = [[0, "#74B9D8"], [.28, "#3D8EBC"], [.58, "#1C6397"], [.82, "#0B3E6F"], [1, "#041F3D"]]
    return scale, (0, upper), None


def _municipal_map_data(current, history, start_date, end_date):
    """Consolida a carteira municipal sem multiplicar clientes ou percentuais."""
    required = {"Data", "Cliente", "UF", "Município", "Faturamento", "Peso", "Margem"}
    if current is None or history is None or history.empty or not required.issubset(history.columns):
        return pd.DataFrame()
    until_end = history[history["Data"] < pd.Timestamp(end_date) + pd.Timedelta(days=1)].copy()
    until_end = until_end.dropna(subset=["Cliente"]).sort_values("Data")
    if until_end.empty:
        return pd.DataFrame()
    locations = until_end.groupby("Cliente", dropna=False).agg(
        UF=("UF", "last"), Município=("Município", "last"),
    ).reset_index()
    current_client = current.groupby("Cliente", dropna=False).agg(
        Faturamento=("Faturamento", "sum"), Peso=("Peso", "sum"), Margem=("Margem", "sum"),
    ).reset_index()
    reference = _shifted_period(history, start_date, end_date, years=1)
    reference_client = reference.groupby("Cliente", dropna=False)["Faturamento"].sum().rename("Faturamento referência").reset_index()
    clients = locations.merge(current_client, on="Cliente", how="left").merge(reference_client, on="Cliente", how="left")
    for column in ("Faturamento", "Peso", "Margem", "Faturamento referência"):
        clients[column] = pd.to_numeric(clients[column], errors="coerce").fillna(0.0)
    clients["Cliente ativo"] = clients["Faturamento"].gt(0).astype(int)
    clients["Potencial R$"] = clients["Faturamento referência"].clip(lower=0)
    clients["Potencial não atendido R$"] = clients["Faturamento referência"].sub(clients["Faturamento"]).clip(lower=0)
    result = clients.groupby(["UF", "Município"], dropna=False).agg(
        **{
            "Clientes totais": ("Cliente", "nunique"),
            "Clientes ativos": ("Cliente ativo", "sum"),
            "Faturamento": ("Faturamento", "sum"),
            "KG faturado": ("Peso", "sum"),
            "Margem R$": ("Margem", "sum"),
            "Potencial R$": ("Potencial R$", "sum"),
            "Potencial não atendido R$": ("Potencial não atendido R$", "sum"),
        }
    ).reset_index()
    result["Taxa de ativação"] = result["Clientes ativos"].div(result["Clientes totais"].replace(0, np.nan))
    result["Preço médio/kg"] = result["Faturamento"].div(result["KG faturado"].replace(0, np.nan))
    result["Margem %"] = result["Margem R$"].div(result["Faturamento"].replace(0, np.nan))
    return result.sort_values(["Potencial não atendido R$", "Faturamento"], ascending=False)


def _attach_municipal_coordinates(frame, coordinates=None):
    if frame.empty:
        return frame.copy()
    coordinates = _municipal_coordinates() if coordinates is None else coordinates.copy()
    result = frame.copy()
    result["_municipio_key"] = result["Município"].map(_geo_key)
    result["UF"] = result["UF"].astype(str).str.strip().str.upper()
    return result.merge(coordinates, on=["_municipio_key", "UF"], how="left")


def _municipal_map_view(current, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export):
    st.subheader("Mapa comercial por município", help=PANEL_HELP["map"])
    st.caption(
        f"{pd.Timestamp(start_date).strftime('%d/%m/%Y')} a {pd.Timestamp(end_date).strftime('%d/%m/%Y')} • "
        "cada região representa um município e a intensidade da cor representa a medida selecionada."
    )
    municipal = _municipal_map_data(current, history, start_date, end_date)
    if municipal.empty:
        st.info("Não há dados municipais disponíveis com os filtros atuais.")
        return
    metrics = [
        "Faturamento", "Clientes totais", "Clientes ativos", "Taxa de ativação",
        "Potencial R$", "Potencial não atendido R$", "KG faturado", "Preço médio/kg", "Margem %",
    ]
    selected = st.selectbox("Medida do mapa", metrics, index=5, key="municipal_map_metric")
    cards = st.columns(4)
    cards[0].metric("Municípios", _quantity(municipal[["UF", "Município"]].drop_duplicates().shape[0]))
    cards[1].metric("Clientes totais", _quantity(municipal["Clientes totais"].sum()))
    cards[2].metric("Clientes ativos", _quantity(municipal["Clientes ativos"].sum()))
    cards[3].metric("Potencial não atendido", brl(float(municipal["Potencial não atendido R$"].sum())))

    plotted = _attach_municipal_coordinates(municipal)
    mapped = plotted.dropna(subset=["Código IBGE", "Latitude", "Longitude"]).copy()
    coverage = len(mapped) / len(plotted) if len(plotted) else 0
    if mapped.empty:
        st.warning("Nenhum município da seleção foi reconhecido na malha geográfica. Use a tabela abaixo para conferir os nomes publicados na base.")
    else:
        geojson = _municipal_geojson()
        mapped_ids = set(mapped["Código IBGE"].astype(str))
        features = [
            feature for feature in geojson.get("features", [])
            if str(feature.get("properties", {}).get("id", "")) in mapped_ids
        ]
        available_ids = {str(feature.get("properties", {}).get("id", "")) for feature in features}
        mapped = mapped[mapped["Código IBGE"].astype(str).isin(available_ids)].copy()
        coverage = len(mapped) / len(plotted) if len(plotted) else 0
        if mapped.empty:
            st.warning("Os municípios foram identificados, mas seus polígonos não estão disponíveis na malha do mapa.")
            features = []
        regional_geojson = {"type": "FeatureCollection", "features": features}
        mapped["Local"] = mapped["Município"].astype(str) + " / " + mapped["UF"].astype(str)
        mapped["Faturamento exibido"] = mapped["Faturamento"].map(brl2)
        mapped["Potencial exibido"] = mapped["Potencial R$"].map(brl2)
        mapped["Não atendido exibido"] = mapped["Potencial não atendido R$"].map(brl2)
        mapped["Ativação exibida"] = mapped["Taxa de ativação"].map(pct)
        mapped["Margem exibida"] = mapped["Margem %"].map(pct)
        mapped["Preço exibido"] = mapped["Preço médio/kg"].map(lambda value: brl2(value) if pd.notna(value) else "—")
        custom = [
            "Clientes totais", "Clientes ativos", "Faturamento exibido", "Potencial exibido",
            "Não atendido exibido", "Ativação exibida", "Margem exibida", "Preço exibido",
        ]
        if features:
            color_scale, color_range, color_midpoint = _municipal_color_settings(mapped, selected)
            center = {"lat": float(mapped["Latitude"].mean()), "lon": float(mapped["Longitude"].mean())}
            zoom = 7 if len(mapped) == 1 else 5 if mapped["UF"].nunique() == 1 else 3.2
            chart = px.choropleth_map(
                mapped, geojson=regional_geojson, locations="Código IBGE",
                featureidkey="properties.id", color=selected, hover_name="Local", custom_data=custom,
                color_continuous_scale=color_scale, range_color=color_range,
                color_continuous_midpoint=color_midpoint, zoom=zoom, center=center,
                map_style="carto-positron", opacity=.88, title=f"{selected} por município",
            )
            chart.update_traces(
                marker_line_color="#FFFFFF", marker_line_width=1.05,
                hovertemplate=(
                    "<b>%{hovertext}</b><br>Clientes totais: %{customdata[0]:,.0f}"
                    "<br>Clientes ativos: %{customdata[1]:,.0f}<br>Faturamento: %{customdata[2]}"
                    "<br>Potencial: %{customdata[3]}<br>Potencial não atendido: %{customdata[4]}"
                    "<br>Taxa de ativação: %{customdata[5]}<br>Margem: %{customdata[6]}"
                    "<br>Preço médio/kg: %{customdata[7]}<extra></extra>"
                ),
            )
            chart.update_layout(
                height=610, margin=dict(l=8, r=8, t=58, b=8),
                coloraxis_colorbar=dict(title=selected, thickness=14, bgcolor="rgba(255,255,255,.88)"),
            )
            if selected in {"Faturamento", "Potencial R$", "Potencial não atendido R$", "Preço médio/kg"}:
                chart.update_coloraxes(colorbar_tickprefix="R$ ", colorbar_tickformat=",.2f")
            elif selected in {"Taxa de ativação", "Margem %"}:
                chart.update_coloraxes(colorbar_tickformat=".2%")
            else:
                chart.update_coloraxes(colorbar_tickformat=",.0f")
            show_chart(chart)
            st.caption(
                f"Cobertura geográfica: {coverage:.2%}".replace(".", ",")
                + " dos municípios exibidos possuem região reconhecida. A escala limita a influência dos 5% maiores valores apenas na cor; os valores exatos permanecem no detalhe e no hover."
            )

    detail_columns = [
        "UF", "Município", "Clientes totais", "Clientes ativos", "Taxa de ativação", "Faturamento",
        "Potencial R$", "Potencial não atendido R$", "KG faturado", "Preço médio/kg", "Margem %",
    ]
    detail = municipal[detail_columns].sort_values(selected, ascending=False, na_position="last")
    with st.expander("Detalhamento municipal", expanded=bool(mapped.empty)):
        show_table(detail, height=520, width="stretch", hide_index=True)
        if can_export:
            st.download_button(
                "Exportar visão municipal", detail.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                "mapa_municipal.csv", "text/csv", key="export_municipal_map", width="stretch",
            )
    st.caption(
        "ⓘ Potencial = faturamento positivo do mesmo período do ano anterior. "
        "Potencial não atendido = diferença positiva entre esse valor e o faturamento atual. "
        "Clientes sem histórico no período de referência podem ter potencial igual a zero."
    )


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
    st.subheader("Command Center", help=PANEL_HELP["overview"])
    st.caption(
        f"Visão central do METALFORTE 360 • {pd.Timestamp(start_date).strftime('%d/%m/%Y')} a {pd.Timestamp(end_date).strftime('%d/%m/%Y')} • "
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


def _unified_table(data, targets, flow_events, indicators, start_date, end_date):
    """Cria uma consulta única preservando a origem e o grão de cada fato."""
    frames = []
    sales = data.copy()
    if not sales.empty:
        sales.insert(0, "Fonte", "Faturamento")
        sales.insert(1, "Tipo de registro", "Nota faturada")
        sales.insert(2, "Data de referência", sales.get("Data"))
        sales = sales.rename(columns={
            "Data": "Data faturamento", "Peso": "Peso faturado (kg)",
            "Margem": "Margem (R$)", "Margem %": "Margem faturamento %",
        })
        frames.append(sales)

    flow = flow_events.copy() if flow_events is not None else pd.DataFrame()
    if not flow.empty:
        date_columns = [column for column in flow.columns if str(column).startswith("Data ")]
        if date_columns:
            period_start, period_end = pd.Timestamp(start_date), pd.Timestamp(end_date)
            in_period = flow[date_columns].apply(lambda series: series.between(period_start, period_end, inclusive="both")).any(axis=1)
            flow = flow.loc[in_period].copy()
        if not flow.empty:
            flow.insert(0, "Fonte", "Funil")
            flow.insert(1, "Tipo de registro", flow.get("Origem", pd.Series("Evento do funil", index=flow.index)).fillna("Evento do funil"))
            flow.insert(2, "Data de referência", flow[date_columns].max(axis=1) if date_columns else pd.NaT)
            flow = flow.rename(columns={"Peso": "Peso funil (kg)", "Valor": "Valor funil (R$)"})
            frames.append(flow)

    target_frame = targets.copy() if targets is not None else pd.DataFrame()
    if not target_frame.empty and "Competência" in target_frame:
        target_frame["Competência"] = pd.to_datetime(target_frame["Competência"], errors="coerce")
        target_frame = target_frame[target_frame["Competência"].between(pd.Timestamp(start_date).to_period("M").start_time, pd.Timestamp(end_date).to_period("M").end_time, inclusive="both")].copy()
        if not target_frame.empty:
            target_frame.insert(0, "Fonte", "Meta oficial")
            target_frame.insert(1, "Tipo de registro", "Meta mensal")
            target_frame.insert(2, "Data de referência", target_frame["Competência"])
            target_frame = target_frame.rename(columns={"Meta R$": "Meta (R$)", "Meta KG": "Meta (kg)"})
            frames.append(target_frame)

    snapshot = []
    for metric, value in (indicators or {}).items():
        if value is None:
            continue
        metric_name = str(metric).replace("_", " ").title()
        is_weight = "peso" in str(metric).lower() or "kg" in str(metric).lower()
        snapshot.append({
            "Fonte": "Indicador", "Tipo de registro": "Fotografia da última carga",
            "Data de referência": pd.Timestamp(end_date), "Métrica": metric_name,
            "Indicador (kg)" if is_weight else "Indicador (R$)": value,
        })
    if snapshot:
        frames.append(pd.DataFrame(snapshot))
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _unified_view(data, targets, flow_events, indicators, start_date, end_date, show_table, can_export):
    st.subheader("Base unificada", help=PANEL_HELP["unified"])
    st.caption("Recorte do período e dos filtros ativos. As fontes não são somadas entre si: use a coluna Fonte para interpretar cada registro.")
    unified = _unified_table(data, targets, flow_events, indicators, start_date, end_date)
    if unified.empty:
        st.info("Não há registros nas fontes disponíveis para o recorte selecionado.")
        return
    source_options = unified["Fonte"].dropna().unique().tolist()
    selected_sources = st.multiselect("Fontes incluídas", source_options, default=source_options, key="unified_sources")
    result = unified[unified["Fonte"].isin(selected_sources)].copy()
    core = [
        "Fonte", "Tipo de registro", "Data de referência", "Data faturamento", "Competência",
        "Pedido", "NF", "OP", "Vendedor", "Cliente", "Segmento Cliente", "Grupo Produto", "Produto",
        "Faturamento", "Peso faturado (kg)", "Margem (R$)", "Margem faturamento %",
        "Meta (R$)", "Meta (kg)", "Valor funil (R$)", "Peso funil (kg)", "Métrica", "Indicador (R$)", "Indicador (kg)",
    ]
    available_core = [column for column in core if column in result.columns]
    show_all = st.checkbox("Exibir todos os campos disponíveis", value=False, key="unified_all_fields")
    visible_columns = list(result.columns) if show_all else available_core
    max_rows = st.select_slider("Linhas exibidas", options=[250, 500, 1_000, 2_500, 5_000, 10_000], value=2_500, key="unified_rows")
    st.caption(f"{len(result):,} registros no recorte • exibindo até {min(len(result), max_rows):,}.".replace(",", "."))
    sort_columns = [column for column in ("Data de referência", "Fonte", "Tipo de registro") if column in result]
    if sort_columns:
        result = result.sort_values(sort_columns, ascending=[False] + [True] * (len(sort_columns) - 1), na_position="last")
    show_table(result[visible_columns].head(max_rows), height=620, width="stretch", hide_index=True)
    if can_export:
        st.download_button(
            "Exportar recorte completo", result.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "base_unificada_metalforte.csv", "text/csv", width="stretch",
        )


def _yoy(data, history, start_date, end_date, show_chart, show_table):
    st.subheader("Comparativo com o ano anterior", help=PANEL_HELP["yoy"])
    dimensions = [column for column in ("Vendedor", "Cliente", "Grupo Produto", "UF", "Município") if column in data.columns]
    dimension = st.selectbox("Analisar por", dimensions, key="yoy_dimension")
    previous = _shifted_period(history, start_date, end_date, years=1)
    current_view = _summary(data, dimension, data["Faturamento"].sum()).set_index(dimension)
    prior_view = _summary(previous, dimension, previous["Faturamento"].sum()).set_index(dimension)
    result = current_view[["Faturamento", "Margem %", "Preço médio/kg", "Clientes positivados"]].join(
        prior_view[["Faturamento", "Margem %", "Preço médio/kg", "Clientes positivados"]], how="outer", lsuffix=" atual", rsuffix=" ano anterior"
    ).reset_index()
    additive_columns = [
        "Faturamento atual", "Faturamento ano anterior",
        "Clientes positivados atual", "Clientes positivados ano anterior",
    ]
    result[additive_columns] = result[additive_columns].fillna(0)
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
            "Este detalhamento é uma alocação gerencial: Meta R$ e Meta KG usam a participação do peso faturado nos 3 meses-calendário anteriores à competência, dentro de cada vendedor × grupo."
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


FUNNEL_JOURNEY = ("Orçamento", "Crédito", "Produção", "Carga", "Faturamento", "Entrega")
FUNNEL_STAGES = (
    ("Orçamento", "Comercial", "Orçamentos em aberto", "orcamentos_abertos_valor", "R$", False),
    ("Orçamento", "Comercial", "Orçamentos fechados", "orcamentos_fechados_valor", "R$", False),
    ("Orçamento", "Comercial", "Orçamentos perdidos", "orcamentos_perdidos_valor", "R$", False),
    ("Crédito", "Comercial", "Pedidos aguardando crédito", "pedidos_pendentes_valor", "R$", False),
    ("Crédito", "Comercial", "Crédito liberado", "pedidos_liberados_credito_valor", "R$", False),
    ("Produção", "Operação", "Aguardando OS", "aguardando_os_peso", "kg", False),
    ("Produção", "Operação", "Aguardando kit", "aguardando_kit_peso", "kg", False),
    ("Carga", "Operação", "Aguardando carga CIF", "aguardando_carga_cif_peso", "kg", False),
    ("Carga", "Operação", "Aguardando carga FOB", "aguardando_carga_fob_peso", "kg", False),
    ("Faturamento", "Operação", "Aguardando faturamento", "aguardando_faturamento_peso", "kg", False),
    ("Faturamento", "Operação", "Aguardando faturamento CIF", "aguardando_faturamento_cif_peso", "kg", True),
    ("Faturamento", "Operação", "Aguardando faturamento FOB", "aguardando_faturamento_fob_peso", "kg", True),
    ("Faturamento", "Comercial", "Faturado no período", "pedidos_faturados_valor", "R$", False),
    ("Entrega", "Operação", "Aguardando entrega", "aguardando_entrega_peso", "kg", False),
    ("Entrega", "Operação", "Entregue", "entregue_peso", "kg", False),
)
FUNNEL_DATE_REFERENCES = {
    "Orçamento": "Data do orçamento",
    "Crédito": "Data do pedido e da liberação",
    "Produção": "Data da OP, produção e OS",
    "Carga": "Data da montagem da carga",
    "Faturamento": "Data de emissão da NF",
    "Entrega": "Data de saída e previsão de entrega",
}
FLOW_DATE_EVENTS = (
    ("Orçamento", "Orçamentos emitidos", "Data Orçamento"),
    ("Crédito", "Pedidos emitidos", "Data Pedido"),
    ("Crédito", "Pedidos liberados", "Data Liberação"),
    ("Produção", "OP emitidas", "Data Emissão OP"),
    ("Produção", "OP confirmadas", "Data Confirmação OP"),
    ("Produção", "Produção programada", "Data Produção"),
    ("Produção", "Ordens de serviço", "Data OS"),
    ("Carga", "Cargas montadas", "Data Montagem Carga"),
    ("Faturamento", "Notas fiscais emitidas", "Data Emissão NF"),
    ("Entrega", "Saídas realizadas", "Data Saída"),
    ("Entrega", "Entregas previstas", "Data Previsão Entrega"),
    ("Entrega", "Data desejada pelo cliente", "Data Desejo Cliente"),
)

# A posição da carteira usa somente fatos concluídos do processo. Datas de
# desejo e de previsão são compromissos, não movimentações do pedido.
# Cada pedido/OP fica em uma única etapa: a mais avançada já registrada.
CURRENT_POSITION_STAGES = (
    (1, "Orçamento", "Orçamento em aberto", "Data Orçamento"),
    (2, "Crédito", "Pedido emitido", "Data Pedido"),
    (3, "Crédito", "Pedido liberado", "Data Liberação"),
    (4, "Produção", "OP emitida", "Data Emissão OP"),
    (5, "Produção", "OP confirmada", "Data Confirmação OP"),
    (6, "Produção", "Produção programada", "Data Produção"),
    (7, "Produção", "OS gerada", "Data OS"),
    (8, "Carga", "Carga montada", "Data Montagem Carga"),
    (9, "Faturamento", "NF emitida", "Data Emissão NF"),
    (10, "Entrega", "Saída realizada", "Data Saída"),
)

POSITION_FALLBACKS = {
    "Orçamento em aberto": (1, "Orçamento", "Orçamento em aberto"),
    "Pedido liberado": (3, "Crédito", "Pedido liberado"),
    "OP sob encomenda": (4, "Produção", "OP emitida"),
}


def _funnel_frame(indicators):
    indicators = indicators or {}
    rows = []
    for sequence, (journey, flow, stage, key, unit, subtotal) in enumerate(FUNNEL_STAGES, start=1):
        raw = indicators.get(key)
        try:
            value = float(raw) if raw is not None and not pd.isna(raw) else np.nan
        except (TypeError, ValueError):
            value = np.nan
        rows.append({
            "Ordem": sequence, "Macroetapa": journey, "Fluxo": flow, "Etapa": stage, "Chave": key,
            "Unidade": unit, "Valor": value, "Cobertura": "Disponível" if pd.notna(value) else "Indisponível",
            "É subtotal": subtotal,
        })
    return pd.DataFrame(rows)


def _flow_current_positions(flow):
    """Localiza cada pedido/OP na última etapa concluída, sem duplicá-lo."""
    position_columns = [
        "Documento", "Origem", "Ordem", "Macroetapa", "Etapa", "Data da posição",
        "Registros", "Peso", "Valor",
    ]
    summary_columns = [
        "Ordem", "Macroetapa", "Etapa", "Documentos", "Registros", "Peso", "Valor", "Data mais recente",
    ]
    if flow is None or flow.empty:
        return pd.DataFrame(columns=position_columns), pd.DataFrame(columns=summary_columns)

    source = flow.copy().reset_index(drop=True)
    for column, default in (("Origem", "Não informado"), ("Peso", np.nan), ("Valor", np.nan)):
        if column not in source:
            source[column] = default
    source["_ordem"] = 0
    source["_macroetapa"] = pd.NA
    source["_etapa"] = pd.NA
    source["_data_posicao"] = pd.NaT
    for order, journey, stage, date_column in CURRENT_POSITION_STAGES:
        if date_column not in source:
            continue
        dates = pd.to_datetime(source[date_column], errors="coerce")
        moved = dates.notna()
        # A ordem do processo é a regra de desempate: uma etapa posterior
        # sempre substitui uma anterior, mesmo se a fonte registrar datas fora
        # da sequência esperada.
        source.loc[moved, "_ordem"] = order
        source.loc[moved, "_macroetapa"] = journey
        source.loc[moved, "_etapa"] = stage
        source.loc[moved, "_data_posicao"] = dates[moved]

    origins = source.get("Origem", pd.Series("", index=source.index)).fillna("").astype(str)
    for origin, (order, journey, stage) in POSITION_FALLBACKS.items():
        fallback = source["_ordem"].eq(0) & origins.eq(origin)
        source.loc[fallback, "_ordem"] = order
        source.loc[fallback, "_macroetapa"] = journey
        source.loc[fallback, "_etapa"] = stage

    # Orçamentos e pedidos têm chave pelo pedido; OPs sem vínculo confiável
    # usam sua própria chave. Linhas sem chave permanecem separadas para não
    # forçar uma união artificial entre documentos distintos.
    pedido = source.get("Pedido", pd.Series(pd.NA, index=source.index)).astype("string").str.strip()
    op = source.get("OP", pd.Series(pd.NA, index=source.index)).astype("string").str.strip()
    invalid = {"", "<NA>", "nan", "None"}
    document = pedido.where(~pedido.isin(invalid), op)
    document = document.where(~document.isin(invalid), "LINHA-" + source.index.astype(str))
    source["_documento"] = document.astype(str)

    # Se um pedido tem mais de um item, todo o volume é mantido junto na
    # posição mais avançada encontrada entre seus itens.
    selected = (
        source.sort_values(["_documento", "_ordem", "_data_posicao"], na_position="first")
        .groupby("_documento", as_index=False, sort=False)
        .tail(1)
        .set_index("_documento")
    )
    totals = source.groupby("_documento", dropna=False).agg(
        Origem=("Origem", "last"), Registros=("_documento", "size"),
        Peso=("Peso", lambda values: pd.to_numeric(values, errors="coerce").sum(min_count=1)),
        Valor=("Valor", lambda values: pd.to_numeric(values, errors="coerce").sum(min_count=1)),
    )
    positions = selected[["_ordem", "_macroetapa", "_etapa", "_data_posicao"]].join(totals, how="left").reset_index()
    positions = positions.rename(columns={
        "_documento": "Documento", "_ordem": "Ordem", "_macroetapa": "Macroetapa",
        "_etapa": "Etapa", "_data_posicao": "Data da posição",
    })
    positions = positions[positions["Ordem"].gt(0)].copy()
    if positions.empty:
        return pd.DataFrame(columns=position_columns), pd.DataFrame(columns=summary_columns)

    positions["Data da posição"] = pd.to_datetime(positions["Data da posição"], errors="coerce")
    summary = positions.groupby(["Ordem", "Macroetapa", "Etapa"], as_index=False, dropna=False).agg(
        Documentos=("Documento", "nunique"), Registros=("Registros", "sum"),
        Peso=("Peso", lambda values: pd.to_numeric(values, errors="coerce").sum(min_count=1)),
        Valor=("Valor", lambda values: pd.to_numeric(values, errors="coerce").sum(min_count=1)),
        **{"Data mais recente": ("Data da posição", "max")},
    ).sort_values("Ordem")
    return positions[position_columns], summary[summary_columns]


def _position_stage_cards(position_summary, brl):
    cards = []
    for stage_number, journey in enumerate(FUNNEL_JOURNEY, start=1):
        lines = []
        stage_rows = position_summary[position_summary["Macroetapa"] == journey] if not position_summary.empty else pd.DataFrame()
        if stage_rows.empty:
            lines.append('<div class="mf-stage-line empty"><div class="mf-stage-value">Sem pedidos nesta posição</div></div>')
        else:
            for _, row in stage_rows.iterrows():
                values = []
                if pd.notna(row.get("Valor")):
                    values.append(brl(float(row["Valor"])))
                if pd.notna(row.get("Peso")):
                    values.append(f"{_quantity(float(row['Peso']))} kg")
                formatted = " · ".join(values) if values else f"{_quantity(row['Registros'])} registros"
                meta = f"{int(row['Documentos'])} documento(s) · {int(row['Registros'])} linha(s)"
                lines.append(
                    '<div class="mf-stage-line">'
                    f'<div class="mf-stage-label"><span class="mf-stage-dot">●</span><span>{html.escape(str(row["Etapa"]))}</span></div>'
                    f'<div class="mf-stage-value">{html.escape(formatted)}</div>'
                    f'<div class="mf-stage-meta">{html.escape(meta)}</div></div>'
                )
        cards.append(
            f'<section class="mf-stage"><div class="mf-stage-number">Etapa {stage_number:02d}</div>'
            f'<div class="mf-stage-title">{html.escape(journey)}</div>'
            '<div class="mf-stage-ref">Posição atual da última carga</div>'
            f'{"".join(lines)}</section>'
        )
    st.markdown('<div class="mf-flow">' + "".join(cards) + '</div>', unsafe_allow_html=True)


def _funnel_stage_cards(date_summary, brl):
    cards = []
    for stage_number, journey in enumerate(FUNNEL_JOURNEY, start=1):
        lines = []
        stage_events = date_summary[date_summary["Macroetapa"] == journey] if not date_summary.empty else pd.DataFrame()
        if stage_events.empty:
            stage_events = pd.DataFrame([{
                "Movimentação": "Eventos da etapa", "Situação": "Data não publicada",
                "Registros": np.nan, "Documentos": np.nan, "Peso": np.nan, "Valor": np.nan,
            }])
        for _, row in stage_events.iterrows():
            situation = row["Situação"]
            if situation == "Data não publicada":
                css_class, dot, formatted, meta = "missing", "○", "Data não publicada", ""
            elif situation == "Sem movimento no período":
                css_class, dot, formatted, meta = "empty", "○", "Sem movimento no período", ""
            else:
                css_class, dot = "", "●"
                value, weight = row.get("Valor"), row.get("Peso")
                if journey in {"Orçamento", "Crédito", "Faturamento"} and pd.notna(value):
                    formatted = brl(float(value))
                elif pd.notna(weight):
                    formatted = f"{_quantity(float(weight))} kg"
                else:
                    formatted = f"{_quantity(float(row['Registros']))} registros"
                documents = int(row["Documentos"]) if pd.notna(row.get("Documentos")) else 0
                records = int(row["Registros"]) if pd.notna(row.get("Registros")) else 0
                meta = f"{documents} documento(s) · {records} registro(s)"
            lines.append(
                f'<div class="mf-stage-line {css_class}">'
                f'<div class="mf-stage-label"><span class="mf-stage-dot">{dot}</span>'
                f'<span>{html.escape(str(row["Movimentação"]))}</span></div>'
                f'<div class="mf-stage-value">{html.escape(formatted)}</div>'
                f'{f"<div class=\"mf-stage-meta\">{html.escape(meta)}</div>" if meta else ""}</div>'
            )
        cards.append(
            f'<section class="mf-stage"><div class="mf-stage-number">Etapa {stage_number:02d}</div>'
            f'<div class="mf-stage-title">{html.escape(journey)}</div>'
            f'<div class="mf-stage-ref">Referência: {html.escape(FUNNEL_DATE_REFERENCES[journey])}</div>'
            f'{"".join(lines)}</section>'
        )
    st.markdown('<div class="mf-flow">' + "".join(cards) + '</div>', unsafe_allow_html=True)


def _funnel_chart(frame, title, unit):
    available = frame[(frame["Unidade"] == unit) & frame["Valor"].notna() & ~frame["É subtotal"]].copy()
    if available.empty:
        return None
    available = available.sort_values("Ordem", ascending=False)
    chart = px.bar(
        available, x="Valor", y="Etapa", orientation="h", text="Valor", title=title,
        color="Etapa", color_discrete_sequence=["#F36A2D", "#E58B55", "#D8A784", "#64748B", "#2F8FD8"],
    )
    chart.update_traces(
        texttemplate="R$ %{text:,.2f}" if unit == "R$" else "%{text:,.0f} kg",
        textposition="outside", cliponaxis=False, hovertemplate=(
            "%{y}<br>R$ %{x:,.2f}<extra></extra>" if unit == "R$" else "%{y}<br>%{x:,.0f} kg<extra></extra>"
        ),
    )
    return _polish_chart(
        chart, height=max(360, 58 * len(available) + 120),
        x_title="Valor (R$)" if unit == "R$" else "Peso (kg)", y_title="",
    )


def _flow_event_summary(flow, start_date, end_date):
    columns = ["Ordem", "Macroetapa", "Movimentação", "Data de referência", "Registros", "Documentos", "Peso", "Valor", "Situação"]
    if flow is None or flow.empty:
        return pd.DataFrame(columns=columns)
    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date) + pd.Timedelta(days=1)
    rows = []
    document = flow.get("Pedido", pd.Series(pd.NA, index=flow.index)).astype("string")
    if "OP" in flow:
        document = document.fillna(flow["OP"].astype("string"))
    for order, (journey, label, date_column) in enumerate(FLOW_DATE_EVENTS, start=1):
        if date_column not in flow:
            rows.append({"Ordem": order, "Macroetapa": journey, "Movimentação": label, "Data de referência": date_column, "Registros": np.nan, "Documentos": np.nan, "Peso": np.nan, "Valor": np.nan, "Situação": "Data não publicada"})
            continue
        dates = pd.to_datetime(flow[date_column], errors="coerce")
        mask = dates.ge(start) & dates.lt(end)
        scoped = flow.loc[mask]
        rows.append({
            "Ordem": order, "Macroetapa": journey, "Movimentação": label, "Data de referência": date_column,
            "Registros": int(mask.sum()), "Documentos": int(document.loc[mask].dropna().nunique()),
            "Peso": float(pd.to_numeric(scoped.get("Peso"), errors="coerce").sum()) if "Peso" in scoped else np.nan,
            "Valor": float(pd.to_numeric(scoped.get("Valor"), errors="coerce").sum()) if "Valor" in scoped else np.nan,
            "Situação": "Com movimento" if mask.any() else "Sem movimento no período",
        })
    return pd.DataFrame(rows, columns=columns)


def _flow_deadlines(flow, start_date, end_date):
    columns = ["Transição", "Prazo mediano (dias)", "Amostra"]
    if flow is None or flow.empty:
        return pd.DataFrame(columns=columns)
    transitions = (
        ("Pedido → liberação", "Data Pedido", "Data Liberação"),
        ("Liberação → OS", "Data Liberação", "Data OS"),
        ("OS → montagem da carga", "Data OS", "Data Montagem Carga"),
        ("Montagem da carga → NF", "Data Montagem Carga", "Data Emissão NF"),
        ("NF → saída", "Data Emissão NF", "Data Saída"),
    )
    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date) + pd.Timedelta(days=1)
    rows = []
    for label, origin, destination in transitions:
        if origin not in flow or destination not in flow:
            continue
        origin_dates = pd.to_datetime(flow[origin], errors="coerce")
        destination_dates = pd.to_datetime(flow[destination], errors="coerce")
        days = (destination_dates - origin_dates).dt.total_seconds() / 86400
        valid = destination_dates.ge(start) & destination_dates.lt(end) & days.between(0, 365)
        sample = days[valid]
        if not sample.empty:
            rows.append({"Transição": label, "Prazo mediano (dias)": float(sample.median()), "Amostra": int(len(sample))})
    return pd.DataFrame(rows, columns=columns)


def _funnel_view(indicators, flow_events, start_date, end_date, brl, show_chart, show_table, can_export):
    st.subheader("Funil comercial e operacional", help=PANEL_HELP["funnel"])
    st.caption(
        f"ⓘ {pd.Timestamp(start_date).strftime('%d/%m/%Y')} a {pd.Timestamp(end_date).strftime('%d/%m/%Y')}. "
        "A posição da carteira é uma fotografia da última carga; as movimentações por data continuam disponíveis para analisar o fluxo no período."
    )
    frame = _funnel_frame(indicators)
    available = frame[frame["Valor"].notna()]
    missing = frame[frame["Valor"].isna()]
    date_summary = _flow_event_summary(flow_events, start_date, end_date)
    current_positions, position_summary = _flow_current_positions(flow_events)

    def event_metric(label, field, formatter):
        match = date_summary[date_summary["Movimentação"] == label]
        if match.empty or match.iloc[0]["Situação"] == "Data não publicada" or pd.isna(match.iloc[0][field]):
            return "Data não publicada"
        return formatter(float(match.iloc[0][field]))

    metric_cards = [
        ("Orçamentos emitidos no período", event_metric("Orçamentos emitidos", "Valor", brl), ()),
        ("Pedidos emitidos no período", event_metric("Pedidos emitidos", "Valor", brl), ()),
        ("Notas fiscais emitidas no período", event_metric("Notas fiscais emitidas", "Valor", brl), ()),
        ("Saídas realizadas no período", event_metric("Saídas realizadas", "Peso", lambda value: f"{_quantity(value)} kg"), ()),
    ]
    _metric_cards(metric_cards)
    st.markdown("### Posição atual da carteira")
    _position_stage_cards(position_summary, brl)
    st.markdown(
        '<div class="mf-funnel-note"><strong>Leitura correta:</strong> cada pedido ou OP aparece em apenas uma caixa: a etapa mais avançada '
        'registrada na última carga. Ao receber uma nova movimentação, o volume sai da caixa anterior e passa para a próxima. '
        'A aba “Movimentações por data” é histórica e pode registrar o mesmo documento em várias etapas.</div>',
        unsafe_allow_html=True,
    )

    deadlines = _flow_deadlines(flow_events, start_date, end_date)
    position_tab, dates_tab, deadlines_tab, commercial_tab, operation_tab, coverage_tab = st.tabs([
        "Posição atual", "Movimentações por data", "Prazos entre etapas", "Filas · R$", "Filas · kg", "Cobertura da base",
    ])
    with position_tab:
        if current_positions.empty:
            st.info("A carga atual ainda não publicou documentos com uma etapa de processo identificável.")
        else:
            st.caption("Cada documento é exibido uma vez, na etapa mais avançada já registrada. O calendário não recorta esta fotografia atual.")
            show_table(
                current_positions.sort_values(["Ordem", "Data da posição"], ascending=[False, False]),
                height=560, width="stretch", hide_index=True,
            )
            if can_export:
                st.download_button(
                    "Exportar posição atual da carteira",
                    current_positions.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                    "funil_posicao_atual.csv", "text/csv", width="stretch",
                )
    with dates_tab:
        if flow_events is None or flow_events.empty:
            st.info("A trilha de datas ainda não foi publicada. Execute uma nova atualização da base para habilitar esta visão.")
        else:
            st.caption("Escopo atual: trilha global. A origem ainda não publicou vendedor, cliente e produto nesta tabela; por isso somente o calendário é aplicado.")
            measured = date_summary[date_summary["Registros"].notna()]
            active = measured[measured["Registros"] > 0]
            date_columns = [column for column in flow_events.columns if str(column).startswith("Data ")]
            date_coverage = flow_events[date_columns].notna().any(axis=1).mean() if date_columns else 0
            cards = st.columns(3)
            cards[0].metric("Movimentações no período", _quantity(measured["Registros"].sum()), help="Soma dos eventos registrados em cada etapa; um mesmo pedido pode aparecer em mais de uma etapa.")
            cards[1].metric("Etapas com movimento", f"{len(active)} de {len(measured)}")
            cards[2].metric("Linhas com alguma data", f"{date_coverage * 100:.2f}%".replace(".", ","))
            if active.empty:
                st.info("Não houve movimentações nas datas selecionadas.")
            else:
                chart_data = active.sort_values("Ordem", ascending=False)
                chart = px.bar(
                    chart_data, x="Registros", y="Movimentação", orientation="h", color="Macroetapa",
                    text="Registros", title="Movimentações ocorridas no período",
                    color_discrete_sequence=["#F36A2D", "#D89A20", "#2F8FD8", "#7C6CC4", "#20A36A", "#64748B"],
                )
                chart.update_traces(textposition="outside", cliponaxis=False)
                show_chart(_polish_chart(chart, height=max(390, 38 * len(chart_data) + 130), x_title="Registros", y_title=""))
            show_table(date_summary.drop(columns="Ordem"), height=520, width="stretch", hide_index=True)
            if can_export:
                st.download_button(
                    "Exportar movimentações por data",
                    date_summary.drop(columns="Ordem").to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                    "funil_movimentacoes_por_data.csv", "text/csv", width="stretch",
                )
    with deadlines_tab:
        st.caption("ⓘ O prazo é calculado entre duas datas reais do mesmo registro. Valores negativos, ausentes ou acima de 365 dias são excluídos.")
        if deadlines.empty:
            st.info("Ainda não há pares de datas válidos no período para calcular os prazos entre etapas.")
        else:
            chart_data = deadlines.sort_values("Prazo mediano (dias)")
            chart = px.bar(
                chart_data, x="Prazo mediano (dias)", y="Transição", orientation="h", text="Prazo mediano (dias)",
                title="Tempo mediano entre etapas", color_discrete_sequence=["#2F8FD8"],
            )
            chart.update_traces(texttemplate="%{text:.1f} dias", textposition="outside", cliponaxis=False)
            show_chart(_polish_chart(chart, height=max(350, 48 * len(chart_data) + 120), x_title="Dias", y_title=""))
            show_table(deadlines, height=300, width="stretch", hide_index=True)
    with commercial_tab:
        chart = _funnel_chart(frame[frame["Fluxo"] == "Comercial"], "Orçamentos e pedidos", "R$")
        if chart is None:
            st.info("A carga atual ainda não publicou as etapas comerciais do funil.")
        else:
            show_chart(chart)
    with operation_tab:
        chart = _funnel_chart(frame[frame["Fluxo"] == "Operação"], "Fila de produção, carga e faturamento", "kg")
        if chart is None:
            st.info("A carga atual ainda não publicou as etapas operacionais do funil.")
        else:
            show_chart(chart)
        subtotals = frame[(frame["É subtotal"]) & frame["Valor"].notna()][["Etapa", "Valor"]].copy()
        if not subtotals.empty:
            subtotals = subtotals.rename(columns={"Valor": "Peso"})
            st.caption("Abertura informativa do faturamento por modalidade")
            show_table(subtotals, height=180, width="stretch", hide_index=True)
    with coverage_tab:
        coverage = frame[["Macroetapa", "Fluxo", "Etapa", "Unidade", "Valor", "Cobertura"]].copy()
        coverage["Valor exibido"] = coverage.apply(
            lambda row: (brl(row["Valor"]) if row["Unidade"] == "R$" else f"{_quantity(row['Valor'])} kg")
            if pd.notna(row["Valor"]) else "—", axis=1,
        )
        show_table(coverage.drop(columns="Valor"), height=470, width="stretch", hide_index=True)
        st.caption(f"{len(available)} de {len(frame)} etapas disponíveis na última carga.")
        if not missing.empty:
            st.warning("Etapas ainda não publicadas: " + ", ".join(missing["Etapa"].tolist()) + ".")
    if can_export:
        export = frame.drop(columns=["Chave", "É subtotal"]).copy()
        st.download_button(
            "Exportar fotografia do funil", export.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            "funil_acompanhamento.csv", "text/csv", width="stretch",
        )


def render(data, history, start_date, end_date, last_load, brl, brl2, pct, pp, show_chart, show_table, *, permissions, current_user, targets=None, target_history=None, target_filters=None, commercial_indicators=None, flow_events=None):
    """Exibe somente as páginas explicitamente liberadas ao usuário."""
    _inject_kpi_styles()
    pages = []
    if "view_overview" in permissions:
        pages.append(("Command Center", "view_overview"))
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
    if "view_funnel" in permissions:
        pages.append(("Funil", "view_funnel"))
    if "view_map" in permissions:
        pages.append(("Mapa", "view_map"))
    if "view_heatmap" in permissions:
        pages.append(("Mapa mensal", "view_heatmap"))
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
    elif permission == "view_funnel":
        _funnel_view(commercial_indicators, flow_events, start_date, end_date, brl, show_chart, show_table, can_export)
    elif permission == "view_map":
        _municipal_map_view(data, history, start_date, end_date, brl, brl2, pct, show_chart, show_table, can_export)
    elif permission == "view_heatmap":
        _monthly_activity_view(history, end_date, brl, show_chart, show_table, can_export)
    elif permission == "view_insights":
        _insights_view(data, history, start_date, end_date, brl, show_table, can_export)
    elif permission == "view_pivot":
        _pivot(data, show_table, can_export)
    elif permission == "view_unified":
        _unified_view(data, targets, flow_events, commercial_indicators, start_date, end_date, show_table, can_export)
    elif permission == "view_yoy":
        _yoy(data, history, start_date, end_date, show_chart, show_table)
    elif permission == "use_assistant":
        st.subheader("Assistente analítico", help=PANEL_HELP["assistant"])
        st.caption("Respostas calculadas a partir do período e dos filtros atuais. Escolha uma pergunta pronta ou escreva sua própria pergunta.")
        if "chat" not in st.session_state:
            st.session_state.chat = []
        for role, message in st.session_state.chat:
            with st.chat_message(role):
                st.markdown(message)
        st.markdown("##### Perguntas prontas")
        question = None
        prompt_columns = st.columns(3)
        for index, (label, prompt) in enumerate(SUGGESTED_QUESTIONS):
            if prompt_columns[index % 3].button(label, key=f"assistant_prompt_{index}", width="stretch"):
                question = prompt
        typed_question = st.chat_input("Ex.: quais vendedores mais contribuíram para o resultado?")
        if typed_question:
            question = typed_question
        if question:
            response = answer(question, data, history, start_date, end_date)
            st.session_state.chat.extend([("user", question), ("assistant", response)])
            st.rerun()
    elif permission == "manage_users":
        render_user_admin(
            current_user,
            seller_options=sorted(history["Vendedor"].dropna().astype(str).unique().tolist()),
        )
