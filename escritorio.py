"""Painel independente do Escritório METALFORTE 360.

Usa as mesmas bases autenticadas e os mesmos carregadores Supabase do app principal.
Execute no Streamlit apontando o arquivo principal para escritorio.py.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st

from src.auth import require_login, logout
from src.data import load_data, load_targets, load_stock, load_flow
from src.cloud_storage import upload_bytes, download_status
from src.inventory import build_inventory_analysis

st.set_page_config(page_title="Escritório METALFORTE 360", layout="wide", page_icon="🏢")
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = ["#F36A2D", "#2F8FD8", "#34B27B", "#F2B84B", "#A78BFA"]

PEOPLE = [
    {"name":"Jeandro","area":"Planejamento","role":"Analista de Business Plan","icon":"📈","task":"Pulso de realizado x orçado e plano de metas"},
    {"name":"Nayane","area":"Marcas & Marketing","role":"Analista de Marcas e Marketing","icon":"🎯","task":"Radar de portfólio, demanda e calendário de ações"},
    {"name":"Lucas","area":"Trade","role":"Analista de Trade","icon":"🤝","task":"Performance de revendas e plano de sell-out"},
    {"name":"Bruno","area":"Administração de Vendas","role":"Analista de Administração de Vendas","icon":"💼","task":"Ritmo diário, previsão e performance comercial"},
    {"name":"Uandson","area":"S&OP","role":"Analista de S&OP","icon":"📦","task":"Pedidos pendentes, estoque e risco de ruptura"},
    {"name":"Wilton","area":"Expansão Territorial","role":"Analista de Expansão Territorial","icon":"🗺️","task":"Desempenho comercial por região"},
    {"name":"Breno","area":"Design","role":"Analista de Design","icon":"🎨","task":"Fila de campanhas, peças e materiais auxiliares"},
]

@st.cache_data(ttl=1800, show_spinner="Lendo as bases conectadas do METALFORTE 360…")
def read_sources(refresh_key):
    try:
        status = download_status()
    except Exception:
        status = {}
    return load_data(), load_targets(), load_stock(), load_flow(), status

def money(value):
    return f"R$ {float(value or 0):,.0f}".replace(",", ".")

def number(value):
    return f"{float(value or 0):,.0f}".replace(",", ".")

def total(frame, column):
    return float(pd.to_numeric(frame.get(column, pd.Series(dtype=float)), errors="coerce").fillna(0).sum())

def latest_period(frame):
    dates = pd.to_datetime(frame.get("Data", pd.Series(dtype="datetime64[ns]")), errors="coerce").dropna()
    return dates.max().to_period("M") if not dates.empty else pd.Timestamp.today().to_period("M")

def month_slice(frame, period):
    if frame is None or frame.empty or "Data" not in frame:
        return pd.DataFrame()
    dates = pd.to_datetime(frame["Data"], errors="coerce")
    return frame.loc[dates.dt.to_period("M").eq(period)].copy()

def previous_month_slice(frame, period):
    return month_slice(frame, period - 1)

def top_table(frame, dimension, measure, limit=10):
    if frame is None or frame.empty or dimension not in frame or measure not in frame:
        return pd.DataFrame()
    return (frame.groupby(dimension, dropna=False)[measure].sum().sort_values(ascending=False)
            .head(limit).rename(measure).reset_index())

def kpi(label, value, note="Base conectada"):
    st.metric(label, value, help=note)

def heading(person, period):
    st.subheader(f"{person['icon']} {person['name']} · {person['area']}")
    st.caption(f"{person['role']}  |  Rotina diária: {person['task']}  |  Referência dos dados: {period}")

def report_jeandro(sales, targets, period):
    actual = month_slice(sales, period)
    target = targets.copy()
    if not target.empty and "Competência" in target:
        target = target[pd.to_datetime(target["Competência"], errors="coerce").dt.to_period("M").eq(period)]
    target_revenue, target_kg = total(target, "Meta R$"), total(target, "Meta KG")
    revenue, kg = total(actual, "Faturamento"), total(actual, "Peso")
    a, b, c = st.columns(3)
    with a: kpi("Realizado", money(revenue), "Faturamento do mês de referência")
    with b: kpi("Meta R$", money(target_revenue), "Metas granulares conectadas")
    with c: kpi("Atingimento", f"{revenue/target_revenue:.1%}" if target_revenue else "Sem meta", "Realizado ÷ meta")
    d, e = st.columns(2)
    with d: kpi("Realizado KG", f"{number(kg)} kg")
    with e: kpi("Meta KG", f"{number(target_kg)} kg")
    if target.empty:
        st.warning("A base de metas não trouxe linhas para este mês. O painel não estima metas ausentes.")
    if not actual.empty and "Data" in actual:
        daily = actual.groupby(pd.to_datetime(actual["Data"]).dt.date)["Faturamento"].sum().rename("Faturamento").reset_index()
        st.plotly_chart(px.line(daily, x="Data", y="Faturamento", markers=True, title="Realizado diário no mês"), use_container_width=True)

def report_nayane(sales, period):
    current, previous = month_slice(sales, period), previous_month_slice(sales, period)
    dimension = "Grupo Produto" if "Grupo Produto" in sales else "Produto"
    now, before = top_table(current, dimension, "Faturamento"), top_table(previous, dimension, "Faturamento")
    if now.empty:
        st.info("Sem vendas de produto na base para este período.")
        return
    now = now.rename(columns={"Faturamento":"Faturamento mês atual"})
    if not before.empty:
        before = before.rename(columns={"Faturamento":"Faturamento mês anterior"})
        merged = now.merge(before, on=dimension, how="left").fillna({"Faturamento mês anterior":0})
        merged["Variação R$"] = merged["Faturamento mês atual"] - merged["Faturamento mês anterior"]
        st.dataframe(merged, hide_index=True, use_container_width=True)
    else:
        st.dataframe(now, hide_index=True, use_container_width=True)
    st.caption("Leitura interna do portfólio vendido. A base conectada não contém pesquisa externa de mercado nem calendário de mídia.")

def report_lucas(sales):
    st.caption("A fonte conectada mostra vendas METALFORTE (sell-in). Sem uma base de sell-out das revendas, o painel não inventa venda ao consumidor final.")
    customer = "Cliente Painel" if "Cliente Painel" in sales else "Cliente"
    current = sales
    if "Data" in current:
        current = month_slice(current, latest_period(current))
    table = top_table(current, customer, "Faturamento", 15)
    if not table.empty:
        table = table.rename(columns={customer:"Revenda / grupo", "Faturamento":"Sell-in (R$)"})
        st.dataframe(table, hide_index=True, use_container_width=True)
    else:
        st.info("A base não contém dados suficientes para o ranking de clientes.")

def report_bruno(sales):
    current = month_slice(sales, latest_period(sales))
    if current.empty:
        st.info("Sem linhas de faturamento no mês de referência.")
        return
    c1, c2, c3 = st.columns(3)
    with c1: kpi("Faturamento do mês", money(total(current, "Faturamento")))
    with c2: kpi("Volume do mês", f"{number(total(current, 'Peso'))} kg")
    with c3: kpi("Pedidos", number(current["Pedido"].nunique()) if "Pedido" in current else "—")
    if "Data" in current:
        daily = current.groupby(pd.to_datetime(current["Data"]).dt.date)["Faturamento"].sum().rename("Faturamento").reset_index()
        st.plotly_chart(px.bar(daily, x="Data", y="Faturamento", title="Ritmo diário de faturamento"), use_container_width=True)
    seller = "Vendedor Painel" if "Vendedor Painel" in current else "Vendedor"
    table = top_table(current, seller, "Faturamento", 12)
    if not table.empty:
        st.markdown("**Performance por vendedor**")
        st.dataframe(table, hide_index=True, use_container_width=True)

def report_uandson(sales, stock, flow):
    if stock is not None and not stock.empty:
        analysis = build_inventory_analysis(stock, sales, months=3)
        risk = analysis[analysis["Cobertura"].isin(["Ruptura", "Baixo (≤30 dias)"])].copy()
        a,b,c = st.columns(3)
        with a: kpi("Produtos com risco", number(len(risk)), "Ruptura ou cobertura de até 30 dias")
        with b: kpi("Aguardando estoque", f"{number(total(analysis, 'Aguardando estoque (kg)'))} kg")
        with c: kpi("Excesso potencial", f"{number(total(analysis, 'Excesso potencial (kg)'))} kg")
        if not risk.empty:
            st.dataframe(risk[["Produto Codigo","Produto","Cobertura","Estoque disponível (kg)","Venda média diária (kg)","Dias de estoque"]].head(20), hide_index=True, use_container_width=True)
    else:
        st.warning("A fotografia de estoque não está disponível na base conectada.")
    if flow is not None and not flow.empty:
        st.markdown("**Fluxo de pedidos**")
        st.caption(f"{len(flow):,} registros na base de fluxo. Consulte os campos de processo abaixo; a base é exibida sem reinterpretar etapas.")
        preferred = [c for c in ("Pedido","Cliente Painel","Vendedor Painel","Produto","Peso","Valor","Status","Etapa","Data Pedido","Data Liberação","Data Entrega") if c in flow]
        st.dataframe(flow[preferred].head(30) if preferred else flow.head(30), hide_index=True, use_container_width=True)
    else:
        st.info("A base de fluxo de pedidos não retornou registros.")

def report_wilton(sales):
    current = month_slice(sales, latest_period(sales))
    dimension = "UF" if "UF" in current else "Município"
    table = top_table(current, dimension, "Faturamento", 20)
    if table.empty:
        st.info("A base não trouxe localização para o período.")
        return
    table = table.rename(columns={"Faturamento":"Faturamento (R$)"})
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.plotly_chart(px.bar(table.head(12), x=dimension, y="Faturamento (R$)", title="Faturamento por território"), use_container_width=True)

def report_breno():
    st.markdown("Central de materiais auxiliares para briefing e entregas de design.")
    uploaded = st.file_uploader("Adicionar briefing, calendário, campanha ou referência aprovada",
        type=["pdf","pptx","xlsx","csv","png","jpg","jpeg","docx"], key="office_asset")
    if uploaded is not None:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", uploaded.name).strip("._") or "anexo"
        path = f"escritorio/auxiliares/{datetime.now().strftime('%Y/%m/%d')}/{uuid.uuid4().hex[:8]}_{safe_name}"
        if st.button("Salvar no armazenamento METALFORTE 360", type="primary"):
            try:
                upload_bytes(uploaded.getvalue(), path, uploaded.type or "application/octet-stream")
                st.success(f"Arquivo salvo no Supabase Storage: {path}")
            except Exception as exc:
                st.error(f"Não foi possível salvar o arquivo ({type(exc).__name__}).")
    st.caption("A prévia não acessa referências externas; use os anexos para fornecer identidade visual, briefing e modelos aprovados.")

def main():
    access = require_login()
    role = access.get("role")
    if role not in {"admin", "manager", "analyst"}:
        st.error("O Escritório está disponível para os perfis de administração, gestão e análise.")
        st.stop()
    user = access.get("user", {})
    with st.sidebar:
        logo = Path(__file__).parent / "LOGO_METALFORTE.jpg"
        if logo.exists(): st.image(str(logo), use_container_width=True)
        st.caption("Painel de rotinas, relatórios e análises")
        st.caption(f"Perfil: {role or 'usuário'}")
        if st.button("Sair"): logout(); st.rerun()
        if st.button("Atualizar bases", type="primary"):
            read_sources.clear()
            st.rerun()
        st.divider()
        st.markdown("**Fonte**  \nBases oficiais do METALFORTE 360 no Supabase")
    try:
        sales, targets, stock, flow, status = read_sources(str(datetime.now().date()))
    except Exception as exc:
        st.error(f"Não foi possível carregar a base principal ({type(exc).__name__}).")
        st.caption("Confira os mesmos Secrets do Streamlit usados pelo METALFORTE 360: SUPABASE_URL e SUPABASE_SERVICE_KEY.")
        st.stop()
    if role == "seller":
        from src.dimensions import normalize_seller
        scope = normalize_seller(access.get("seller_scope", ""))
        sales = sales[sales["Vendedor"].astype(str).eq(scope)].copy() if scope and "Vendedor" in sales else sales.iloc[0:0]
        if sales.empty:
            st.error("Não há carteira associada a este usuário.")
            st.stop()
    period = latest_period(sales)
    period_label = period.strftime("%m/%Y")
    load_time = status.get("atualizado_em", "horário da carga indisponível") if isinstance(status, dict) else "horário da carga indisponível"
    st.markdown("<div class='hero'><span>🏢 ESCRITÓRIO METALFORTE 360</span><h1>Rotinas que transformam dados em ação</h1><p>Sete áreas, uma fonte de dados oficial e entregas transparentes.</p></div>", unsafe_allow_html=True)
    st.caption(f"Base de vendas atualizada: {load_time} · Período analítico mais recente: {period_label}")
    st.markdown("""
    <style>
    .stApp{background:#F5F7FB;color:#172033}.block-container{max-width:1600px;padding-top:1.5rem}
    .hero{padding:1.5rem 1.8rem;border-radius:18px;background:linear-gradient(120deg,#152B48,#244C70 65%,#F36A2D);color:white;margin-bottom:1rem}
    .hero span{font-size:.8rem;letter-spacing:.12em;font-weight:800;opacity:.85}.hero h1{color:white;margin:.5rem 0;font-size:2.2rem}.hero p{margin:0;color:#EAF1F8}
    [data-testid="stMetric"]{background:white;padding:1rem;border:1px solid #DFE6EF;border-radius:14px;box-shadow:0 3px 12px #14243b0b}
    </style>
    """, unsafe_allow_html=True)
    st.subheader("Salas e colaboradores")
    columns = st.columns(4)
    for index, person in enumerate(PEOPLE):
        with columns[index % 4]:
            st.markdown(f"**{person['icon']} {person['area']}**  \n{person['name']} · {person['role']}")
            st.caption(f"Rotina diária: {person['task']}")
    st.divider()
    tabs = st.tabs([f"{p['icon']} {p['name']}" for p in PEOPLE])
    renderers = [report_jeandro, report_nayane, report_lucas, report_bruno, report_uandson, report_wilton, report_breno]
    for person, tab, render in zip(PEOPLE, tabs, renderers):
        with tab:
            heading(person, period_label)
            if person["name"] == "Jeandro": render(sales, targets, period)
            elif person["name"] == "Nayane": render(sales, period)
            elif person["name"] == "Lucas": render(sales)
            elif person["name"] == "Bruno": render(sales)
            elif person["name"] == "Uandson": render(sales, stock, flow)
            elif person["name"] == "Wilton": render(sales)
            else: render()

if __name__ == "__main__":
    main()
