import pandas as pd
import numpy as np

def div(a,b): return a/b if b not in (0,None) and pd.notna(b) else 0

def metrics(df):
    rev=df["Faturamento"].sum(); mar=df["Margem"].sum(); kg=df["Peso"].sum(); nf=df["NF"].nunique()
    return {"revenue":rev,"margin":mar,"margin_pct":div(mar,rev),"weight":kg,"price_kg":div(rev,kg),"clients":df["Cliente"].nunique(),"products":df["Produto"].nunique(),"invoices":nf,"ticket":div(rev,nf)}

def group_metrics(df, dim):
    g=df.groupby(dim,dropna=False).agg(faturamento=("Faturamento","sum"),margem=("Margem","sum"),peso=("Peso","sum"),clientes=("Cliente","nunique"),produtos=("Produto","nunique"),nfs=("NF","nunique")).reset_index()
    g["margem_pct"]=np.where(g["faturamento"]!=0,g["margem"]/g["faturamento"],0)
    g["preco_kg"]=np.where(g["peso"]!=0,g["faturamento"]/g["peso"],0)
    return g

def client_classification(df, reference_date=None):
    reference_date=reference_date if reference_date is not None else df["Data"].max()
    g=df.groupby(["Cod Cliente","Cliente"],dropna=False).agg(faturamento=("Faturamento","sum"),margem=("Margem","sum"),peso=("Peso","sum"),nfs=("NF","nunique"),meses=("Mes","nunique"),ultima_compra=("Data","max"),primeira_compra=("Data","min"),UF=("UF","first"),municipio=("Município","first"),vendedor=("Vendedor","first")).reset_index().sort_values("faturamento",ascending=False)
    pos=g["faturamento"].clip(lower=0); total=pos.sum(); g["share_cum"]=pos.cumsum()/total if total else 1
    g["abc"]=np.select([g["share_cum"]<=.70,g["share_cum"]<=.90],["A","B"],default="C")
    g["dias_sem_compra"]=(reference_date-g["ultima_compra"]).dt.days
    g["status"]=np.select([g["dias_sem_compra"]<=60,g["dias_sem_compra"]<=90,g["dias_sem_compra"]<=180],["Ativo","Atenção","Inativo"],default="Perdido")
    g["margem_pct"]=np.where(g["faturamento"]!=0,g["margem"]/g["faturamento"],0); g["ticket_nf"]=np.where(g["nfs"]!=0,g["faturamento"]/g["nfs"],0)
    return g

def price_analysis(df, dim="Vendedor", min_weight=1000):
    valid=df[(df["Faturamento"]>0)&(df["Peso"]>0)&(df["Benchmark Grupo"]>0)].copy(); out=[]
    for key,r in valid.groupby(dim,dropna=False):
        rev=r["Faturamento"].sum(); kg=r["Peso"].sum()
        if kg<min_weight: continue
        actual=rev/kg; bench=(r["Benchmark Grupo"]*r["Peso"]).sum()/kg
        out.append({dim:key,"faturamento":rev,"peso":kg,"preco_real":actual,"benchmark":bench,"desvio_pct":actual/bench-1 if bench else 0,"margem_pct":r["Margem"].sum()/rev if rev else 0})
    return pd.DataFrame(out)

def comparable_ytd(df):
    if df.empty or df["Data"].dropna().empty:
        return None, None, df.iloc[0:0].copy(), df.iloc[0:0].copy()
    mx=df["Data"].max(); cy=int(mx.year); py=cy-1
    cur=df[(df["Data"].dt.year==cy)&(df["Data"]<=mx)]
    cut=mx-pd.DateOffset(years=1)
    prev=df[(df["Data"].dt.year==py)&(df["Data"]<=cut)]
    return cy,py,cur,prev

def quick_insights(df):
    cy,py,cur,prev=comparable_ytd(df)
    cm,pm=metrics(cur),metrics(prev)
    if cy is None:
        empty=pd.DataFrame(columns=["Cliente","faturamento_cur","faturamento_prev","diff"])
        return {"cy":"—","py":"—","current":cm,"previous":pm,"rev_growth":0,"margin_growth":0,"margin_pp":0,"client_growth":empty,"client_decline":empty}
    cg=group_metrics(cur,"Cliente").set_index("Cliente")[["faturamento"]] if not cur.empty else pd.DataFrame(columns=["faturamento"])
    pg=group_metrics(prev,"Cliente").set_index("Cliente")[["faturamento"]] if not prev.empty else pd.DataFrame(columns=["faturamento"])
    comp=cg.join(pg,how="outer",lsuffix="_cur",rsuffix="_prev").fillna(0)
    if "faturamento_cur" not in comp: comp["faturamento_cur"]=0
    if "faturamento_prev" not in comp: comp["faturamento_prev"]=0
    comp["diff"]=comp["faturamento_cur"]-comp["faturamento_prev"]
    return {"cy":cy,"py":py,"current":cm,"previous":pm,"rev_growth":div(cm["revenue"],pm["revenue"])-1 if pm["revenue"] else 0,"margin_growth":div(cm["margin"],pm["margin"])-1 if pm["margin"] else 0,"margin_pp":(cm["margin_pct"]-pm["margin_pct"])*100,"client_growth":comp.sort_values("diff",ascending=False).head(15).reset_index(),"client_decline":comp.sort_values("diff").head(15).reset_index()}

def compare_periods(history, start_date, end_date, dim="Cliente", top_n=15):
    """Compara o período selecionado com o período anterior de mesma duração."""
    start=pd.Timestamp(start_date); end=pd.Timestamp(end_date); days=(end-start).days+1
    prev_end=start-pd.Timedelta(days=1); prev_start=prev_end-pd.Timedelta(days=days-1)
    cur=history[(history["Data"]>=start)&(history["Data"]<end+pd.Timedelta(days=1))]
    prev=history[(history["Data"]>=prev_start)&(history["Data"]<prev_end+pd.Timedelta(days=1))]
    cm,pm=metrics(cur),metrics(prev)
    c=group_metrics(cur,dim).set_index(dim)[["faturamento","margem","peso"]] if not cur.empty else pd.DataFrame(columns=["faturamento","margem","peso"])
    p=group_metrics(prev,dim).set_index(dim)[["faturamento","margem","peso"]] if not prev.empty else pd.DataFrame(columns=["faturamento","margem","peso"])
    comp=c.join(p,how="outer",lsuffix="_atual",rsuffix="_anterior").fillna(0).reset_index()
    if dim not in comp.columns and "index" in comp.columns: comp=comp.rename(columns={"index":dim})
    for metric in ("faturamento","margem","peso"):
        comp[f"delta_{metric}"]=comp[f"{metric}_atual"]-comp[f"{metric}_anterior"]
        comp[f"var_{metric}"]=np.where(comp[f"{metric}_anterior"]!=0,comp[f"delta_{metric}"]/comp[f"{metric}_anterior"],np.nan)
    comp["margem_pct_atual"]=np.where(comp["faturamento_atual"]!=0,comp["margem_atual"]/comp["faturamento_atual"],0)
    comp["margem_pct_anterior"]=np.where(comp["faturamento_anterior"]!=0,comp["margem_anterior"]/comp["faturamento_anterior"],0)
    comp["delta_margem_pp"]=(comp["margem_pct_atual"]-comp["margem_pct_anterior"])*100
    comp["contribuicao_delta"]=np.where((cm["revenue"]-pm["revenue"])!=0,comp["delta_faturamento"]/(cm["revenue"]-pm["revenue"]),0)
    ranked=comp.reindex(comp["delta_faturamento"].abs().sort_values(ascending=False).index).head(top_n)
    total=cm["revenue"]; concentration=comp.nlargest(5,"faturamento_atual")["faturamento_atual"].sum()/total if total else 0
    return {"current":cur,"previous":prev,"current_metrics":cm,"previous_metrics":pm,"comparison":comp,"ranked":ranked,"start":start,"end":end,"prev_start":prev_start,"prev_end":prev_end,"concentration_top5":concentration}

def forecast_year(df, method="hybrid", scenario="base"):
    if df.empty or df["Data"].dropna().empty:
        return {"year":"—","prev_year":"—","max_date":pd.NaT,"actual_ytd":0,"prev_full":0,"projected":0,"runrate":0,"months":pd.DataFrame({"mes":range(1,13),"actual":[0]*12,"forecast":[0]*12,"status":["Sem dados"]*12})}
    mx=df["Data"].max(); cy=int(mx.year); py=cy-1; cm=int(mx.month); day=int(mx.day); days_month=(mx+pd.offsets.MonthEnd(0)).day
    cur=df[df["Data"].dt.year==cy]; prev=df[df["Data"].dt.year==py]; actual=cur["Faturamento"].sum(); prev_full=prev["Faturamento"].sum(); curr_month=cur.groupby(cur["Data"].dt.month)["Faturamento"].sum().to_dict(); hist_years=sorted([y for y in df["Data"].dt.year.unique() if y<cy])
    avg={}
    for m in range(1,13):
        vals=[df[(df["Data"].dt.year==y)&(df["Data"].dt.month==m)]["Faturamento"].sum() for y in hist_years]; vals=[v for v in vals if v]; avg[m]=np.mean(vals) if vals else 0
    complete=list(range(1,cm)); scale=sum(curr_month.get(m,0) for m in complete)/sum(avg.get(m,0) for m in complete) if sum(avg.get(m,0) for m in complete) else 1
    prev_m=prev.groupby(prev["Data"].dt.month)["Faturamento"].sum().to_dict(); prev_scale=sum(curr_month.get(m,0) for m in complete)/sum(prev_m.get(m,0) for m in complete) if sum(prev_m.get(m,0) for m in complete) else 1
    elapsed=(mx-pd.Timestamp(cy,1,1)).days+1; days_year=(pd.Timestamp(cy+1,1,1)-pd.Timestamp(cy,1,1)).days; runrate=actual/elapsed*days_year
    rows=[]
    for m in range(1,13):
        act=curr_month.get(m,0)
        if m<cm: fc=act; status="Realizado"
        elif m==cm: fc=act*days_month/day if day else act; status="Mês corrente"
        else:
            seasonal=avg[m]*scale; last=prev_m.get(m,0)*prev_scale
            fc= last if method=="lastyear" else runrate/12 if method=="runrate" else .55*seasonal+.25*last+.20*(runrate/12) if method=="hybrid" else seasonal; status="Projetado"
        rows.append({"mes":m,"actual":act,"forecast":fc,"status":status})
    projected=sum(r["forecast"] for r in rows); projected*=({"conservative":.95,"base":1,"aggressive":1.05}.get(scenario,1) if method!="runrate" else 1)
    return {"year":cy,"prev_year":py,"max_date":mx,"actual_ytd":actual,"prev_full":prev_full,"projected":projected,"runrate":runrate,"months":pd.DataFrame(rows)}

def build_opportunities(df):
    pos=df[df["Faturamento"]>0].copy()
    cols=["Vendedor","Cliente","Produto","faturamento","margem","nfs","meses","ultima","dias","margem_pct","score","acao"]
    if pos.empty or pos["Data"].dropna().empty:
        return pd.DataFrame(columns=cols)
    mx=pos["Data"].max(); s=pos.groupby(["Vendedor","Cliente","Produto"],dropna=False).agg(faturamento=("Faturamento","sum"),margem=("Margem","sum"),nfs=("NF","nunique"),meses=("Mes","nunique"),ultima=("Data","max")).reset_index(); s["dias"]=(mx-s["ultima"]).dt.days; s["margem_pct"]=np.where(s["faturamento"]!=0,s["margem"]/s["faturamento"],0)
    rv=s["faturamento"].rank(pct=True); rec=np.clip(1-s["dias"]/365,0,1); freq=np.clip(s["nfs"]/8,0,1); mq=np.clip((s["margem_pct"]+.05)/.30,0,1); s["score"]=100*(.30*rv+.30*rec+.25*freq+.15*mq); s["acao"]=np.where(s["dias"]>120,"Reativação","Reposição"); return s.sort_values("score",ascending=False)

def commercial_command_center(history, start_date, end_date):
    """Camada de decisão: resultado, drivers e filas de ação no mesmo grão temporal."""
    seller=compare_periods(history,start_date,end_date,"Vendedor",50)
    client=compare_periods(history,start_date,end_date,"Cliente",200)
    product=compare_periods(history,start_date,end_date,"Grupo Produto",50)
    cm,pm=client["current_metrics"],client["previous_metrics"]
    rev_delta=cm["revenue"]-pm["revenue"]
    rev_growth=div(rev_delta,pm["revenue"]) if pm["revenue"] else 0
    margin_pp=(cm["margin_pct"]-pm["margin_pct"])*100

    sellers=seller["comparison"].copy()
    if not sellers.empty:
        cur_clients=group_metrics(seller["current"],"Vendedor")[["Vendedor","clientes","produtos","nfs"]]
        sellers=sellers.merge(cur_clients,on="Vendedor",how="left").fillna({"clientes":0,"produtos":0,"nfs":0})
        sellers["valor_em_risco"]=sellers["delta_faturamento"].clip(upper=0).abs()
        sellers["status"]=np.select(
            [(sellers["delta_faturamento"]<0)&(sellers["delta_margem_pp"]<0),sellers["delta_faturamento"]<0,sellers["delta_margem_pp"]<0],
            ["Receita e margem em queda","Receita em queda","Margem em queda"],default="Evolução saudável")
        sellers=sellers.sort_values(["valor_em_risco","faturamento_atual"],ascending=[False,False])

    clients=client["comparison"].copy()
    if not clients.empty:
        latest=history.groupby("Cliente",dropna=False).agg(Vendedor=("Vendedor","last"),UF=("UF","last"),ultima_compra=("Data","max")).reset_index()
        clients=clients.merge(latest,on="Cliente",how="left")
        clients["dias_sem_compra"]=(pd.Timestamp(end_date)-clients["ultima_compra"]).dt.days.clip(lower=0)
        clients["valor_em_risco"]=clients["delta_faturamento"].clip(upper=0).abs()
        clients["ação_recomendada"]=np.select(
            [(clients["faturamento_atual"]==0)&(clients["faturamento_anterior"]>0),
             (clients["margem_pct_atual"]<0)&(clients["faturamento_atual"]>0),
             (clients["delta_faturamento"]<0)&(clients["delta_margem_pp"]<0),
             clients["delta_faturamento"]<0,
             (clients["faturamento_anterior"]==0)&(clients["faturamento_atual"]>0)],
            ["Reativar","Corrigir rentabilidade","Recuperar receita e margem","Recuperar volume","Desenvolver novo cliente"],
            default="Expandir mix")
        risk_rank=clients["valor_em_risco"].rank(pct=True).fillna(0)
        value_rank=clients["faturamento_atual"].rank(pct=True).fillna(0)
        inactivity=np.clip(clients["dias_sem_compra"].fillna(0)/120,0,1)
        margin_risk=np.clip((.12-clients["margem_pct_atual"])/.20,0,1)
        clients["prioridade"]=100*(.45*risk_rank+.25*value_rank+.15*inactivity+.15*margin_risk)
        clients=clients.sort_values(["prioridade","valor_em_risco"],ascending=False)

    products=product["comparison"].copy()
    if not products.empty:
        products["valor_em_risco"]=products["delta_faturamento"].clip(upper=0).abs()
        products["sinal"]=np.select(
            [(products["delta_faturamento"]>0)&(products["delta_margem_pp"]>=0),
             (products["delta_faturamento"]>0)&(products["delta_margem_pp"]<0),
             (products["delta_faturamento"]<0)&(products["delta_margem_pp"]>=0)],
            ["Crescimento rentável","Crescimento com pressão","Queda com margem protegida"],default="Queda com pressão")
        products=products.sort_values("faturamento_atual",ascending=False)

    trend=history[(history["Data"]>=client["prev_start"])&(history["Data"]<=pd.Timestamp(end_date))].copy()
    if not trend.empty:
        trend=trend.groupby(trend["Data"].dt.to_period("W").apply(lambda p:p.start_time)).agg(Faturamento=("Faturamento","sum"),Margem=("Margem","sum"),Clientes=("Cliente","nunique")).reset_index(names="Semana")
        trend["Margem %"]=np.where(trend["Faturamento"]!=0,trend["Margem"]/trend["Faturamento"],0)
        trend["Média móvel 4S"]=trend["Faturamento"].rolling(4,min_periods=1).mean()

    return {"current":cm,"previous":pm,"revenue_delta":rev_delta,"revenue_growth":rev_growth,
            "margin_pp":margin_pp,"sellers":sellers,"clients":clients,"products":products,
            "trend":trend,"period":client}

def market_watch(history, start_date, end_date, dim="Vendedor"):
    """Painel de movimentações por entidade, com fita diária comparável."""
    comparison=compare_periods(history,start_date,end_date,dim,200)
    movers=comparison["comparison"].copy()
    if not movers.empty:
        movers["movimento"]=np.select(
            [movers["delta_faturamento"]>0,movers["delta_faturamento"]<0],
            ["Alta","Queda"],default="Estável")
        movers["impacto"]=movers["delta_faturamento"].abs()
        movers=movers.sort_values("impacto",ascending=False)
    days=(pd.Timestamp(end_date)-pd.Timestamp(start_date)).days+1
    tapes=[]
    for label,data in (("Atual",comparison["current"]),("Anterior",comparison["previous"])):
        if data.empty: continue
        daily=data.groupby(data["Data"].dt.normalize()).agg(Faturamento=("Faturamento","sum"),Margem=("Margem","sum"),Clientes=("Cliente","nunique"),Produtos=("Produto","nunique")).reset_index(names="Data")
        anchor=comparison["start"] if label=="Atual" else comparison["prev_start"]
        daily["Dia do período"]=(daily["Data"]-anchor).dt.days+1
        daily["Período"]=label; daily["Acumulado"]=daily["Faturamento"].cumsum()
        daily["Margem %"]=np.where(daily["Faturamento"]!=0,daily["Margem"]/daily["Faturamento"],0)
        tapes.append(daily)
    tape=pd.concat(tapes,ignore_index=True) if tapes else pd.DataFrame(columns=["Data","Faturamento","Margem","Clientes","Produtos","Dia do período","Período","Acumulado","Margem %"])
    return {**comparison,"movers":movers,"tape":tape,"days":days}

def monitoring_snapshot(df):
    """Indicadores executivos e alertas acionáveis para a central de monitoramento."""
    empty={"as_of":pd.NaT,"year":"—","revenue":0,"margin":0,"margin_pct":0,"weight":0,
           "yoy_revenue":0,"yoy_margin_pp":0,"projected":0,"target":0,"target_attainment":0,
           "month_revenue":0,"month_pace":0,"inactive_a":0,"negative_margin":0,"below_benchmark":0,
           "unmapped_revenue_pct":0,"benchmark_coverage":0,"alerts":[],"monthly":pd.DataFrame(),
           "sellers":pd.DataFrame(),"at_risk":pd.DataFrame()}
    if df.empty or df["Data"].dropna().empty: return empty
    x=df.dropna(subset=["Data"]).copy(); mx=x["Data"].max(); cy=int(mx.year); py=cy-1
    cur=x[x["Data"].dt.year==cy]; cut=mx-pd.DateOffset(years=1); prev=x[(x["Data"].dt.year==py)&(x["Data"]<=cut)]
    cm,pm=metrics(cur),metrics(prev); fc=forecast_year(x,"hybrid","base"); target=fc["prev_full"]*1.10
    month=cur[cur["Data"].dt.month==mx.month]; days=int((mx+pd.offsets.MonthEnd(0)).day)
    pace=month["Faturamento"].sum()/max(mx.day,1)*days
    clients=client_classification(x,mx); inactive_a=int(((clients["abc"]=="A")&(clients["dias_sem_compra"]>=90)).sum())
    neg=x[x["Margem"]<0]; below=x[(x["Benchmark Grupo"]>0)&(x["Preço Real Kg"]<x["Benchmark Grupo"]*.95)]
    total_rev=x["Faturamento"].sum(); unmapped=x[x["UF"]=="Não mapeado"]["Faturamento"].sum()/total_rev if total_rev else 0
    bench_cov=x.loc[x["Benchmark Grupo"].gt(0),"Faturamento"].sum()/total_rev if total_rev else 0
    monthly=cur.groupby(cur["Data"].dt.month).agg(faturamento=("Faturamento","sum"),margem=("Margem","sum")).reset_index(names="mes")
    monthly["margem_pct"]=np.where(monthly["faturamento"]!=0,monthly["margem"]/monthly["faturamento"],0)
    sellers=group_metrics(cur,"Vendedor").sort_values("faturamento",ascending=False).head(12)
    at_risk=clients[(clients["abc"]=="A")&(clients["dias_sem_compra"]>=60)].sort_values(["dias_sem_compra","faturamento"],ascending=[False,False]).head(20)
    yoy=div(cm["revenue"],pm["revenue"])-1 if pm["revenue"] else 0; mpp=(cm["margin_pct"]-pm["margin_pct"])*100
    attainment=div(fc["projected"],target) if target else 0
    alerts=[]
    def add(level,title,value,detail,action): alerts.append({"nível":level,"alerta":title,"valor":value,"contexto":detail,"ação":action})
    if attainment<1: add("Crítico" if attainment<.9 else "Atenção","Gap anual projetado",target-fc["projected"],f"Realizado YTD R$ {cm['revenue']:,.0f} • projeção R$ {fc['projected']:,.0f} • meta R$ {target:,.0f} ({attainment:.1%})","Priorizar carteira e oportunidades de maior score")
    if mpp<0: add("Crítico" if mpp<=-2 else "Atenção","Compressão de margem",abs(mpp),f"Queda de {abs(mpp):.1f} p.p. versus período comparável","Revisar preço, mix e descontos")
    if inactive_a: add("Crítico" if inactive_a>=10 else "Atenção","Clientes A em risco",inactive_a,"Clientes curva A sem comprar há 90 dias ou mais","Abrir plano de reativação por vendedor")
    if neg["Margem"].sum()<0: add("Crítico","Margem negativa",abs(neg["Margem"].sum()),f"{neg['NF'].nunique():,} notas com itens negativos","Bloquear recorrência e revisar custo/preço")
    if unmapped>.01: add("Atenção","Geografia não mapeada",unmapped,f"{unmapped:.1%} do faturamento sem UF","Corrigir cadastro e enriquecimento")
    if bench_cov<.95: add("Informativo","Cobertura de benchmark",bench_cov,f"{bench_cov:.1%} do faturamento com referência","Expandir benchmark para grupos sem cobertura")
    priority={"Crítico":0,"Atenção":1,"Informativo":2}; alerts=sorted(alerts,key=lambda a:priority[a["nível"]])
    return {**empty,"as_of":mx,"year":cy,"revenue":cm["revenue"],"margin":cm["margin"],"margin_pct":cm["margin_pct"],"weight":cm["weight"],"yoy_revenue":yoy,"yoy_margin_pp":mpp,"projected":fc["projected"],"target":target,"target_attainment":attainment,"month_revenue":month["Faturamento"].sum(),"month_pace":pace,"inactive_a":inactive_a,"negative_margin":abs(neg["Margem"].sum()),"below_benchmark":below["Faturamento"].sum(),"unmapped_revenue_pct":unmapped,"benchmark_coverage":bench_cov,"alerts":alerts,"monthly":monthly,"sellers":sellers,"at_risk":at_risk}
