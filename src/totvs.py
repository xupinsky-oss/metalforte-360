import os,time,requests

FIXED_FILTERS=[2186,20811,2190,2188,2193,11127459,400287,32094813,32320838,11288138,36831947,3019,4491,4485,4489,30338385]
REPORTS={"faturamento":"32915720","margem":"22637729","clientes_pedidos":"42959723","cliente_geo":"29087588","cliente_classificacao":"50868753","produto_classificacao":"20814355","preco_benchmark":"47742","regra_desconto":"854730"}

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
        fixed_filters=FIXED_FILTERS if fixed_filters is None else fixed_filters; obj=lambda x:f"/gdc/md/{self.workspace}/obj/{x}"; payload={"report_req":{"report":obj(report_id),"context":{"filters":[{"uri":obj(date_filter_obj),"constraint":{"type":"floating","from":str(offset_from),"to":str(offset_to)}},*[{"uri":obj(x)} for x in fixed_filters]],"dashboard":obj(self.dashboard),"report":obj(report_id)}}}
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
