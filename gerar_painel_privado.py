"""Gera um HTML privado para a gestão comercial da METALFORTE."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.io as pio
from plotly.subplots import make_subplots

from atualizar_gooddata import ACTIVE, parse_raw
from src.manual_load import report_path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "PAINEL_PRIVADO_HTML" / "painel_gestao_comercial.html"
COLORS = ["#F36A2D", "#2F8FD8", "#34B27B", "#D9534F"]


def _money(value):
    return f"R$ {float(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _int(value):
    return f"{float(value):,.0f}".replace(",", ".")


def _pct(value):
    return "—" if pd.isna(value) else f"{float(value) * 100:.2f}%".replace(".", ",")


def _ratio(a, b):
    return a / b if b else pd.NA


def _customer_key(data):
    code = data["Cod Cliente"].astype("string").fillna("").str.strip()
    return code.mask(code.eq(""), data["Cliente"].astype("string").fillna("Não identificado").str.strip())


def _table(frame, money=(), percent=()):
    if frame.empty:
        return '<p class="empty">Sem dados para este recorte.</p>'
    view = frame.copy()
    for col in view.columns:
        if col in money:
            view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0).map(_money)
        elif col in percent:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(_pct)
        elif pd.api.types.is_numeric_dtype(view[col]):
            view[col] = view[col].fillna(0).map(_int)
    return view.to_html(index=False, border=0, classes="data-table", escape=True)


def _chart(fig, include_js=False):
    fig.update_layout(template="plotly_white", paper_bgcolor="white", plot_bgcolor="white", font={"family": "Arial", "color": "#27364A"}, margin={"l": 44, "r": 24, "t": 55, "b": 42}, legend={"orientation": "h", "y": 1.12})
    fig.update_xaxes(gridcolor="#EDF1F5")
    fig.update_yaxes(gridcolor="#EDF1F5")
    return pio.to_html(fig, full_html=False, include_plotlyjs="inline" if include_js else False, config={"displayModeBar": False, "responsive": True})


def _group(data, dimension):
    out = data.groupby(dimension, dropna=False).agg(Faturamento=("Faturamento", "sum"), Margem=("Margem", "sum"), Peso=("Peso", "sum"), Clientes=("Cliente Chave", "nunique")).reset_index()
    out["Margem %"] = out["Margem"] / out["Faturamento"].replace(0, pd.NA)
    return out.sort_values("Faturamento", ascending=False)


def _stock_days(data):
    path = report_path("estoque_produto")
    if path is None:
        return pd.DataFrame()
    stock = parse_raw(path.read_bytes())
    normal = {str(c).lower().replace(" ", "").replace("_", ""): c for c in stock.columns}
    product = next((v for k, v in normal.items() if "produto" in k and ("codigo" in k or "cód" in k)), None)
    product = product or next((v for k, v in normal.items() if "produto" in k), None)
    stock_kg = next((v for k, v in normal.items() if "estoque" in k and ("kg" in k or "peso" in k)), None)
    if not product or not stock_kg:
        return pd.DataFrame()
    latest = data["Data"].max()
    demand = data[data["Data"] > latest - pd.Timedelta(days=90)].groupby("Produto Codigo")["Peso"].sum().rename("Demanda 90 dias (kg)")
    out = pd.DataFrame({"Produto Codigo": stock[product].astype("string").str.strip(), "Estoque (kg)": pd.to_numeric(stock[stock_kg], errors="coerce")}).dropna()
    out = out.groupby("Produto Codigo", as_index=False)["Estoque (kg)"].sum().merge(demand, on="Produto Codigo", how="left").fillna({"Demanda 90 dias (kg)": 0})
    out["Dias de estoque"] = out["Estoque (kg)"] / (out["Demanda 90 dias (kg)"] / 90).replace(0, pd.NA)
    names = data.groupby("Produto Codigo")["Produto"].last()
    return out.merge(names, on="Produto Codigo", how="left").sort_values("Dias de estoque", na_position="last")


def generate_private_dashboard():
    if not ACTIVE.exists():
        raise FileNotFoundError("Base comercial ausente. Execute primeiro uma carga válida.")
    data = pd.read_csv(ACTIVE, compression="gzip", low_memory=False)
    data["Data"] = pd.to_datetime(data["Data"], errors="coerce")
    data["Data Pedido"] = pd.to_datetime(data["Data Pedido"], errors="coerce")
    for col in ("Faturamento", "Margem", "Peso"):
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)
    data = data.dropna(subset=["Data"]).copy()
    if data.empty:
        raise ValueError("A base comercial não possui datas válidas.")
    data["Cliente Chave"] = _customer_key(data)
    data["Segmento Cliente"] = data["Segmento Cliente"].fillna("Não classificado")
    data["Grupo Produto"] = data["Grupo Produto"].fillna("Não classificado")
    latest = data["Data"].max().normalize()
    start = latest.replace(day=1)
    previous_end = start - pd.Timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    previous_cut = previous_start + pd.Timedelta(days=min(latest.day, previous_end.day) - 1)
    current = data[data["Data"].between(start, latest)]
    previous = data[data["Data"].between(previous_start, previous_cut)]
    last_year = data[data["Data"].between(start - pd.DateOffset(years=1), latest - pd.DateOffset(years=1))]
    first_purchase = data.groupby("Cliente Chave")["Data"].min()
    new_keys = first_purchase[first_purchase.between(start, latest)].index
    revenue = current["Faturamento"].sum()
    margin_pct = _ratio(current["Margem"].sum(), revenue)
    month_delta = _ratio(revenue - previous["Faturamento"].sum(), previous["Faturamento"].sum())
    year_delta = _ratio(revenue - last_year["Faturamento"].sum(), last_year["Faturamento"].sum())
    active = current["Cliente Chave"].nunique()
    observed = data[data["Data"] > latest - pd.Timedelta(days=365)]["Cliente Chave"].nunique()
    new_active = current[current["Cliente Chave"].isin(new_keys)]["Cliente Chave"].nunique()

    monthly = data[data["Data"] > latest - pd.DateOffset(months=18)].groupby(data["Data"].dt.to_period("M")).agg(Faturamento=("Faturamento", "sum"), Margem=("Margem", "sum"), Peso=("Peso", "sum"), Clientes=("Cliente Chave", "nunique")).reset_index().rename(columns={"Data": "Período"})
    monthly["Margem %"] = monthly["Margem"] / monthly["Faturamento"].replace(0, pd.NA)
    monthly["Rótulo"] = monthly["Período"].astype(str)
    weekly = data[data["Data"] > latest - pd.Timedelta(days=182)].groupby(data["Data"].dt.to_period("W-MON"))["Faturamento"].sum().reset_index().rename(columns={"Data": "Período"})
    weekly["Rótulo"] = weekly["Período"].astype(str)
    daily = data[data["Data"] > latest - pd.Timedelta(days=62)].groupby("Data")["Faturamento"].sum().reset_index()
    client_segment = _group(current, "Segmento Cliente").head(12)
    product_segment = _group(current, "Grupo Produto").head(12)

    now_value = current.groupby("Cliente Chave").agg(Cliente=("Cliente", "last"), Segmento=("Segmento Cliente", "last"), Atual=("Faturamento", "sum"))
    before_value = previous.groupby("Cliente Chave")["Faturamento"].sum().rename("Anterior")
    movement = now_value.join(before_value, how="outer").fillna({"Atual": 0, "Anterior": 0}).reset_index()
    movement["Variação %"] = (movement["Atual"] - movement["Anterior"]) / movement["Anterior"].replace(0, pd.NA)
    growing = movement[(movement["Anterior"] > 0) & (movement["Variação %"] >= .1)].sort_values("Variação %", ascending=False).head(20)
    declining = movement[(movement["Anterior"] > 0) & (movement["Variação %"] <= -.1)].sort_values("Variação %").head(20)
    stopped = data.groupby("Cliente Chave").agg(
        Cliente=("Cliente", "last"),
        Segmento=("Segmento Cliente", "last"),
        Faturamento=("Faturamento", "sum"),
        **{"Última compra": ("Data", "max")},
    ).reset_index()
    stopped = stopped[stopped["Última compra"] < latest - pd.Timedelta(days=90)].sort_values("Faturamento", ascending=False).head(20)
    stock = _stock_days(data)

    evolution = make_subplots(specs=[[{"secondary_y": True}]])
    evolution.add_bar(x=monthly["Rótulo"], y=monthly["Faturamento"], name="Faturamento", marker_color=COLORS[0])
    evolution.add_scatter(x=monthly["Rótulo"], y=monthly["Margem %"], name="Margem %", mode="lines+markers", line={"color": COLORS[1], "width": 3}, secondary_y=True)
    evolution.update_layout(title="Evolução mês a mês: faturamento e margem")
    evolution.update_yaxes(tickprefix="R$ ", secondary_y=False); evolution.update_yaxes(tickformat=".1%", secondary_y=True)
    week_chart = px.line(weekly, x="Rótulo", y="Faturamento", title="Evolução semana a semana", markers=True, color_discrete_sequence=[COLORS[2]])
    week_chart.update_yaxes(tickprefix="R$ ")
    day_chart = px.bar(daily, x="Data", y="Faturamento", title="Evolução dia a dia: últimos 62 dias", color_discrete_sequence=[COLORS[1]])
    day_chart.update_yaxes(tickprefix="R$ ")
    client_chart = px.bar(client_segment.sort_values("Faturamento"), x="Faturamento", y="Segmento Cliente", orientation="h", title="Segmento de cliente", color_discrete_sequence=[COLORS[0]])
    product_chart = px.bar(product_segment.sort_values("Faturamento"), x="Faturamento", y="Grupo Produto", orientation="h", title="Segmento de produto", color_discrete_sequence=[COLORS[2]])
    client_chart.update_xaxes(tickprefix="R$ "); product_chart.update_xaxes(tickprefix="R$ ")
    orders = data.dropna(subset=["Pedido", "Data Pedido"]).groupby(data["Data Pedido"].dt.to_period("M"))["Faturamento"].sum().rename("Pedidos associados").reset_index().rename(columns={"Data Pedido": "Período"})
    billed = data.groupby(data["Data"].dt.to_period("M"))["Faturamento"].sum().rename("Faturamento").reset_index().rename(columns={"Data": "Período"})
    order_compare = billed.merge(orders, on="Período", how="outer").fillna(0).tail(18); order_compare["Rótulo"] = order_compare["Período"].astype(str)
    order_chart = px.bar(order_compare.melt(id_vars="Rótulo", value_vars=["Faturamento", "Pedidos associados"], var_name="Métrica", value_name="Valor"), x="Rótulo", y="Valor", color="Métrica", barmode="group", title="Faturamento x pedidos associados", color_discrete_sequence=COLORS[:2])
    order_chart.update_yaxes(tickprefix="R$ ")

    cards = [("Faturamento MTD", _money(revenue), f"{_pct(month_delta)} vs. mês anterior · {_pct(year_delta)} vs. ano anterior"), ("Margem %", _pct(margin_pct), "margem realizada sobre faturamento"), ("Positivação", _int(active), f"clientes compradores · {_pct(_ratio(active, observed))} da base observada em 12 meses"), ("Novos clientes", _int(len(new_keys)), "primeira compra observada no mês"), ("Positivação – novos", _int(new_active), "novos clientes que compraram no mês")]
    cards_html = "".join(f'<article class="card"><span>{html.escape(label)}</span><strong>{value}</strong><small>{html.escape(note)}</small></article>' for label, value, note in cards)
    charts = [_chart(evolution, True), _chart(week_chart), _chart(day_chart), _chart(client_chart), _chart(product_chart), _chart(order_chart)]
    stock_html = _table(stock[["Produto", "Estoque (kg)", "Demanda 90 dias (kg)", "Dias de estoque"]].head(25)) if not stock.empty else '<p class="empty">Inclua estoque_produto.csv com código de produto e estoque em kg para calcular os dias de estoque.</p>'
    growing_table = growing[["Cliente", "Segmento", "Atual", "Anterior", "Variação %"]].rename(
        columns={"Atual": "Faturamento", "Anterior": "Pedidos"}
    )
    declining_table = declining[["Cliente", "Segmento", "Atual", "Anterior", "Variação %"]].rename(
        columns={"Atual": "Faturamento", "Anterior": "Pedidos"}
    )
    page = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gestão comercial privada | METALFORTE</title><style>body{{font-family:Arial,sans-serif;background:#F5F7FA;color:#27364A;margin:0}}.wrap{{max-width:1600px;margin:auto;padding:26px}}h1{{margin:0;font-size:30px}}h2{{font-size:20px;margin:28px 0 12px}}.sub,.note{{color:#617086;font-size:13px;line-height:1.5}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}.card,.panel{{background:#fff;border:1px solid #DFE6EE;border-radius:12px;padding:17px;box-shadow:0 2px 9px #25354A0A}}.card span,.card small{{display:block;color:#617086;font-size:13px}}.card strong{{display:block;font-size:25px;margin:9px 0}}.grid{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(360px,.75fr);gap:16px;margin-top:16px}}.full{{margin-top:16px}}.data-table{{width:100%;border-collapse:collapse;font-size:13px}}.data-table th{{text-align:left;background:#F7F9FC;color:#516277}}.data-table th,.data-table td{{padding:9px;border-bottom:1px solid #E7ECF2}}.empty{{padding:16px;background:#FFF6EE;border-left:4px solid #F36A2D;color:#704126}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}.wrap{{padding:15px}}}}</style></head><body><main class="wrap"><h1>METALFORTE | Gestão comercial privada</h1><p class="sub">Base até {latest.strftime('%d/%m/%Y')} · arquivo local, de uso interno</p><section class="cards">{cards_html}</section><section class="full panel">{charts[0]}</section><section class="grid"><article class="panel">{charts[1]}</article><article class="panel">{charts[2]}</article></section><section class="grid"><article class="panel">{charts[3]}</article><article class="panel">{_table(client_segment, money=("Faturamento", "Margem"), percent=("Margem %",))}</article></section><section class="grid"><article class="panel">{charts[4]}</article><article class="panel">{_table(product_segment, money=("Faturamento", "Margem"), percent=("Margem %",))}</article></section><section class="grid"><article class="panel">{charts[5]}<p class="note">Pedidos associados usam a data de pedido das linhas que já fazem parte da base faturada. Para carteira ainda em aberto, inclua os arquivos de fluxo na carga.</p></article><article class="panel">{_table(order_compare[["Rótulo", "Faturamento", "Pedidos associados"]], money=("Faturamento", "Pedidos associados"))}</article></section><h2>Clientes em crescimento, queda e inativos</h2><section class="grid"><article class="panel"><h3>Crescimento ≥ 10%</h3>{_table(growing_table, money=("Faturamento", "Pedidos"), percent=("Variação %",))}</article><article class="panel"><h3>Queda ≤ -10%</h3>{_table(declining_table, money=("Faturamento", "Pedidos"), percent=("Variação %",))}</article></section><section class="grid"><article class="panel"><h2>Pararam de comprar</h2>{_table(stopped, money=("Faturamento",))}<p class="note">Sem compra há mais de 90 dias a partir da última data da base.</p></article><article class="panel"><h2>Estoque x demanda</h2>{stock_html}<p class="note">Dias de estoque = estoque em kg ÷ demanda média diária dos últimos 90 dias.</p></article></section><section class="full panel"><h2>Definições</h2><p class="note">Positivação = clientes compradores no período. Novos clientes = primeira compra observada na base. Comparações M-1 e ano anterior consideram o mesmo número de dias transcorridos. A base atual não contém data de cadastro do cliente; por isso, “novo” significa novo comprador.</p></section></main></body></html>'''
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(page, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    print(generate_private_dashboard())
