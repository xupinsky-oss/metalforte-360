import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import html
from pathlib import Path
from src.data import load_data,apply_filters
from src.analytics import metrics,group_metrics,client_classification,quick_insights,forecast_year,price_analysis,build_opportunities,monitoring_snapshot,compare_periods,commercial_command_center,market_watch
from src.assistant import answer
from src.totvs import TotvsGoodDataConnector,from_streamlit_secrets,REPORTS

st.set_page_config(page_title="Metalforte 360",layout="wide",page_icon="🏭")
px.defaults.template="plotly_dark"
px.defaults.color_discrete_sequence=["#F36A2D","#2F8FD8","#34B27B","#F2B84B","#A78BFA","#EC6F91"]
def brl(v): return (f"R$ {v:,.0f}").replace(",",".")
def brl2(v): return brl(v)
def pct(v): return f"{v*100:.1f}%".replace(".",",")
def pp(v): return f"{v:+.1f}".replace(".",",")+" p.p."
@st.cache_data(show_spinner="Carregando Metalforte 360...")
def get_data(): return load_data()
def _is_fraction_percent(name):
    name=str(name).lower()
    return ("_pct" in name or "margem %" in name or name.endswith(" %") or any(term in name for term in ("variação %","variacao %","share","participação","participacao","cobertura","atingimento"))) and "desvio_%" not in name

def _is_money_column(name):
    name=str(name).lower()
    return any(term in name for term in ("faturamento","receita","margem","valor","preço","preco","custo","ticket","benchmark","gap","projeção","projecao","realizado","impacto")) and not _is_fraction_percent(name) and "p.p." not in name

def _numeric_column_config(data):
    """Moeda em R$, margens em % e os demais números sem casas decimais."""
    config={}
    for col in data.columns:
        if not pd.api.types.is_numeric_dtype(data[col]): continue
        name=str(col).lower()
        if "p.p." in name or "delta_margem_pp" in name: fmt="%.1f p.p."
        elif "desvio_%" in name: fmt="%.2f%%"
        elif _is_fraction_percent(name): fmt="%.2f%%"
        elif _is_money_column(name): fmt="R$ %.0f"
        else: fmt="%.0f"
        config[col]=st.column_config.NumberColumn(format=fmt)
    return config
def show_table(data,**kwargs):
    display=data.copy()
    for col in display.columns:
        if pd.api.types.is_numeric_dtype(display[col]) and _is_fraction_percent(col):
            display[col]=display[col]*100
        elif pd.api.types.is_numeric_dtype(display[col]) and _is_money_column(col):
            display[col]=display[col].map(lambda value: brl(value) if pd.notna(value) else "—")
    inferred=_numeric_column_config(display)
    inferred.update(kwargs.pop("column_config",{}) or {})
    return st.dataframe(display,column_config=inferred,**kwargs)
def show_chart(fig,**kwargs):
    fig.update_layout(font=dict(size=14,color="#F5F7FA"),title_font=dict(size=18,color="#FFFFFF"),legend_font=dict(size=13,color="#F5F7FA"),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#121923",margin=dict(l=28,r=28,t=60,b=42),hoverlabel=dict(font_size=14))
    fig.update_xaxes(tickfont=dict(size=12,color="#E7EDF5"),title_font=dict(size=14,color="#F5F7FA"),gridcolor="#2A3442",zerolinecolor="#3B4655")
    fig.update_yaxes(tickfont=dict(size=12,color="#E7EDF5"),title_font=dict(size=14,color="#F5F7FA"),gridcolor="#2A3442",zerolinecolor="#3B4655")
    for axis_name in ("xaxis","yaxis"):
        axis=getattr(fig.layout,axis_name,None); title=((axis.title.text if axis and axis.title else "") or "").lower()
        if "desvio_%" in title: axis.update(tickformat=",.1f",ticksuffix="%")
        elif any(term in title for term in ("margem %","margem_pct","participação","participacao","share")): axis.update(tickformat=".1%")
        elif any(term in title for term in ("faturamento","receita","margem","valor","preço","preco","custo","ticket","benchmark","gap")): axis.update(tickprefix="R$ ",tickformat=",.0f")
        elif title and not any(term in title for term in ("data","mês","mes","cliente","produto","vendedor","uf","município","municipio")): axis.update(tickformat=",.0f")
    return st.plotly_chart(fig,width="stretch",**kwargs)
df=get_data(); base_min=df["Data"].min().date(); base_max=df["Data"].max().date(); last_update=base_max.strftime("%d/%m/%Y")
today=pd.Timestamp.today().date(); month_start=today.replace(day=1)
default_start=month_start if base_min<=month_start<=base_max else base_max.replace(day=1)
st.title("🏭 Metalforte 360"); st.caption(f"Faturamento • margem • geografia • portfólio • preço • planejamento • IA • integração TOTVS  |  Última atualização: {last_update}")
st.markdown("""<style>
html,body,[class*="css"]{font-size:16px;color:#F5F7FA}
.block-container{padding-top:1.6rem;padding-bottom:3rem;max-width:1800px}
h1{font-size:2.25rem!important;letter-spacing:-.02em} h2{font-size:1.65rem!important} h3{font-size:1.28rem!important}
[data-testid="stCaptionContainer"]{font-size:.92rem;color:#BFC9D8}
[data-testid="stSidebar"]{background:#111821;border-right:1px solid #2A3442}
[data-testid="stSidebar"] label,[data-testid="stSidebar"] p{font-size:.95rem!important;color:#E7EDF5!important}
[data-testid="stMetric"]{background:#171F2B;border:1px solid #2D3948;border-radius:12px;padding:1rem 1.05rem;min-height:116px}
[data-testid="stMetricLabel"] p{font-size:.9rem!important;font-weight:650;color:#C8D2E0!important}
[data-testid="stMetricValue"]{font-size:clamp(1.3rem,1.7vw,2rem)!important;font-weight:750;color:#FFFFFF}
[data-testid="stMetricDelta"]{font-size:.88rem!important}
[data-baseweb="tab-list"]{gap:.3rem;overflow-x:auto}
[data-baseweb="tab"]{min-height:46px;padding:.7rem .9rem;font-size:.92rem;font-weight:650;color:#C8D2E0;white-space:nowrap}
[aria-selected="true"][data-baseweb="tab"]{color:#FFFFFF;background:#1D2734;border-radius:9px 9px 0 0}
.mf-status{display:inline-flex;align-items:center;gap:.5rem;padding:.45rem .8rem;border:1px solid #347A55;border-radius:999px;font-size:.9rem;font-weight:700;background:#15251D;color:#DDF8E8}
.mf-dot{width:.58rem;height:.58rem;border-radius:50%;display:inline-block;background:#35C77B;box-shadow:0 0 0 4px #35C77B25}
.mf-alert{border-left:5px solid #E3A62F;padding:.9rem 1rem;margin:.55rem 0;background:#282314;color:#FFF4CF;border-radius:0 .55rem .55rem 0;font-size:.98rem;line-height:1.45}
.mf-alert small{font-size:.88rem;color:#E8DFBF}.mf-critical{border-left-color:#F05B63;background:#2A181B;color:#FFE4E6}.mf-critical small{color:#F0C4C8}.mf-info{border-left-color:#419BE0;background:#142434;color:#DDEFFF}.mf-info small{color:#BDD8EF}
.mw-strip{display:flex;gap:.65rem;overflow-x:auto;padding:.25rem 0 .8rem}.mw-quote{min-width:210px;background:#121923;border:1px solid #2D3948;border-radius:9px;padding:.7rem .8rem}.mw-name{font-size:.78rem;color:#AEBAC9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mw-value{font-size:1rem;font-weight:750;color:#FFF;margin-top:.2rem}.mw-up{color:#62C894}.mw-down{color:#F18A68}.mw-flat{color:#C5CEDA}
[data-testid="stDataFrame"]{border:1px solid #2D3948;border-radius:10px;overflow:hidden}
button,input,[role="combobox"]{font-size:.95rem!important}
@media(max-width:900px){.block-container{padding-left:1rem;padding-right:1rem}[data-testid="stMetric"]{min-height:104px;padding:.8rem}[data-testid="stMetricValue"]{font-size:1.35rem!important}}
</style>""",unsafe_allow_html=True)

with st.sidebar:
    st.header("Filtros")
    st.markdown(f'<span class="mf-status"><span class="mf-dot"></span> Atualizada em {last_update}</span>',unsafe_allow_html=True)
    st.subheader("Período")
    selected_dates=st.date_input("Selecione no calendário",value=(default_start,base_max),min_value=base_min,max_value=base_max,format="DD/MM/YYYY",help="O mês atual já vem selecionado. Clique para escolher outro intervalo.")
    if isinstance(selected_dates,(tuple,list)) and len(selected_dates)==2: start_date,end_date=selected_dates
    elif isinstance(selected_dates,(tuple,list)) and len(selected_dates)==1: start_date=end_date=selected_dates[0]
    else: start_date=end_date=selected_dates
    st.caption(f"Período disponível: {base_min.strftime('%d/%m/%Y')} a {last_update}")
    names={1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
    filial=st.multiselect("Filial",sorted(df["Filial"].unique())); uf=st.multiselect("UF",sorted(df["UF"].unique())); pool=df if not uf else df[df["UF"].isin(uf)]; city=st.multiselect("Município",sorted(pool["Município"].unique())); vend=st.multiselect("Vendedor",sorted(df["Vendedor"].unique())); grupo=st.multiselect("Grupo Produto",sorted(df["Grupo Produto"].unique())); tipo=st.multiselect("Tipo Produto",sorted(df["Tipo Produto"].unique())); esp=st.multiselect("Espessura",sorted(df["Espessura"].dropna().unique())); ct=st.text_input("Buscar cliente"); pt=st.text_input("Buscar produto")
f=apply_filters(df,filial=filial,uf=uf,municipio=city,vendedor=vend,grupo=grupo,tipo=tipo,espessura=esp,cliente_text=ct,produto_text=pt,start_date=start_date,end_date=end_date)
# Forecast, meta anual e alertas YTD precisam do histórico completo. O calendário
# continua controlando todas as análises do período, mas não corta a série usada
# para projetar o fechamento do ano.
monitor_scope=apply_filters(df,filial=filial,uf=uf,municipio=city,vendedor=vend,grupo=grupo,tipo=tipo,espessura=esp,cliente_text=ct,produto_text=pt)

if f.empty:
    st.warning("Nenhum registro encontrado com os filtros atuais. Ajuste os filtros para continuar a análise.")

tabs=st.tabs(["Command Center","Market Watch","Resumo","Drivers & Tendências","Carteira do Vendedor","Clientes 360","Portfólio","Geografia","Preço & Margem","Forecast & Oportunidades","Assistente IA","Integrações","Auditoria"])
with tabs[0]:
    s=monitoring_snapshot(monitor_scope)
    asof=s['as_of'].strftime('%d/%m/%Y') if pd.notna(s['as_of']) else 'sem dados'
    command=commercial_command_center(monitor_scope,start_date,end_date); cm=command['current']; pm=command['previous']
    st.subheader('Command Center Comercial')
    st.markdown(f'<span class="mf-status"><span class="mf-dot"></span> Base atualizada até {asof} • calendário: {start_date.strftime("%d/%m/%Y")} a {end_date.strftime("%d/%m/%Y")}</span>',unsafe_allow_html=True)
    st.caption(f"Comparativo automático: {command['period']['prev_start'].strftime('%d/%m/%Y')} a {command['period']['prev_end'].strftime('%d/%m/%Y')} • todos os filtros globais aplicados")
    k=st.columns(6)
    k[0].metric('Faturamento',brl(cm['revenue']),delta=f"{command['revenue_growth']:+.1%}".replace('.',','))
    k[1].metric('Margem',brl(cm['margin']),delta=pp(command['margin_pp']))
    k[2].metric('Margem %',pct(cm['margin_pct']))
    k[3].metric('Clientes ativos',f"{cm['clients']:,}".replace(',','.'),delta=f"{cm['clients']-pm['clients']:+d}")
    k[4].metric('Produtos ativos',f"{cm['products']:,}".replace(',','.'),delta=f"{cm['products']-pm['products']:+d}")
    k[5].metric('Ticket médio',brl(cm['ticket']))

    c1,c2=st.columns([1.35,1])
    with c1:
        trend=command['trend']
        if not trend.empty:
            fig=go.Figure(); fig.add_bar(x=trend['Semana'],y=trend['Faturamento'],name='Faturamento semanal',marker_color='#2F8FD8'); fig.add_scatter(x=trend['Semana'],y=trend['Média móvel 4S'],name='Tendência 4 semanas',line=dict(color='#F2B84B',width=3)); fig.update_layout(title='Tendência semanal de faturamento',legend=dict(orientation='h'),yaxis=dict(title='Faturamento')); show_chart(fig)
    with c2:
        sellers=command['sellers'].head(30)
        if not sellers.empty:
            sellers=sellers.copy(); sellers['volume_visual']=sellers['faturamento_atual'].clip(lower=0)+1
            fig=px.scatter(sellers,x='var_faturamento',y='delta_margem_pp',size='volume_visual',color='status',hover_name='Vendedor',hover_data={'faturamento_atual':':,.0f','valor_em_risco':':,.0f','clientes':':,.0f','volume_visual':False},title='Matriz de performance dos vendedores',labels={'var_faturamento':'Variação de faturamento','delta_margem_pp':'Δ Margem p.p.','status':'Situação'},color_discrete_map={'Evolução saudável':'#2F8FD8','Receita em queda':'#F2B84B','Margem em queda':'#A78BFA','Receita e margem em queda':'#F36A2D'})
            fig.add_hline(y=0,line_color='#94A3B8',line_width=1); fig.add_vline(x=0,line_color='#94A3B8',line_width=1); fig.update_xaxes(tickformat='.0%'); fig.update_yaxes(ticksuffix=' p.p.'); show_chart(fig)

    st.markdown('### Fila prioritária de clientes')
    st.caption('Prioridade combina valor perdido, relevância da carteira, inatividade e pressão de margem. O valor em risco é somente a queda observada versus o período anterior.')
    queue=command['clients'].copy()
    q1,q2,q3=st.columns([1.2,1.2,1])
    action_options=['Todas']+sorted(queue['ação_recomendada'].dropna().unique().tolist()) if not queue.empty else ['Todas']
    owner_options=['Todos']+sorted(queue['Vendedor'].dropna().astype(str).unique().tolist()) if not queue.empty else ['Todos']
    queue_action=q1.selectbox('Ação recomendada',action_options,key='cc_action'); queue_owner=q2.selectbox('Responsável',owner_options,key='cc_owner'); queue_rows=q3.selectbox('Clientes na fila',[15,30,50,100],index=1,key='cc_rows')
    if queue_action!='Todas': queue=queue[queue['ação_recomendada']==queue_action]
    if queue_owner!='Todos': queue=queue[queue['Vendedor'].astype(str)==queue_owner]
    if queue.empty: st.info('Nenhum cliente na fila com os critérios selecionados.')
    else:
        queue=queue.head(queue_rows).rename(columns={'faturamento_atual':'Faturamento atual','faturamento_anterior':'Faturamento anterior','delta_faturamento':'Δ Faturamento','margem_pct_atual':'Margem %','delta_margem_pp':'Δ Margem p.p.','valor_em_risco':'Valor em risco','dias_sem_compra':'Dias sem compra','ação_recomendada':'Próxima ação','prioridade':'Prioridade','ultima_compra':'Última compra'})
        show_table(queue[['Prioridade','Próxima ação','Vendedor','Cliente','UF','Faturamento atual','Δ Faturamento','Valor em risco','Margem %','Δ Margem p.p.','Dias sem compra','Última compra']],height=480,width='stretch',column_config={'Última compra':st.column_config.DateColumn(format='DD/MM/YYYY')})

    c1,c2=st.columns([1.25,1])
    with c1:
        products=command['products'].head(25)
        if not products.empty:
            products=products.copy(); products['volume_visual']=products['faturamento_atual'].clip(lower=0)+1
            fig=px.scatter(products,x='delta_faturamento',y='delta_margem_pp',size='volume_visual',color='sinal',hover_name='Grupo Produto',hover_data={'faturamento_atual':':,.0f','margem_pct_atual':':.1%','volume_visual':False},title='Sinais de mix: crescimento × qualidade de margem',labels={'delta_faturamento':'Δ Faturamento','delta_margem_pp':'Δ Margem p.p.','sinal':'Sinal'},color_discrete_map={'Crescimento rentável':'#2F8FD8','Crescimento com pressão':'#F2B84B','Queda com margem protegida':'#A78BFA','Queda com pressão':'#F36A2D'})
            fig.add_hline(y=0,line_color='#94A3B8',line_width=1); fig.add_vline(x=0,line_color='#94A3B8',line_width=1); fig.update_yaxes(ticksuffix=' p.p.'); show_chart(fig)
    with c2:
        risk=command['clients']; risk_total=risk['valor_em_risco'].sum() if not risk.empty else 0; falling=int((risk['delta_faturamento']<0).sum()) if not risk.empty else 0; margin_pressure=int((risk['delta_margem_pp']<0).sum()) if not risk.empty else 0
        st.markdown('### Radar de decisão')
        st.metric('Receita perdida na carteira',brl(risk_total),help='Soma das quedas por cliente versus o período anterior; não é previsão.')
        st.metric('Clientes em retração',f'{falling:,}'.replace(',','.'))
        st.metric('Clientes com pressão de margem',f'{margin_pressure:,}'.replace(',','.'))
        st.info('Sinais de mercado exibidos aqui são internos: mudança de mix, preço, geografia e comportamento da carteira. Dados externos de mercado ainda não estão conectados.')

    st.divider(); st.markdown('### Saúde anual e alertas estruturais')
    k=st.columns(3)
    k[0].metric('Faturamento YTD',brl(s['revenue']),delta=f"{s['yoy_revenue']:+.1%} YoY".replace('.',','))
    k[1].metric('Margem YTD',brl(s['margin']),delta=pp(s['yoy_margin_pp']))
    k[2].metric('Margem %',pct(s['margin_pct']))
    k=st.columns(3)
    k[0].metric('Projeção anual',brl(s['projected']))
    k[1].metric('Atingimento meta',pct(s['target_attainment']),delta=brl(s['projected']-s['target']))
    k[2].metric('Ritmo do mês',brl(s['month_pace']),delta=f"Realizado {brl(s['month_revenue'])}")
    st.markdown('### Alertas e decisões')
    if not s['alerts']: st.success('Nenhum alerta relevante no contexto selecionado.')
    else:
        for a in s['alerts']:
            css='mf-critical' if a['nível']=='Crítico' else 'mf-info' if a['nível']=='Informativo' else ''
            val=brl(a['valor']) if any(x in a['alerta'] for x in ['Gap','Margem negativa']) else (pct(a['valor']) if 'Cobertura' in a['alerta'] or 'Geografia' in a['alerta'] else f"{a['valor']:,.0f}".replace(',','.'))
            st.markdown(f"<div class='mf-alert {css}'><b>{a['nível']} • {a['alerta']}</b> — {val}<br><small>{a['contexto']} • <b>Próxima ação:</b> {a['ação']}</small></div>",unsafe_allow_html=True)
    c1,c2=st.columns([1.35,1])
    with c1:
        if not s['monthly'].empty:
            fig=go.Figure(); fig.add_bar(x=[names[x] for x in s['monthly'].mes],y=s['monthly'].faturamento,name='Faturamento',marker_color='#184a78'); fig.add_scatter(x=[names[x] for x in s['monthly'].mes],y=s['monthly'].margem_pct*100,name='Margem %',yaxis='y2',line=dict(color='#e0a100',width=3)); fig.update_layout(title='Pulso mensal',yaxis2=dict(overlaying='y',side='right',ticksuffix='%'),legend=dict(orientation='h')); show_chart(fig)
    with c2:
        if not s['sellers'].empty:
            show_chart(px.bar(s['sellers'].sort_values('faturamento'),x='faturamento',y='Vendedor',orientation='h',color='margem_pct',color_continuous_scale='RdYlGn',title='Vendedores: receita e qualidade de margem'))
        else: st.info('Sem vendedores no contexto selecionado.')
    c1,c2,c3,c4=st.columns(4); c1.metric('Clientes A em risco',s['inactive_a']); c2.metric('Perda em margem negativa',brl(s['negative_margin'])); c3.metric('Receita abaixo do benchmark',brl(s['below_benchmark'])); c4.metric('Cobertura benchmark',pct(s['benchmark_coverage']))
    if not s['at_risk'].empty:
        st.subheader('Fila de ação comercial')
        show_table(s['at_risk'][['vendedor','Cliente','UF','faturamento','margem_pct','ultima_compra','dias_sem_compra']].rename(columns={'vendedor':'Vendedor','faturamento':'Faturamento','margem_pct':'Margem %','ultima_compra':'Última compra','dias_sem_compra':'Dias sem compra'}),height=380,column_config={'Última compra':st.column_config.DateColumn(format='DD/MM/YYYY')})
with tabs[1]:
    st.subheader('Market Watch Comercial')
    st.caption('Movimentações do período contra a janela anterior de mesma duração. Alta e queda representam variação de faturamento, não cotação financeira.')
    wc1,wc2,wc3=st.columns([1.1,1,1])
    watch_dim=wc1.selectbox('Acompanhar por',['Vendedor','Cliente','Produto'],key='watch_dim')
    watch_top=wc2.selectbox('Quantidade no radar',[10,15,25,40],index=1,key='watch_top')
    watch_metric=wc3.selectbox('Ordenar por',['Maior impacto','Maiores altas','Maiores quedas'],key='watch_order')
    watch=market_watch(monitor_scope,start_date,end_date,watch_dim); movers=watch['movers'].copy(); wm=watch['current_metrics']; wp=watch['previous_metrics']
    if watch_metric=='Maiores altas': movers=movers.sort_values('delta_faturamento',ascending=False)
    elif watch_metric=='Maiores quedas': movers=movers.sort_values('delta_faturamento')
    else: movers=movers.sort_values('impacto',ascending=False)
    shown=movers.head(watch_top)
    quotes=[]
    for _,r in shown.head(12).iterrows():
        cls='mw-up' if r.delta_faturamento>0 else 'mw-down' if r.delta_faturamento<0 else 'mw-flat'; arrow='▲' if r.delta_faturamento>0 else '▼' if r.delta_faturamento<0 else '●'; variation=f"{r.var_faturamento:+.1%}" if pd.notna(r.var_faturamento) else 'novo/sem base'
        quotes.append(f"<div class='mw-quote'><div class='mw-name'>{html.escape(str(r[watch_dim]))}</div><div class='mw-value'>{brl(r.faturamento_atual)}</div><div class='{cls}'>{arrow} {variation.replace('.',',')} • {brl(r.delta_faturamento)}</div></div>")
    if quotes: st.markdown("<div class='mw-strip'>"+''.join(quotes)+"</div>",unsafe_allow_html=True)
    k=st.columns(6); revenue_delta=wm['revenue']-wp['revenue']; revenue_var=revenue_delta/wp['revenue'] if wp['revenue'] else 0
    k[0].metric('Faturamento do período',brl(wm['revenue']),delta=f"{revenue_var:+.1%}".replace('.',',')); k[1].metric('Movimento líquido',brl(revenue_delta)); k[2].metric('Margem %',pct(wm['margin_pct']),delta=pp((wm['margin_pct']-wp['margin_pct'])*100)); k[3].metric('Em alta',f"{(movers.movimento=='Alta').sum():,}".replace(',','.')); k[4].metric('Em queda',f"{(movers.movimento=='Queda').sum():,}".replace(',','.')); k[5].metric('Entidades ativas',f"{(movers.faturamento_atual!=0).sum():,}".replace(',','.'))
    c1,c2=st.columns([1.2,1])
    with c1:
        if not watch['tape'].empty:
            fig=px.line(watch['tape'],x='Dia do período',y='Acumulado',color='Período',markers=True,title='Curva acumulada do período',labels={'Acumulado':'Faturamento acumulado'},color_discrete_map={'Atual':'#2F8FD8','Anterior':'#94A3B8'}); fig.update_traces(line_width=3); show_chart(fig)
    with c2:
        if not shown.empty:
            chart=shown.sort_values('delta_faturamento').copy(); chart['Sinal']=chart['delta_faturamento'].map(lambda v:'Alta' if v>0 else 'Queda' if v<0 else 'Estável')
            fig=px.bar(chart,x='delta_faturamento',y=watch_dim,orientation='h',color='Sinal',title=f'Movimentações por {watch_dim.lower()}',labels={'delta_faturamento':'Δ Faturamento'},color_discrete_map={'Alta':'#2F8FD8','Queda':'#F36A2D','Estável':'#94A3B8'},hover_data={'faturamento_atual':':,.0f','margem_pct_atual':':.1%','delta_margem_pp':':.1f'}); fig.add_vline(x=0,line_color='#CBD5E1',line_width=1); show_chart(fig)
    st.markdown('### Quadro de movimentações')
    board=shown.rename(columns={'faturamento_atual':'Faturamento atual','faturamento_anterior':'Faturamento anterior','delta_faturamento':'Δ Faturamento','var_faturamento':'Variação %','margem_pct_atual':'Margem %','delta_margem_pp':'Δ Margem p.p.','movimento':'Movimento','impacto':'Impacto'})
    if not board.empty: show_table(board[[watch_dim,'Movimento','Faturamento atual','Faturamento anterior','Δ Faturamento','Variação %','Margem %','Δ Margem p.p.','Impacto']],height=420,width='stretch')
    else: st.info('Não há movimentações no contexto selecionado.')

    st.markdown('### Drill-down da movimentação')
    if not movers.empty:
        entity_options=movers[watch_dim].dropna().astype(str).tolist(); entity=st.selectbox(f'Selecione {watch_dim.lower()}',entity_options,key='watch_entity')
        drill=monitor_scope[monitor_scope[watch_dim].astype(str)==entity].copy()
        child_dim='Cliente' if watch_dim in ('Vendedor','Produto') else 'Produto'
        child_options=['Todos']+sorted(drill[child_dim].dropna().astype(str).unique().tolist())
        child=st.selectbox(f'Detalhar por {child_dim.lower()}',child_options,key='watch_child')
        if child!='Todos': drill=drill[drill[child_dim].astype(str)==child]
        cur_drill=drill[(drill.Data>=pd.Timestamp(start_date))&(drill.Data<pd.Timestamp(end_date)+pd.Timedelta(days=1))]
        prev_drill=drill[(drill.Data>=watch['prev_start'])&(drill.Data<watch['prev_end']+pd.Timedelta(days=1))]
        dm,dp=metrics(cur_drill),metrics(prev_drill); ddelta=dm['revenue']-dp['revenue']; dvar=ddelta/dp['revenue'] if dp['revenue'] else 0
        dk=st.columns(5); dk[0].metric('Faturamento',brl(dm['revenue']),delta=f"{dvar:+.1%}".replace('.',',')); dk[1].metric('Margem',brl(dm['margin'])); dk[2].metric('Margem %',pct(dm['margin_pct']),delta=pp((dm['margin_pct']-dp['margin_pct'])*100)); dk[3].metric('Clientes',f"{dm['clients']:,}".replace(',','.')); dk[4].metric('Produtos',f"{dm['products']:,}".replace(',','.'))
        if not cur_drill.empty:
            daily=cur_drill.groupby(cur_drill.Data.dt.normalize()).agg(Faturamento=('Faturamento','sum'),Margem=('Margem','sum'),Clientes=('Cliente','nunique'),Produtos=('Produto','nunique')).reset_index(names='Data'); daily['Margem %']=daily.Margem/daily.Faturamento.replace(0,pd.NA)
            fig=go.Figure(); fig.add_bar(x=daily.Data,y=daily.Faturamento,name='Faturamento',marker_color='#2F8FD8'); fig.add_scatter(x=daily.Data,y=daily['Margem %']*100,name='Margem %',yaxis='y2',line=dict(color='#F2B84B',width=3)); fig.update_layout(title='Movimentação diária do recorte',yaxis=dict(title='Faturamento'),yaxis2=dict(overlaying='y',side='right',ticksuffix='%'),legend=dict(orientation='h')); show_chart(fig)
            with st.expander('Abrir transações e notas do recorte',expanded=False):
                detail_cols=[c for c in ['Data','NF','Vendedor','Cliente','Produto','Grupo Produto','Tipo Produto','UF','Município','Faturamento','Margem','Margem %','Peso','Preço Real Kg'] if c in cur_drill.columns]
                tx=cur_drill[detail_cols].sort_values(['Data','Faturamento'],ascending=[False,False]); show_table(tx,height=560,width='stretch',column_config={'Data':st.column_config.DateColumn(format='DD/MM/YYYY')})
                st.download_button('Baixar detalhe em CSV',tx.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),file_name=f"market_watch_{watch_dim.lower()}_{start_date}_{end_date}.csv",mime='text/csv')
        else: st.info('A seleção não possui movimentação no período atual; consulte o período anterior no quadro acima.')
with tabs[2]:
    m=metrics(f); summary_metrics=[("Faturamento",brl(m["revenue"])),("Margem",brl(m["margin"])),("Margem %",pct(m["margin_pct"])),("Peso",f"{m['weight']/1e6:.0f} mi kg"),("Clientes",f"{m['clients']:,}".replace(',','.')),("Produtos",f"{m['products']:,}".replace(',','.'))]
    for start in (0,3):
        cols=st.columns(3)
        for c,(lab,val) in zip(cols,summary_metrics[start:start+3]): c.metric(lab,val)
    mon=f.groupby("Mes",as_index=False).agg(Faturamento=("Faturamento","sum"),Margem=("Margem","sum")); show_chart(px.bar(mon,x="Mes",y="Faturamento",title="Faturamento mensal"))
    c1,c2=st.columns(2)
    with c1:
        t=group_metrics(f,"Cliente").nlargest(15,"faturamento"); show_chart(px.bar(t.sort_values("faturamento"),x="faturamento",y="Cliente",orientation="h",title="Top clientes"))
    with c2:
        t=group_metrics(f,"Produto").nlargest(15,"faturamento"); show_chart(px.bar(t.sort_values("faturamento"),x="faturamento",y="Produto",orientation="h",title="Top produtos"))
with tabs[3]:
    st.subheader('Diagnóstico interativo')
    st.caption('Compara o calendário selecionado com o período imediatamente anterior de mesma duração, respeitando os demais filtros.')
    c1,c2,c3=st.columns([1.2,1,1])
    insight_dim=c1.selectbox('Analisar por',['Cliente','Vendedor','Grupo Produto','Produto','UF','Município'],key='insight_dim')
    insight_metric=c2.selectbox('Métrica',['Faturamento','Margem','Peso'],key='insight_metric')
    insight_top=c3.slider('Principais drivers',5,25,12,key='insight_top')
    diag=compare_periods(monitor_scope,start_date,end_date,insight_dim,insight_top); cm=diag['current_metrics']; pm=diag['previous_metrics']
    rev_delta=cm['revenue']-pm['revenue']; rev_growth=rev_delta/pm['revenue'] if pm['revenue'] else 0; margin_pp=(cm['margin_pct']-pm['margin_pct'])*100
    k=st.columns(4); k[0].metric('Faturamento do período',brl(cm['revenue']),delta=f"{rev_growth:+.1%}".replace('.',',')); k[1].metric('Variação absoluta',brl(rev_delta)); k[2].metric('Margem %',pct(cm['margin_pct']),delta=pp(margin_pp)); k[3].metric('Concentração Top 5',pct(diag['concentration_top5']))
    metric_key={'Faturamento':'faturamento','Margem':'margem','Peso':'peso'}[insight_metric]; delta_key=f'delta_{metric_key}'
    ranked=diag['comparison'].reindex(diag['comparison'][delta_key].abs().sort_values(ascending=False).index).head(insight_top).copy(); ranked['Direção']=ranked[delta_key].map(lambda v:'Positivo' if v>=0 else 'Negativo')
    c1,c2=st.columns([1.35,1])
    with c1:
        fig=px.bar(ranked.sort_values(delta_key),x=delta_key,y=insight_dim,orientation='h',color='Direção',color_discrete_map={'Positivo':'#34B27B','Negativo':'#F05B63'},title=f'Drivers da variação de {insight_metric.lower()}',labels={delta_key:f'Δ {insight_metric}'})
        fig.add_vline(x=0,line_color='#D8E0EA',line_width=1); show_chart(fig)
    with c2:
        trend=pd.concat([diag['current'].assign(Período='Atual'),diag['previous'].assign(Período='Anterior')]); trend=trend.groupby(['Período',trend.Data.dt.to_period('D').astype(str)],as_index=False).agg(Faturamento=('Faturamento','sum'),Margem=('Margem','sum'),Peso=('Peso','sum'))
        show_chart(px.line(trend,x='Data',y=insight_metric,color='Período',markers=True,title=f'Evolução diária de {insight_metric.lower()}'))
    positives=diag['comparison'].nlargest(3,'delta_faturamento'); negatives=diag['comparison'].nsmallest(3,'delta_faturamento')
    pos_txt=', '.join(f"{r[insight_dim]} ({brl(r.delta_faturamento)})" for _,r in positives.iterrows()); neg_txt=', '.join(f"{r[insight_dim]} ({brl(r.delta_faturamento)})" for _,r in negatives.iterrows())
    st.markdown(f"**Leitura executiva:** o faturamento variou **{brl(rev_delta)} ({rev_growth:+.1%})**. Maiores contribuições: {pos_txt or '—'}. Maiores pressões: {neg_txt or '—'}.")
    with st.expander('Ver tabela detalhada dos drivers'):
        show_table(ranked[[insight_dim,'faturamento_atual','faturamento_anterior','delta_faturamento','var_faturamento','margem_pct_atual','delta_margem_pp']].rename(columns={'faturamento_atual':'Faturamento atual','faturamento_anterior':'Faturamento anterior','delta_faturamento':'Δ Faturamento','var_faturamento':'Variação %','margem_pct_atual':'Margem % atual','delta_margem_pp':'Δ Margem p.p.'}),width='stretch',height=450)
with tabs[4]:
    st.subheader('Performance da carteira do vendedor')
    st.caption('Visão integrada de resultado, mix, clientes, margem, tendência e evolução. A comparação usa o período anterior de mesma duração.')
    seller_options=sorted(monitor_scope['Vendedor'].dropna().astype(str).unique().tolist())
    if not seller_options:
        st.warning('Nenhum vendedor disponível com os filtros atuais.')
    else:
        current_sellers=f.groupby('Vendedor')['Faturamento'].sum().sort_values(ascending=False)
        default_seller=str(current_sellers.index[0]) if len(current_sellers) else seller_options[0]
        seller=st.selectbox('Selecione o vendedor',seller_options,index=seller_options.index(default_seller) if default_seller in seller_options else 0,key='portfolio_seller')
        seller_history=monitor_scope[monitor_scope['Vendedor'].astype(str)==seller]
        seller_period=f[f['Vendedor'].astype(str)==seller]
        portfolio_cmp=compare_periods(seller_history,start_date,end_date,'Cliente',20); sm=portfolio_cmp['current_metrics']; sp=portfolio_cmp['previous_metrics']
        rev_var=sm['revenue']/sp['revenue']-1 if sp['revenue'] else 0; margin_var=(sm['margin_pct']-sp['margin_pct'])*100; client_var=sm['clients']-sp['clients']; product_var=sm['products']-sp['products']
        k=st.columns(3); k[0].metric('Faturamento',brl(sm['revenue']),delta=f"{rev_var:+.1%}".replace('.',',')); k[1].metric('Margem',brl(sm['margin']),delta=pp(margin_var)); k[2].metric('Margem %',pct(sm['margin_pct']))
        k=st.columns(3); k[0].metric('Clientes ativos',f"{sm['clients']:,}".replace(',','.'),delta=f"{client_var:+d}"); k[1].metric('Produtos vendidos',f"{sm['products']:,}".replace(',','.'),delta=f"{product_var:+d}"); k[2].metric('Ticket médio por NF',brl(sm['ticket']))
        if seller_period.empty:
            st.warning('Este vendedor não possui faturamento no período selecionado. A tendência histórica permanece disponível abaixo.')
        trend=seller_history.copy(); trend=trend[trend['Data']>=pd.Timestamp(base_max)-pd.DateOffset(months=18)]
        trend=trend.groupby(trend['Data'].dt.to_period('M').astype(str)).agg(Faturamento=('Faturamento','sum'),Margem=('Margem','sum'),Clientes=('Cliente','nunique')).reset_index(names='Mês'); trend['Margem %']=trend['Margem']/trend['Faturamento'].replace(0,pd.NA); trend['Média móvel 3M']=trend['Faturamento'].rolling(3,min_periods=1).mean()
        fig=go.Figure(); fig.add_bar(x=trend['Mês'],y=trend['Faturamento'],name='Faturamento',marker_color='#2F8FD8'); fig.add_scatter(x=trend['Mês'],y=trend['Média móvel 3M'],name='Tendência 3M',line=dict(color='#F2B84B',width=3)); fig.add_scatter(x=trend['Mês'],y=trend['Margem %']*100,name='Margem %',yaxis='y2',line=dict(color='#34B27B',width=2)); fig.update_layout(title='Tendência e evolução da carteira — últimos 18 meses',yaxis2=dict(overlaying='y',side='right',ticksuffix='%')); show_chart(fig)
        c1,c2=st.columns(2)
        with c1:
            mix=group_metrics(seller_period,'Grupo Produto').sort_values('faturamento',ascending=False).head(15) if not seller_period.empty else pd.DataFrame()
            if not mix.empty:
                mix['share']=mix['faturamento']/mix['faturamento'].sum(); show_chart(px.bar(mix.sort_values('faturamento'),x='faturamento',y='Grupo Produto',orientation='h',color='margem_pct',color_continuous_scale='RdYlGn',title='Mix de produtos: receita e margem',hover_data={'share':':.1%','margem_pct':':.1%'}))
            else: st.info('Sem mix de produtos no período.')
        with c2:
            clients=group_metrics(seller_period,'Cliente').sort_values('faturamento',ascending=False) if not seller_period.empty else pd.DataFrame()
            if not clients.empty:
                clients['share']=clients['faturamento']/clients['faturamento'].sum(); show_chart(px.scatter(clients.head(40),x='faturamento',y='margem_pct',size='peso',color='share',hover_name='Cliente',color_continuous_scale='Turbo',title='Carteira de clientes: receita × margem',labels={'faturamento':'Faturamento','margem_pct':'Margem %','share':'Participação'}))
            else: st.info('Sem clientes ativos no período.')
        drivers=portfolio_cmp['comparison'].copy(); drivers=drivers.reindex(drivers['delta_faturamento'].abs().sort_values(ascending=False).index).head(15); drivers['Direção']=drivers['delta_faturamento'].map(lambda v:'Avanço' if v>=0 else 'Recuo')
        if not drivers.empty: show_chart(px.bar(drivers.sort_values('delta_faturamento'),x='delta_faturamento',y='Cliente',orientation='h',color='Direção',color_discrete_map={'Avanço':'#34B27B','Recuo':'#F05B63'},title='Evolução dos clientes versus período anterior',labels={'delta_faturamento':'Δ Faturamento'}))
        else: st.info('Sem movimentação de clientes no período atual e no período anterior comparável.')
        if not clients.empty:
            top5=clients.head(5)['faturamento'].sum()/clients['faturamento'].sum(); low_margin=clients[clients['margem_pct']<.10]['faturamento'].sum()/clients['faturamento'].sum(); new_clients=int(((portfolio_cmp['comparison']['faturamento_anterior']==0)&(portfolio_cmp['comparison']['faturamento_atual']>0)).sum()); lost_clients=int(((portfolio_cmp['comparison']['faturamento_anterior']>0)&(portfolio_cmp['comparison']['faturamento_atual']==0)).sum())
            st.markdown(f"**Leitura da carteira:** Top 5 clientes concentram **{pct(top5)}** da receita; **{pct(low_margin)}** do faturamento está em clientes com margem abaixo de 10%; houve **{new_clients} entradas** e **{lost_clients} saídas** versus o período anterior.")
            with st.expander('Detalhamento da carteira de clientes'):
                detail=portfolio_cmp['comparison'].sort_values('faturamento_atual',ascending=False).rename(columns={'faturamento_atual':'Faturamento atual','faturamento_anterior':'Faturamento anterior','delta_faturamento':'Δ Faturamento','var_faturamento':'Variação %','margem_pct_atual':'Margem % atual','delta_margem_pp':'Δ Margem p.p.'})
                show_table(detail[['Cliente','Faturamento atual','Faturamento anterior','Δ Faturamento','Variação %','Margem % atual','Δ Margem p.p.']],width='stretch',height=500)
with tabs[5]:
    st.subheader('Clientes 360')
    st.caption('Segmentação de valor, recência, frequência, rentabilidade e responsável comercial no contexto filtrado.')
    cc=client_classification(f); k=st.columns(5)
    for c,(lab,val) in zip(k,[("Clientes",len(cc)),("Curva A",(cc.abc=='A').sum()),("Curva B",(cc.abc=='B').sum()),("Curva C",(cc.abc=='C').sum()),("Inativos 90+d",(cc.dias_sem_compra>=90).sum())]): c.metric(lab,f"{val:,}".replace(',','.'))
    if not cc.empty:
        c1,c2=st.columns(2)
        with c1:
            status_view=cc.groupby('status',as_index=False).agg(Clientes=('Cliente','nunique'),Faturamento=('faturamento','sum')); show_chart(px.bar(status_view.sort_values('Faturamento'),x='Faturamento',y='status',orientation='h',text='Clientes',title='Valor da carteira por estágio',labels={'status':'Estágio'}))
        with c2:
            abc_view=cc.groupby('abc',as_index=False).agg(Faturamento=('faturamento','sum'),Margem=('margem','sum'),Clientes=('Cliente','nunique')); abc_view['Margem %']=abc_view['Margem']/abc_view['Faturamento'].replace(0,pd.NA); show_chart(px.bar(abc_view,x='abc',y='Faturamento',text='Clientes',color='Margem %',color_continuous_scale='Blues',title='Curva ABC: receita e qualidade',labels={'abc':'Curva'}))
        q1,q2,q3=st.columns(3); abc_filter=q1.multiselect('Curva ABC',['A','B','C'],key='client_abc'); status_filter=q2.multiselect('Estágio',sorted(cc.status.unique()),key='client_status'); owner_filter=q3.multiselect('Vendedor',sorted(cc.vendedor.astype(str).unique()),key='client_owner')
        detail=cc.copy()
        if abc_filter: detail=detail[detail.abc.isin(abc_filter)]
        if status_filter: detail=detail[detail.status.isin(status_filter)]
        if owner_filter: detail=detail[detail.vendedor.astype(str).isin(owner_filter)]
        show_table(detail[["abc","status","Cliente","UF","municipio","vendedor","faturamento","margem_pct","nfs","meses","ultima_compra","dias_sem_compra","ticket_nf"]],height=600,width='stretch',column_config={'ultima_compra':st.column_config.DateColumn(format='DD/MM/YYYY')})
    else: st.info('Sem clientes no período selecionado.')
with tabs[6]:
    g=group_metrics(f,"Grupo Produto").sort_values('faturamento',ascending=False); t=group_metrics(f,"Tipo Produto").sort_values('faturamento',ascending=False); e=group_metrics(f,"Espessura").sort_values('faturamento',ascending=False); c1,c2=st.columns(2)
    with c1: show_chart(px.bar(g.head(20),x='Grupo Produto',y='faturamento',title='Faturamento por grupo'))
    with c2: show_chart(px.bar(g.head(20),x='Grupo Produto',y='margem',title='Margem por grupo'))
    c1,c2=st.columns(2)
    with c1: show_chart(px.bar(t.head(20),x='Tipo Produto',y='faturamento',title='Tipo de produto'))
    with c2: show_chart(px.bar(e.head(20),x='Espessura',y='faturamento',title='Espessura'))
with tabs[7]:
    mapped=f[f.UF!='Não mapeado']; u=group_metrics(mapped,'UF').sort_values('faturamento',ascending=False); cities=group_metrics(mapped,'Município').sort_values('faturamento',ascending=False); c1,c2=st.columns(2)
    with c1: show_chart(px.bar(u,x='UF',y='faturamento',title='Faturamento por UF'))
    with c2: show_chart(px.bar(u,x='UF',y='margem',title='Margem por UF'))
    show_chart(px.bar(cities.head(30).sort_values('faturamento'),x='faturamento',y='Município',orientation='h',title='Top municípios'))
with tabs[8]:
    pv=price_analysis(f,'Vendedor',1000); pc=price_analysis(f,'Cliente',5000)
    if not pv.empty: pv['desvio_%']=pv.desvio_pct*100; show_chart(px.bar(pv.sort_values('desvio_%'),x='desvio_%',y='Vendedor',orientation='h',title='Desvio de preço por vendedor'))
    if not pc.empty: pc['desvio_%']=pc.desvio_pct*100; show_table(pc.sort_values('desvio_%'),height=450)
    neg=group_metrics(f,'Produto'); st.subheader('Produtos com margem negativa'); show_table(neg[neg.margem<0].sort_values('margem').head(100))
with tabs[9]:
    st.subheader('Forecast & Oportunidades')
    c1,c2,c3=st.columns(3); method=c1.selectbox('Método',['hybrid','seasonal','lastyear','runrate'],format_func=lambda x:{'hybrid':'Híbrido','seasonal':'Sazonalidade','lastyear':'Curva último ano','runrate':'Run-rate'}[x]); scenario=c2.selectbox('Cenário',['base','conservative','aggressive'],format_func=lambda x:{'base':'Base','conservative':'Conservador','aggressive':'Agressivo'}[x]); growth=c3.number_input('Meta crescimento vs ano anterior (%)',value=10.0,step=1.0); fc=forecast_year(monitor_scope,method,scenario); target=fc['prev_full']*(1+growth/100); k=st.columns(4); k[0].metric('Realizado YTD',brl(fc['actual_ytd'])); k[1].metric('Fechamento projetado',brl(fc['projected'])); k[2].metric('Meta anual',brl(target)); k[3].metric('Gap vs meta',brl(target-fc['projected'])); mdf=fc['months']; fig=go.Figure(); fig.add_bar(x=[names[x] for x in mdf.mes],y=mdf.actual,name='Realizado',marker_color='#2F8FD8'); fig.add_bar(x=[names[x] for x in mdf.mes],y=mdf.forecast,name='Realizado + projetado',marker_color='#A78BFA'); fig.update_layout(title='Curva anual: realizado e projeção',yaxis=dict(title='Faturamento')); show_chart(fig)
    st.markdown('### Oportunidades comerciais priorizadas')
    opp=build_opportunities(f)
    if opp.empty: st.info('Sem oportunidades calculáveis no contexto selecionado.')
    else:
        ok=st.columns(4); ok[0].metric('Oportunidades',f"{len(opp):,}".replace(',','.')); ok[1].metric('Score médio',f"{opp.score.mean():.0f}"); ok[2].metric('Reativações',f"{(opp.acao=='Reativação').sum():,}".replace(',','.')); ok[3].metric('Reposições',f"{(opp.acao=='Reposição').sum():,}".replace(',','.'))
        o1,o2,o3=st.columns(3); opp_action=o1.multiselect('Tipo de ação',sorted(opp.acao.unique()),key='opp_action'); opp_owner=o2.multiselect('Vendedor',sorted(opp.Vendedor.astype(str).unique()),key='opp_owner'); min_score=o3.slider('Score mínimo',0,100,60,key='opp_score')
        if opp_action: opp=opp[opp.acao.isin(opp_action)]
        if opp_owner: opp=opp[opp.Vendedor.astype(str).isin(opp_owner)]
        opp=opp[opp.score>=min_score]
        c1,c2=st.columns([1,1.35])
        with c1:
            summary=opp.groupby('acao',as_index=False).agg(Oportunidades=('Cliente','size'),Faturamento=('faturamento','sum')); show_chart(px.bar(summary,x='acao',y='Oportunidades',text='Oportunidades',title='Oportunidades por ação',labels={'acao':'Ação'})) if not summary.empty else st.info('Nenhuma oportunidade acima do score selecionado.')
        with c2:
            cols=['score','acao','Vendedor','Cliente','Produto','faturamento','margem_pct','nfs','meses','ultima','dias']; show_table(opp[cols].head(500),height=520,width='stretch',column_config={'ultima':st.column_config.DateColumn(format='DD/MM/YYYY')})
with tabs[10]:
    st.subheader('Assistente IA analítica')
    st.info('Análise local e segura. A assistente cruza o período selecionado com o histórico completo sem enviar a base para serviços externos.')
    st.caption(f'Contexto ativo: {start_date.strftime("%d/%m/%Y")} a {end_date.strftime("%d/%m/%Y")} • {len(f):,.0f} registros • filtros globais aplicados'.replace(',','.'))
    quick=[('Prioridades agora','Onde agir primeiro no Command Center?'),('Resumo executivo','Faça um resumo executivo'),('Explicar variação','Por que o faturamento variou?'),('Vendedores em risco','Mostre a performance dos vendedores em risco'),('Mapa de riscos','Mostre o mapa de riscos'),('Forecast','Qual a previsão de fechamento?')]
    q=None
    cols=st.columns(3)
    for i,(label,prompt) in enumerate(quick):
        if cols[i%3].button(label,key=f'quick_{i}',width='stretch'): q=prompt
    if 'chat' not in st.session_state: st.session_state.chat=[]
    for role,msg in st.session_state.chat:
        with st.chat_message(role): st.markdown(msg)
    typed=st.chat_input('Ex.: por que o faturamento caiu por vendedor?')
    if typed: q=typed
    if q: st.session_state.chat.append(('user',q)); st.session_state.chat.append(('assistant',answer(q,f,monitor_scope,start_date,end_date))); st.rerun()
with tabs[11]:
    st.subheader('Integrações'); st.markdown('**Atualização manual:** carregue uma nova base consolidada para validar sem substituir a base instalada.'); up=st.file_uploader('Base .csv ou .csv.gz',type=['csv','gz'])
    if up:
        try: tmp=pd.read_csv(up,low_memory=False,compression='infer'); st.success(f'Arquivo lido: {len(tmp):,} linhas'.replace(',','.')); show_table(tmp.head(20))
        except Exception as e: st.error(str(e))
    st.divider(); st.markdown('**TOTVS Analytics / GoodData**'); cfg=from_streamlit_secrets(st); st.json({'base_url':cfg.get('base_url'),'workspace_configurado':bool(cfg.get('workspace')),'dashboard_configurado':bool(cfg.get('dashboard')),'sessao_configurada':bool(cfg.get('cookie'))});
    if st.button('Testar conexão TOTVS'):
        if not all([cfg.get('workspace'),cfg.get('dashboard'),cfg.get('cookie')]): st.warning('Configure .streamlit/secrets.toml usando o arquivo de exemplo.')
        else:
            try: TotvsGoodDataConnector(**cfg).renew_token(); st.success('Conexão TOTVS/GoodData validada.')
            except Exception as e: st.error(f'Falha: {e}')
    st.caption('Relatórios prontos no conector: '+', '.join(f'{k}={v}' for k,v in REPORTS.items()))
with tabs[12]:
    p=Path(__file__).parent/'data'/'auditoria.txt'; st.subheader('Auditoria da base v06'); st.code(p.read_text(encoding='utf-8') if p.exists() else 'Auditoria não encontrada'); st.write('Linhas filtradas:',len(f)); st.write('Período:',f.Data.min(),'→',f.Data.max())
