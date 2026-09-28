import os,time,requests

FIXED_FILTERS=[2186,20811,2190,2188,2193,11127459,400287,32094813,32320838,11288138,36831947,3019,4491,4485,4489,30338385]
REPORTS={"faturamento":"32915720","margem":"22637729","clientes_pedidos":"42959723","cliente_geo":"29087588","cliente_classificacao":"50868753","produto_classificacao":"20814355","preco_benchmark":"47742","regra_desconto":"854730"}
# Indicadores oficiais exibidos no painel "Metas - GH - Comercial". Eles são
# mantidos separados da base de notas fiscais porque representam meta e carteira
# de pedidos (e não faturamento realizado).
INDICATOR_REPORTS={
    "meta_valor":"11096333",
    "meta_peso":"11081459",
    "pedidos_nao_faturados_valor":"11232871",
    "pedidos_liberados_valor":"11228086",
    "pedidos_nao_faturados_peso":"11232869",
    "pedidos_liberados_peso":"11228084",
}
DETAIL_REPORTS={
    "meta_kg_vendedor_grupo":"11081881",
    "carteira_clientes":"51540859",
}
# Etapas oficiais do painel "Pedidos & Orçamentos". Os itens de operação
# foram publicados em kg; por isso não são convertidos artificialmente em R$.
FUNNEL_INDICATOR_REPORTS={
    # Painel "Pedidos & Orçamentos": fotografia comercial do período.
    # Os indicadores de quantidade são mantidos separados dos valores para
    # não inferir quantidades a partir do detalhamento por item.
    "orcamentos_implantados_valor":"49444",
    "orcamentos_implantados_quantidade":"48411",
    # Saldo principal do quadro "Pedidos & Orçamentos". O indicador 40646
    # permanece abaixo como saldo operacional complementar, pois tem outro
    # contexto de relatório e não deve ser comparado diretamente a este.
    "orcamentos_abertos_valor":"49462",
    "orcamentos_abertos_saldo_operacional_valor":"40646",
    "orcamentos_abertos_peso":"40659",
    "orcamentos_abertos_quantidade":"48413",
    "pedidos_rejeitados_valor":"49458",
    "pedidos_rejeitados_quantidade":"48423",
    # Mantido como compatibilidade com cargas anteriores. A interface usa
    # orcamentos_abertos_valor, que é o nome correto deste saldo.
    "pedidos_pendentes_valor":"49462",
    "pedidos_liberados_credito_valor":"49468",
    "pedidos_liberados_credito_quantidade":"49102",
    "aguardando_faturamento_quantidade":"40638",
    "pedidos_faturados_valor":"52444",
    "pedidos_faturados_quantidade":"49085",
    "conversao_faturado_percent":"49481",
    "conversao_pedidos_percent":"49477",
    "conversao_faturado_quantidade_percent":"49275",
    "conversao_pedidos_quantidade_percent":"49269",
    "aguardando_os_peso":"7674329",
    "aguardando_carga_cif_peso":"8084817",
    "aguardando_carga_fob_peso":"8055931",
    "aguardando_faturamento_peso":"41186",
    "aguardando_faturamento_cif_peso":"7674334",
    "aguardando_faturamento_fob_peso":"7674337",
}
# O kit é um detalhamento, não um cartão pronto no GoodData. A medida é
# calculada exclusivamente pela coluna de peso desse relatório.
FUNNEL_DETAIL_REPORTS={"aguardando_kit_peso": ("28736377", "peso")}
# Relatório analítico oficial de perdas. Ele preserva motivo, valor e peso,
# evitando tratar perdas como parte do saldo ainda em aberto do funil.
LOSS_DETAIL_REPORTS={"perdas_por_motivo": "21335179"}
# Relatórios analíticos do painel "Datas". O grão é pedido × item; eles
# preservam as datas reais do processo e não apenas a posição atual da fila.
FUNNEL_DATE_REPORTS={
    "fluxo_liberados_cif":"38943094",
    "fluxo_liberados_fob":"38943353",
    "op_sob_encomenda":"1236344",
    "orcamentos_abertos_detalhe":"3257",
}

class TotvsGoodDataConnector:
    def __init__(self,base_url,workspace,dashboard,cookie=None):
        self.base_url=base_url.rstrip('/'); self.workspace=workspace; self.dashboard=dashboard; self.session=requests.Session(); self.session.headers.update({"Accept":"application/json","X-GDC-Accept":"application/json"});
        if cookie: self.session.headers.update({"Cookie":cookie})
    def login(self,login,password):
        payload={"postUserLogin":{"login":login,"password":password,"remember":1,"verify_level":2}}
        r=self.session.post(f"{self.base_url}/gdc/account/login",json=payload,timeout=30); r.raise_for_status()
        for header in ("x-gdc-authsst","x-gdc-authtt"):
            if r.headers.get(header): self.session.headers[header]=r.headers[header]
        self.renew_token(); return True
    def renew_token(self):
        r=self.session.get(f"{self.base_url}/gdc/account/token",timeout=30); r.raise_for_status()
        for header in ("x-gdc-authsst","x-gdc-authtt"):
            if r.headers.get(header): self.session.headers[header]=r.headers[header]
        return True
    def raw_report(self,report_id,date_filter_obj=2142,offset_from=-55,offset_to=0,fixed_filters=None):
        fixed_filters=FIXED_FILTERS if fixed_filters is None else fixed_filters; obj=lambda x:f"/gdc/md/{self.workspace}/obj/{x}"
        filters=[*([{"uri":obj(date_filter_obj),"constraint":{"type":"floating","from":str(offset_from),"to":str(offset_to)}}] if date_filter_obj else []),*[{"uri":obj(x)} for x in fixed_filters]]
        payload={"report_req":{"report":obj(report_id),"context":{"filters":filters,"dashboard":obj(self.dashboard),"report":obj(report_id)}}}
        self.renew_token(); r=self.session.post(f"{self.base_url}/gdc/app/projects/{self.workspace}/execute/raw",json=payload,timeout=60); r.raise_for_status(); uri=r.json()["uri"]
        for _ in range(180):
            rr=self.session.get(self.base_url+uri if uri.startswith('/') else uri,timeout=60)
            if rr.status_code==202: time.sleep(1.2); continue
            rr.raise_for_status(); ct=rr.headers.get('content-type','')
            if 'application/json' in ct:
                j=rr.json(); uri=j.get('uri') or j.get('url') or j.get('location'); continue
            return rr.content
        raise TimeoutError('Timeout aguardando RAW TOTVS')

def from_streamlit_secrets(st):
    cfg={}
    try: cfg=dict(st.secrets.get('TOTVS',{}))
    except Exception: pass
    cfg.setdefault('base_url',os.getenv('TOTVS_BASE_URL','https://analytics.totvs.com.br')); cfg.setdefault('workspace',os.getenv('TOTVS_WORKSPACE','')); cfg.setdefault('dashboard',os.getenv('TOTVS_DASHBOARD','')); cfg.setdefault('cookie',os.getenv('TOTVS_COOKIE','')); return cfg
