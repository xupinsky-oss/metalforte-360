"""Painel independente do Escritório METALFORTE 360.

Usa as mesmas bases autenticadas e os mesmos carregadores Supabase do app principal.
Execute no Streamlit apontando o arquivo principal para escritorio.py.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import re
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st

from src.auth import require_login, logout
from src.data import load_data, load_targets, load_stock, load_flow
from src.cloud_storage import upload_bytes, download_bytes, download_status
from src.inventory import build_inventory_analysis
from src.analytics import forecast_year

st.set_page_config(page_title="Escritório METALFORTE 360", layout="wide", page_icon="🏢")
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = ["#F36A2D", "#2F8FD8", "#34B27B", "#F2B84B", "#A78BFA"]

PEOPLE = [
    {"name":"Jeandro","area":"Planejamento","role":"Analista de Business Plan","icon":"📈","task":"Histórico mensal, comparação com orçamento e projeção por mês"},
    {"name":"Nayane","area":"Marcas & Marketing","role":"Analista de Marcas e Marketing","icon":"🎯","task":"Radar de portfólio, demanda e calendário de ações"},
    {"name":"Lucas","area":"Trade","role":"Analista de Trade","icon":"🤝","task":"Performance de revendas e plano de sell-out"},
    {"name":"Bruno","area":"Administração de Vendas","role":"Analista de Administração de Vendas","icon":"💼","task":"Ritmo diário, fechamento e previsão de vendas"},
    {"name":"Uandson","area":"S&OP","role":"Analista de S&OP","icon":"📦","task":"Pedidos pendentes, estoque e risco de ruptura"},
    {"name":"Wilton","area":"Expansão Territorial","role":"Analista de Expansão Territorial","icon":"🗺️","task":"Desempenho territorial por Cidade PIVOT"},
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
    if pd.isna(value):
        return "—"
    return f"{float(value or 0):,.0f}".replace(",", ".")

def price(value):
    if pd.isna(value):
        return "—"
    return f"R$ {float(value or 0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def percentage(value):
    if pd.isna(value):
        return "—"
    return f"{float(value):.2%}".replace(".", ",")

def show_table(frame, **kwargs):
    """Mostra tabelas com inteiros sem casas; preço médio e percentuais mantêm precisão."""
    if frame is None or frame.empty:
        return st.dataframe(frame, use_container_width=True, **kwargs)
    display = frame.copy()
    for column in display.columns:
        if not pd.api.types.is_numeric_dtype(display[column]):
            continue
        name = str(column).casefold()
        values = pd.to_numeric(display[column], errors="coerce")
        if any(term in name for term in ("p.p.", "pontos percentuais")):
            display[column] = values.map(lambda value: f"{value:.2f} p.p.".replace(".", ",") if pd.notna(value) else "—")
        elif "%" in name or "atingimento" in name or "margem percentual" in name:
            scale = 100
            display[column] = values.map(lambda value: f"{value * scale:.2f}%".replace(".", ",") if pd.notna(value) else "—")
        elif any(term in name for term in ("preço médio", "preco medio", "preço/kg", "preco/kg", "ticket médio", "ticket medio")):
            display[column] = values.map(price)
        elif any(term in name for term in ("r$", "faturamento", "receita", "valor", "margem", "custo", "sell-in", "meta")):
            display[column] = values.map(money)
        elif any(term in name for term in ("peso", " kg", "(kg)", "volume")):
            display[column] = values.map(lambda value: f"{number(value)} kg" if pd.notna(value) else "—")
        else:
            display[column] = values.map(number)
    return st.dataframe(display, use_container_width=True, **kwargs)

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

def show_chart(figure, **kwargs):
    figure.update_yaxes(tickformat=",.0f")
    kwargs.setdefault("use_container_width", True)
    return st.plotly_chart(figure, **kwargs)

def format_delivery_data(value, key=""):
    if isinstance(value, dict):
        return {name: format_delivery_data(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [format_delivery_data(item, key) for item in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        name = str(key).casefold()
        if any(term in name for term in ("atingimento","attainment","percentual","margem %","variacao %","variação %","pct")):
            return percentage(value)
        if any(term in name for term in ("preço médio","preco medio","preço/kg","preco/kg")):
            return price(value)
        if any(term in name for term in ("r$","_rs","faturamento","receita","valor","margem","custo","meta","sell_in")):
            return money(value)
        if "kg" in name or "peso" in name:
            return f"{number(value)} kg"
        return number(value)
    return value

def show_delivery_data(value):
    st.json(format_delivery_data(value), expanded=False)

def kpi(label, value, note="Base conectada"):
    st.metric(label, value, help=note)

def heading(person, period, routine):
    st.subheader(f"{person['icon']} {person['name']} · {person['area']}")
    st.caption(f"{person['role']}  |  Frequência: {routine['frequency']} às {routine['time']}  |  {routine['task']}  |  Referência: {period}")

def report_jeandro(sales, targets, period):
    if sales.empty or "Data" not in sales:
        st.info("Não há histórico de vendas para construir a visão mensal.")
        return
    base = sales.copy()
    base["Data"] = pd.to_datetime(base["Data"], errors="coerce")
    base = base.dropna(subset=["Data"])
    base["_Mes"] = base["Data"].dt.to_period("M").dt.to_timestamp()
    history = base.groupby("_Mes").agg(
        **{"Faturamento realizado (R$)":("Faturamento","sum"),"Volume realizado (kg)":("Peso","sum")}
    ).reset_index().rename(columns={"_Mes":"Mês"})
    history = history.tail(24)
    st.markdown("**Histórico mensal · últimos 24 meses disponíveis**")
    left, right = st.columns(2)
    with left:
        show_chart(px.line(history, x="Mês", y="Faturamento realizado (R$)", markers=True,
            title="Faturamento mensal histórico"), use_container_width=True)
    with right:
        show_chart(px.line(history, x="Mês", y="Volume realizado (kg)", markers=True,
            title="Volume mensal histórico"), use_container_width=True)
    revenue_forecast = forecast_year(base, method="hybrid", scenario="base")
    forecast_revenue = revenue_forecast["months"].copy()
    forecast_kg_source = base.assign(Faturamento=pd.to_numeric(base["Peso"], errors="coerce").fillna(0))
    forecast_kg = forecast_year(forecast_kg_source, method="hybrid", scenario="base")["months"].copy()
    year = int(revenue_forecast["year"])
    forecast_revenue["Projeção R$"] = forecast_revenue["forecast"]
    forecast_kg["Projeção KG"] = forecast_kg["forecast"]
    month_map = forecast_revenue[["mes","actual","Projeção R$","status"]].merge(
        forecast_kg[["mes","actual","Projeção KG"]].rename(columns={"actual":"Realizado KG"}), on="mes", how="left"
    )
    month_map["Mês"] = month_map["mes"].map(lambda month: f"{int(month):02d}/{year}")
    month_map = month_map.rename(columns={"actual":"Realizado R$","status":"Situação"})
    target = targets.copy()
    if not target.empty and "Competência" in target:
        target["Competência"] = pd.to_datetime(target["Competência"], errors="coerce")
        target = target[target["Competência"].dt.year.eq(year)]
        target_month = target.groupby(target["Competência"].dt.month).agg(
            **{"Meta R$":("Meta R$","sum"),"Meta KG":("Meta KG","sum")}
        ).reset_index(names="mes")
        month_map = month_map.merge(target_month, on="mes", how="left")
    else:
        month_map["Meta R$"] = 0
        month_map["Meta KG"] = 0
    month_map[["Meta R$","Meta KG"]] = month_map[["Meta R$","Meta KG"]].fillna(0)
    month_map["Atingimento projetado R$"] = month_map["Projeção R$"].div(month_map["Meta R$"]).where(month_map["Meta R$"].ne(0))
    month_map["Atingimento projetado KG"] = month_map["Projeção KG"].div(month_map["Meta KG"]).where(month_map["Meta KG"].ne(0))
    display_columns = ["Mês","Situação","Realizado R$","Projeção R$","Meta R$","Atingimento projetado R$",
                       "Realizado KG","Projeção KG","Meta KG","Atingimento projetado KG"]
    month_map = month_map[display_columns]
    st.markdown(f"**Realizado e projeção mês a mês · {year}**")
    st.caption("Projeção híbrida do METALFORTE 360: combina sazonalidade histórica, comparação com o ano anterior e ritmo realizado no ano. Meses futuros são estimativas, não metas.")
    show_chart(px.line(month_map, x="Mês", y=["Realizado R$","Projeção R$","Meta R$"],
        markers=True, title=f"Faturamento · realizado, projeção e meta {year}"), use_container_width=True)
    show_table(month_map, hide_index=True)
    current = month_slice(base, period)
    target_current = targets.copy()
    if not target_current.empty and "Competência" in target_current:
        target_current = target_current[pd.to_datetime(target_current["Competência"], errors="coerce").dt.to_period("M").eq(period)]
    actual_rs, meta_rs = total(current, "Faturamento"), total(target_current, "Meta R$")
    actual_kg, meta_kg = total(current, "Peso"), total(target_current, "Meta KG")
    avg_price = actual_rs / actual_kg if actual_kg else 0
    a,b,c,d = st.columns(4)
    with a: kpi("Realizado do mês", money(actual_rs))
    with b: kpi("Meta R$", money(meta_rs))
    with c: kpi("Atingimento", percentage(actual_rs / meta_rs) if meta_rs else "Sem meta")
    with d: kpi("Preço médio", price(avg_price))
    e,f = st.columns(2)
    with e: kpi("Volume realizado", f"{number(actual_kg)} kg")
    with f: kpi("Meta KG", f"{number(meta_kg)} kg")
    if target_current.empty:
        st.warning("A base de metas não trouxe linhas para este mês. O painel não estima metas ausentes.")

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
        show_table(merged, hide_index=True)
    else:
        show_table(now, hide_index=True)
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
        show_table(table, hide_index=True)
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
        show_chart(px.bar(daily, x="Data", y="Faturamento", title="Ritmo diário de faturamento"), use_container_width=True)
    seller = "Vendedor Painel" if "Vendedor Painel" in current else "Vendedor"
    table = top_table(current, seller, "Faturamento", 12)
    if not table.empty:
        st.markdown("**Performance por vendedor**")
        show_table(table, hide_index=True)

def report_uandson(sales, stock, flow):
    if stock is not None and not stock.empty:
        analysis = build_inventory_analysis(stock, sales, months=3)
        risk = analysis[analysis["Cobertura"].isin(["Ruptura", "Baixo (≤30 dias)"])].copy()
        a,b,c = st.columns(3)
        with a: kpi("Produtos com risco", number(len(risk)), "Ruptura ou cobertura de até 30 dias")
        with b: kpi("Aguardando estoque", f"{number(total(analysis, 'Aguardando estoque (kg)'))} kg")
        with c: kpi("Excesso potencial", f"{number(total(analysis, 'Excesso potencial (kg)'))} kg")
        if not risk.empty:
            show_table(risk[["Produto Codigo","Produto","Cobertura","Estoque disponível (kg)","Venda média diária (kg)","Dias de estoque"]].head(20), hide_index=True)
    else:
        st.warning("A fotografia de estoque não está disponível na base conectada.")
    if flow is not None and not flow.empty:
        st.markdown("**Fluxo de pedidos**")
        st.caption(f"{number(len(flow))} registros na base de fluxo. Consulte os campos de processo abaixo; a base é exibida sem reinterpretar etapas.")
        preferred = [c for c in ("Pedido","Cliente Painel","Vendedor Painel","Produto","Peso","Valor","Status","Etapa","Data Pedido","Data Liberação","Data Entrega") if c in flow]
        show_table(flow[preferred].head(30) if preferred else flow.head(30), hide_index=True)
    else:
        st.info("A base de fluxo de pedidos não retornou registros.")

def report_wilton(sales):
    current = month_slice(sales, latest_period(sales))
    if "Cidade PIVOT" in current:
        dimension = "Cidade PIVOT"
    elif "Cluster PIVOT" in current:
        dimension = "Cluster PIVOT"
    else:
        dimension = "Município"
    if dimension not in current:
        st.warning("A base não contém Cidade PIVOT nem município para esta visualização.")
        return
    table = top_table(current, dimension, "Faturamento", 30)
    if table.empty:
        st.info("A base não trouxe vendas agrupáveis por Cidade PIVOT no período.")
        return
    table = table.rename(columns={"Faturamento":"Faturamento (R$)"})
    st.markdown(f"**Faturamento por {dimension} · mês mais recente**")
    show_table(table, hide_index=True)
    show_chart(px.bar(table.head(15), x=dimension, y="Faturamento (R$)", title=f"Faturamento por {dimension}"), use_container_width=True)

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


OFFICE_CONFIG_PATH = "escritorio/configuracao.json"

def default_routines():
    return {
        person["name"]: {
            "frequency": "Diária",
            "time": "08:30",
            "task": person["task"],
            "enabled": True,
        }
        for person in PEOPLE
    }

def load_routines():
    try:
        saved = json.loads(download_bytes(object_path=OFFICE_CONFIG_PATH).decode("utf-8"))
        defaults = default_routines()
        for name, routine in saved.items():
            if name in defaults and isinstance(routine, dict):
                defaults[name].update(routine)
        return defaults
    except Exception:
        return default_routines()

def save_routines(routines):
    payload = json.dumps(routines, ensure_ascii=False, indent=2).encode("utf-8")
    upload_bytes(payload, OFFICE_CONFIG_PATH, "application/json; charset=utf-8")

def build_delivery_snapshot(sales, targets, stock, period, routines):
    month = month_slice(sales, period)
    target = targets.copy()
    if not target.empty and "Competência" in target:
        target["Competência"] = pd.to_datetime(target["Competência"], errors="coerce")
        target = target[target["Competência"].dt.to_period("M").eq(period)]
    customer = "Cliente Painel" if "Cliente Painel" in month else "Cliente"
    product = "Grupo Produto" if "Grupo Produto" in month else "Produto"
    region = "Cidade PIVOT" if "Cidade PIVOT" in month else ("Cluster PIVOT" if "Cluster PIVOT" in month else "Município")
    sellers = "Vendedor Painel" if "Vendedor Painel" in month else "Vendedor"
    forecast_rs = forecast_year(sales, method="hybrid", scenario="base")
    forecast_kg = forecast_year(sales.assign(Faturamento=pd.to_numeric(sales["Peso"], errors="coerce").fillna(0)), method="hybrid", scenario="base")
    forecast_rows = forecast_rs["months"].merge(
        forecast_kg["months"][["mes","actual","forecast"]].rename(columns={"actual":"realizado_kg","forecast":"projecao_kg"}),
        on="mes", how="left"
    )
    target_monthly = {}
    if not targets.empty and "Competência" in targets:
        target_year = targets.copy()
        target_year["Competência"] = pd.to_datetime(target_year["Competência"], errors="coerce")
        target_year = target_year[target_year["Competência"].dt.year.eq(int(forecast_rs["year"]))]
        if not target_year.empty:
            grouped_targets = target_year.groupby(target_year["Competência"].dt.month).agg({"Meta R$":"sum","Meta KG":"sum"})
            target_monthly = grouped_targets.to_dict("index")
    monthly_projection = []
    for row in forecast_rows.to_dict("records"):
        month_target = target_monthly.get(int(row["mes"]), {})
        meta_rs = float(month_target.get("Meta R$", 0) or 0)
        meta_kg = float(month_target.get("Meta KG", 0) or 0)
        proj_rs = float(row["forecast"] or 0)
        proj_kg = float(row["projecao_kg"] or 0)
        monthly_projection.append({
            "mes": f"{int(row['mes']):02d}/{forecast_rs['year']}",
            "situacao": row["status"],
            "realizado_rs": float(row["actual"] or 0),
            "projecao_rs": proj_rs,
            "meta_rs": meta_rs,
            "atingimento_rs": proj_rs / meta_rs if meta_rs else None,
            "realizado_kg": float(row["realizado_kg"] or 0),
            "projecao_kg": proj_kg,
            "meta_kg": meta_kg,
            "atingimento_kg": proj_kg / meta_kg if meta_kg else None,
        })
    history_rows = sales.copy()
    history_rows["Data"] = pd.to_datetime(history_rows["Data"], errors="coerce")
    history_rows["_Mes"] = history_rows["Data"].dt.to_period("M").dt.to_timestamp()
    monthly_history = history_rows.groupby("_Mes").agg(
        faturamento_rs=("Faturamento","sum"), volume_kg=("Peso","sum")
    ).tail(24).reset_index().rename(columns={"_Mes":"mes"}).to_dict("records")
    outputs = {
        "Jeandro": {
            "historico_mensal_24m": monthly_history,
            "projecao_mensal": monthly_projection,
            "metodologia": "Projeção híbrida por mês: sazonalidade histórica, ano anterior e ritmo realizado.",
        },
        "Nayane": {"portfolio_top": top_table(month, product, "Faturamento", 5).to_dict("records")},
        "Lucas": {
            "sell_in_top": top_table(month, customer, "Faturamento", 5).to_dict("records"),
            "observacao": "A base disponível mede sell-in; não há medição de sell-out.",
        },
        "Bruno": {
            "faturamento_rs": total(month, "Faturamento"),
            "faturamento_kg": total(month, "Peso"),
            "pedidos": int(month["Pedido"].nunique()) if "Pedido" in month else 0,
            "vendedores_top": top_table(month, sellers, "Faturamento", 5).to_dict("records"),
        },
        "Uandson": {"status_estoque": "Base disponível" if stock is not None and not stock.empty else "Base não carregada"},
        "Wilton": {"cidades_pivot_top": top_table(month, region, "Faturamento", 10).to_dict("records")},
        "Breno": {"status": "Aguardando briefing ou arquivo auxiliar"},
    }
    if stock is not None and not stock.empty:
        analysis = build_inventory_analysis(stock, sales, months=3)
        risk = analysis[analysis["Cobertura"].isin(["Ruptura", "Baixo (≤30 dias)"])]
        outputs["Uandson"].update({
            "produtos_em_risco": int(len(risk)),
            "produtos_aguardando_estoque": int((analysis["Aguardando estoque (kg)"] > 0).sum()),
        })
    return {
        "data_execucao": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"),
        "competencia": str(period),
        "rotinas": routines,
        "entregas": outputs,
    }

def show_routine_controls(routines, role):
    if role != "admin":
        st.info("As rotinas são definidas pelo administrador do app.")
        return routines
    with st.expander("⚙️ Configurar rotinas e frequências", expanded=False):
        person_name = st.selectbox("Colaborador", [p["name"] for p in PEOPLE], key="routine_person")
        current = routines[person_name]
        with st.form("routine_config_form"):
            frequency = st.selectbox("Frequência", ["Diária", "Semanal", "Mensal"], index=["Diária", "Semanal", "Mensal"].index(current["frequency"]) if current["frequency"] in ["Diária", "Semanal", "Mensal"] else 0)
            run_time = st.time_input("Horário local", value=datetime.strptime(current["time"], "%H:%M").time())
            task = st.text_area("Rotina e entrega esperada", value=current["task"], height=100)
            enabled = st.checkbox("Rotina ativa", value=bool(current["enabled"]))
            save = st.form_submit_button("Salvar no Supabase", type="primary")
        if save:
            routines[person_name] = {"frequency": frequency, "time": run_time.strftime("%H:%M"), "task": task.strip(), "enabled": enabled}
            try:
                save_routines(routines)
                st.success("Rotina salva no armazenamento privado do Supabase.")
                st.rerun()
            except Exception as exc:
                st.error(f"Não foi possível salvar a rotina ({type(exc).__name__}).")
    return routines

def save_daily_delivery(sales, targets, stock, period, routines):
    path = f"escritorio/entregas/{datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%Y-%m-%d')}.json"
    snapshot = build_delivery_snapshot(sales, targets, stock, period, routines)
    upload_bytes(json.dumps(snapshot, ensure_ascii=False, default=str, indent=2).encode("utf-8"), path, "application/json; charset=utf-8")
    return path, snapshot

def show_delivery_history():
    st.markdown("**Entregas registradas**")
    delivery_day = st.date_input("Data da entrega", value=datetime.now(ZoneInfo("America/Sao_Paulo")).date(), key="delivery_history_date")
    path = f"escritorio/entregas/{delivery_day.strftime('%Y-%m-%d')}.json"
    try:
        payload = json.loads(download_bytes(object_path=path).decode("utf-8"))
        st.caption(f"Execução registrada em {payload.get('data_execucao', 'horário indisponível')} · competência {payload.get('competencia', '—')}")
        show_delivery_data(payload.get("entregas", {}))
    except Exception:
        st.caption("Ainda não há entrega salva nessa data.")


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
        sales, targets, stock, flow, status = read_sources(str(datetime.now(ZoneInfo("America/Sao_Paulo")).date()))
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
    routines = load_routines()
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
    routines = show_routine_controls(routines, role)
    with st.expander("▶️ Executar rotina inicial e salvar entrega de hoje", expanded=True):
        st.caption("A execução usa a última competência existente nas bases oficiais e registra os indicadores no Supabase para consulta posterior.")
        if st.button("Gerar entregas iniciais dos 7 colaboradores", type="primary"):
            try:
                path, snapshot = save_daily_delivery(sales, targets, stock, period, routines)
                st.success(f"Entrega inicial registrada: {path}")
                show_delivery_data(snapshot["entregas"])
            except Exception as exc:
                st.error(f"Não foi possível registrar as entregas ({type(exc).__name__}).")
        show_delivery_history()
    st.markdown("""
    <style>
    .office-room{min-height:218px;border:2px solid #d8cfbf;border-radius:19px;background:#fffdf9;padding:13px;box-shadow:0 5px 0 #e7dece;transition:all .18s ease}
    .office-room.selected{border-color:#e2572b;box-shadow:0 6px 0 #efc6ad,0 0 0 2px #e2572b1c}
    .office-room-label{font-size:10px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:#8b8578}
    .office-room-title{font-size:14px;font-weight:800;color:#17233c;margin:3px 0 9px}
    .office-interior{position:relative;height:112px;border:1px solid #ece4d7;border-radius:13px;background:var(--wall);display:flex;align-items:center;justify-content:center;overflow:hidden}
    .office-window{position:absolute;right:10px;top:9px;width:30px;height:13px;border:1px solid #b8c8d8;border-radius:3px;background:#eef4f8}
    .office-plant{position:absolute;left:10px;top:8px;font-size:15px}
    .office-desk{position:absolute;left:13px;bottom:8px;width:38px;height:12px;border:1px solid #c4a77c;border-radius:5px 5px 2px 2px;background:#d9bf98}
    .office-person{display:flex;align-items:center;gap:9px;max-width:90%;padding:8px 11px;border:1px solid #e6ded1;border-radius:12px;background:#fffdf9ed;box-shadow:0 2px 6px #17233c12}
    .office-avatar{width:40px;height:40px;display:grid;place-items:center;border-radius:50%;background:#ffffffb5;font-size:22px}
    .office-name{font-size:13px;font-weight:800;color:#17233c}.office-role{font-size:10px;color:#7d8798}
    </style>
    """, unsafe_allow_html=True)
    st.markdown("### 🏢 Escritório · mapa das salas")
    st.caption("Escolha uma sala para abrir os relatórios e análises do responsável. As rotinas e frequências ficam visíveis em cada mesa.")
    st.markdown(
        "<div style='padding:8px 12px;margin-bottom:12px;border:1px solid #ded4c4;border-radius:12px;background:#fffdf9;color:#8b8578;font-size:11px;font-weight:800'>🚪 ENTRADA PRINCIPAL <span style='float:right;font-weight:600'>Corredor central · salas por especialidade</span></div>",
        unsafe_allow_html=True,
    )
    room_meta = {
        "Jeandro": ("Sala de Planejamento", "#f7e8d2"),
        "Nayane": ("Estúdio de Marcas", "#f8e2de"),
        "Lucas": ("Sala de Trade", "#e5eee5"),
        "Bruno": ("Administração Comercial", "#e3eaf6"),
        "Uandson": ("Sala de S&OP", "#e8e4f4"),
        "Wilton": ("Núcleo Territorial", "#e4edf0"),
        "Breno": ("Estúdio Criativo", "#f3e7d8"),
    }
    st.session_state.setdefault("office_selected_person", PEOPLE[0]["name"])
    room_columns = st.columns(3)
    for index, person in enumerate(PEOPLE):
        sala, parede = room_meta[person["name"]]
        routine = routines[person["name"]]
        is_selected = st.session_state["office_selected_person"] == person["name"]
        state = "Ativa" if routine["enabled"] else "Pausada"
        with room_columns[index % 3]:
            with st.container(border=True):
                st.markdown(
                    f"<div class='office-room {'selected' if is_selected else ''}' style='--wall:{parede}'>"
                    f"<div class='office-room-label'>{person['area']}</div>"
                    f"<div class='office-room-title'>{sala}</div>"
                    f"<div class='office-interior' style='--wall:{parede}'>"
                    "<span class='office-plant'>🪴</span><span class='office-window'></span>"
                    f"<div class='office-person'><span class='office-avatar'>{person['icon']}</span>"
                    f"<span><span class='office-name'>{person['name']}</span><br>"
                    f"<span class='office-role'>{person['role']}</span></span></div>"
                    "<span class='office-desk'></span></div></div>",
                    unsafe_allow_html=True,
                )
                st.caption(f"🕒 {routine['frequency']} · {routine['time']} · {state}")
                st.caption(routine["task"])
                if st.button(
                    "✅ Mesa selecionada" if is_selected else "Abrir esta sala",
                    key=f"open_office_room_{person['name']}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                ):
                    st.session_state["office_selected_person"] = person["name"]
                    st.rerun()
    selected_person = next(
        (person for person in PEOPLE if person["name"] == st.session_state["office_selected_person"]),
        PEOPLE[0],
    )
    selected_render = {
        "Jeandro": lambda: report_jeandro(sales, targets, period),
        "Nayane": lambda: report_nayane(sales, period),
        "Lucas": lambda: report_lucas(sales),
        "Bruno": lambda: report_bruno(sales),
        "Uandson": lambda: report_uandson(sales, stock, flow),
        "Wilton": lambda: report_wilton(sales),
        "Breno": report_breno,
    }
    st.divider()
    heading(selected_person, period_label, routines[selected_person["name"]])
    selected_render[selected_person["name"]]()

if __name__ == "__main__":
    main()
