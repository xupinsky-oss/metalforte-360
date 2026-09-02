import re
import pandas as pd
from .analytics import metrics, group_metrics, client_classification, price_analysis, forecast_year, build_opportunities, compare_periods, commercial_command_center

def money(x): return (f"R$ {x:,.0f}").replace(",",".")
def pct(x): return f"{x*100:.1f}%".replace(".",",")

def _top_lines(table,dim,value="faturamento",limit=10,extra=None):
    lines=[]
    for pos,(_,r) in enumerate(table.head(limit).iterrows(),1):
        suffix=f" | {extra(r)}" if extra else ""
        lines.append(f"{pos}. **{r[dim]}**: {money(r[value])}{suffix}")
    return "\n".join(lines)

def _dimension(q):
    for terms,dim in [(("vendedor","equipe"),"Vendedor"),(("produto","sku"),"Produto"),(("grupo","portfólio","portfolio"),"Grupo Produto"),(("uf","estado"),"UF"),(("município","municipio","cidade"),"Município"),(("cliente","carteira"),"Cliente")]:
        if any(t in q for t in terms): return dim
    return "Cliente"

def answer(question,df,history_df=None,start_date=None,end_date=None):
    q=question.lower().strip()
    history_df=history_df if history_df is not None else df
    start_date=pd.Timestamp(start_date if start_date is not None else df["Data"].min())
    end_date=pd.Timestamp(end_date if end_date is not None else df["Data"].max())
    dim=_dimension(q)
    if any(k in q for k in ["onde agir","prioridades","prioridade comercial","command center","plano de ação","plano de acao"]):
        cc=commercial_command_center(history_df,start_date,end_date); clients=cc["clients"].head(8); sellers=cc["sellers"].head(5)
        client_lines="\n".join([f"{i+1}. **{r.Cliente}** — {r['ação_recomendada']} com {money(r.valor_em_risco)} em risco; responsável: {r.Vendedor}." for i,(_,r) in enumerate(clients.iterrows())]) or "Nenhum cliente priorizado."
        seller_lines="\n".join([f"{i+1}. **{r.Vendedor}** — {r.status}; variação {pct(r.var_faturamento) if pd.notna(r.var_faturamento) else 'sem base comparável'}, margem {r.delta_margem_pp:+.1f} p.p." for i,(_,r) in enumerate(sellers.iterrows())]) or "Nenhum vendedor priorizado."
        return f"### Prioridades do Command Center\nFaturamento do período: **{money(cc['current']['revenue'])}**, variação de **{pct(cc['revenue_growth'])}** e margem em **{pct(cc['current']['margin_pct'])}** ({cc['margin_pp']:+.1f} p.p.).\n\n**Clientes para ação imediata**\n{client_lines}\n\n**Vendedores para gestão**\n{seller_lines}\n\n**Ritual sugerido:** validar causa com vendedor, registrar ação, prazo e valor recuperável; revisar a fila diariamente."
    if any(k in q for k in ["vendedores em risco","performance dos vendedores","ranking de vendedores"]):
        cc=commercial_command_center(history_df,start_date,end_date); t=cc["sellers"].head(12)
        return "### Performance dos vendedores\n"+"\n".join([f"{i+1}. **{r.Vendedor}**: {money(r.faturamento_atual)} | {pct(r.margem_pct_atual)} de margem | Δ receita {money(r.delta_faturamento)} | {r.status}." for i,(_,r) in enumerate(t.iterrows())])
    if any(k in q for k in ["resumo executivo","diagnóstico geral","diagnostico geral","como estamos"]):
        cmp=compare_periods(history_df,start_date,end_date,"Cliente",10); cm,pm=cmp["current_metrics"],cmp["previous_metrics"]
        rev=cm["revenue"]/pm["revenue"]-1 if pm["revenue"] else 0; mpp=(cm["margin_pct"]-pm["margin_pct"])*100
        best=cmp["comparison"].nlargest(1,"delta_faturamento"); worst=cmp["comparison"].nsmallest(1,"delta_faturamento")
        best_txt=f"**{best.iloc[0]['Cliente']}** ({money(best.iloc[0]['delta_faturamento'])})" if not best.empty else "—"
        worst_txt=f"**{worst.iloc[0]['Cliente']}** ({money(worst.iloc[0]['delta_faturamento'])})" if not worst.empty else "—"
        return f"### Resumo executivo\n- Faturamento: **{money(cm['revenue'])}** (**{pct(rev)}** vs período anterior).\n- Margem: **{money(cm['margin'])}**, equivalente a **{pct(cm['margin_pct'])}** (**{mpp:+.1f} p.p.**).\n- Maior contribuição positiva: {best_txt}.\n- Maior pressão: {worst_txt}.\n- Top 5 clientes concentram **{pct(cmp['concentration_top5'])}** da receita.\n\n**Leitura:** {'crescimento com melhora de qualidade' if rev>0 and mpp>=0 else 'crescimento com compressão de margem' if rev>0 else 'retração que exige recuperação dos principais detratores'}।"
    if any(k in q for k in ["por que","porque","driver","explica","causa","caiu","subiu","avançou","recuou"]):
        cmp=compare_periods(history_df,start_date,end_date,dim,10); cm,pm=cmp["current_metrics"],cmp["previous_metrics"]
        delta=cm["revenue"]-pm["revenue"]; growth=delta/pm["revenue"] if pm["revenue"] else 0
        pos=cmp["comparison"].nlargest(5,"delta_faturamento"); neg=cmp["comparison"].nsmallest(5,"delta_faturamento")
        return f"### Diagnóstico por {dim}\nO faturamento variou **{money(delta)} ({pct(growth)})** contra o período anterior de mesma duração.\n\n**Principais contribuições positivas**\n{_top_lines(pos,dim,'delta_faturamento',5)}\n\n**Principais pressões**\n{_top_lines(neg,dim,'delta_faturamento',5)}\n\n**Próxima análise:** valide volume, preço/kg e margem dos três maiores detratores antes de definir a ação comercial."
    if any(k in q for k in ["concentração","concentracao","pareto","dependência","dependencia"]):
        t=group_metrics(df,dim).sort_values("faturamento",ascending=False); total=t.faturamento.sum(); t["share"]=t.faturamento/total if total else 0
        top5=t.head(5).share.sum(); top10=t.head(10).share.sum(); return f"### Concentração por {dim}\n- Top 5: **{pct(top5)}** do faturamento.\n- Top 10: **{pct(top10)}**.\n- Base ativa: **{len(t):,}** itens na dimensão.\n\n{_top_lines(t,dim,'faturamento',10,lambda r:f'{pct(r.share)} do total')}"
    if any(k in q for k in ["risco","atenção","atencao","alerta"]):
        c=client_classification(history_df); risk=c[(c.abc=='A')&(c.dias_sem_compra>=90)]; neg=df[df.Margem<0]; below=df[(df['Benchmark Grupo']>0)&(df['Preço Real Kg']<df['Benchmark Grupo']*.95)]
        return f"### Mapa de riscos\n- **{len(risk)} clientes A** sem comprar há 90 dias ou mais.\n- **{money(abs(neg.Margem.sum()))}** em margem negativa no período.\n- **{money(below.Faturamento.sum())}** faturados mais de 5% abaixo do benchmark.\n\n**Prioridade:** reativar clientes A com maior histórico e revisar itens negativos recorrentes por vendedor."
    if any(k in q for k in ["previsão","previsao","fechamento","projeção","projecao"]):
        f=forecast_year(history_df,"hybrid","base"); g=f["projected"]/f["prev_full"]-1 if f["prev_full"] else 0; return f"### Projeção de fechamento\nFechamento projetado de {f['year']}: **{money(f['projected'])}**, equivalente a **{pct(g)}** versus {f['prev_year']}.\n\n- Realizado YTD: **{money(f['actual_ytd'])}**\n- Ano anterior: **{money(f['prev_full'])}**\n- Método: híbrido (sazonalidade, curva anterior e run-rate)."
    if "cliente" in q and any(k in q for k in ["top","maior","maiores"]):
        t=group_metrics(df,"Cliente").sort_values("faturamento",ascending=False).head(10); return _top_lines(t,"Cliente")
    if "produto" in q and any(k in q for k in ["top","maior","maiores"]):
        t=group_metrics(df,"Produto").sort_values("faturamento",ascending=False).head(10); return _top_lines(t,"Produto")
    if "uf" in q or "estado" in q:
        t=group_metrics(df,"UF").sort_values("faturamento",ascending=False).head(10); return "\n".join([f"{i+1}. **{r.UF}**: {money(r.faturamento)} | margem {pct(r.margem_pct)}" for i,r in t.iterrows()])
    if "municip" in q or "cidade" in q:
        t=group_metrics(df,"Município").sort_values("faturamento",ascending=False).head(10); return "\n".join([f"{i+1}. **{r['Município']}**: {money(r.faturamento)}" for i,r in t.iterrows()])
    if "margem negativa" in q:
        t=group_metrics(df,"Produto"); t=t[t["margem"]<0].sort_values("margem").head(15); return "\n".join([f"{i+1}. **{r.Produto}**: {money(r.margem)} | {pct(r.margem_pct)}" for i,r in t.iterrows()])
    m=re.search(r"(\d+)\s*dias",q)
    if ("sem comprar" in q or "inativ" in q) and m:
        days=int(m.group(1)); c=client_classification(df); c=c[c["dias_sem_compra"]>=days].sort_values("faturamento",ascending=False).head(15); return "\n".join([f"{i+1}. **{r.Cliente}**: {r.dias_sem_compra} dias | histórico {money(r.faturamento)}" for i,r in c.iterrows()])
    if "preço" in q or "preco" in q or "benchmark" in q:
        t=price_analysis(df,"Vendedor",1000)
        if t.empty: return "Não há volume suficiente para calcular o benchmark com os filtros atuais."
        t["abs"]=t["desvio_pct"].abs(); t=t.sort_values("abs",ascending=False).head(10); return "\n".join([f"{i+1}. **{r.Vendedor}**: {money(r.preco_real)}/kg vs {money(r.benchmark)}/kg | desvio {pct(r.desvio_pct)}" for i,r in t.iterrows()])
    if "o que vender" in q or "oportunidade" in q:
        o=build_opportunities(df).head(15); return "\n".join([f"{i+1}. **{r.Cliente}** → {r.Produto} | {r.acao} | score {r.score:.0f}" for i,r in o.iterrows()])
    mtr=metrics(df); return f"No contexto filtrado: faturamento **{money(mtr['revenue'])}**, margem **{money(mtr['margin'])} ({pct(mtr['margin_pct'])})**, {mtr['clients']:,} clientes e {mtr['products']:,} produtos."
