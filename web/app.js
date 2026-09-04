const cfg = window.METALFORTE_CONFIG || {};
const brl = new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0});
const num = new Intl.NumberFormat("pt-BR",{maximumFractionDigits:0});
const percent = (v) => new Intl.NumberFormat("pt-BR",{style:"percent",minimumFractionDigits:2,maximumFractionDigits:2}).format(v || 0);
const money = (v) => brl.format(v || 0);
let supa, monthlyChart;
const el = (id) => document.getElementById(id);
function configMissing(){ return !cfg.SUPABASE_URL || !cfg.SUPABASE_ANON_KEY; }
function dateBR(value){ return new Intl.DateTimeFormat("pt-BR",{dateStyle:"medium"}).format(new Date(value+"T12:00:00")); }
function renderKpis(o){
  const cards=[["Faturamento no período",money(o.faturamento)],["Margem",percent(o.margem_pct)],["Peso faturado",num.format(o.peso)+" kg"],["Clientes compradores",num.format(o.clientes)],["Preço médio",money(o.preco_medio_kg)+"/kg"],["Produtos vendidos",num.format(o.produtos)]];
  el("kpis").innerHTML=cards.map(function(c){return '<article class="kpi"><span>'+c[0]+'</span><strong>'+c[1]+'</strong></article>';}).join("");
}
function renderMonthly(rows){
  if(monthlyChart) monthlyChart.destroy();
  monthlyChart=new Chart(el("monthly-chart"),{data:{labels:rows.map(function(r){return new Intl.DateTimeFormat("pt-BR",{month:"short",year:"2-digit"}).format(new Date(r.mes+"-01T12:00:00"));}),datasets:[
    {type:"bar",label:"Faturamento",data:rows.map(function(r){return r.faturamento;}),backgroundColor:"#f26b21",yAxisID:"revenue"},
    {type:"line",label:"Margem %",data:rows.map(function(r){return (r.margem_pct||0)*100;}),borderColor:"#147a52",backgroundColor:"#147a52",tension:.25,yAxisID:"margin"}
  ]},options:{responsive:true,plugins:{legend:{position:"bottom"},tooltip:{callbacks:{label:function(ctx){return ctx.dataset.yAxisID==="margin" ? ctx.dataset.label+": "+ctx.raw.toFixed(2)+"%" : ctx.dataset.label+": "+money(ctx.raw);}}}},scales:{revenue:{ticks:{callback:function(v){return money(v);}}},margin:{position:"right",grid:{drawOnChartArea:false},ticks:{callback:function(v){return v+"%";}}}}}});
}
function table(rows){
  return '<div class="table-wrap"><table><thead><tr><th>Nome</th><th>Faturamento</th><th>Margem</th><th>Participação</th><th>Clientes</th></tr></thead><tbody>'+rows.map(function(r){return "<tr><td title=\""+r.nome+"\">"+r.nome+"</td><td>"+money(r.faturamento)+"</td><td>"+percent(r.margem_pct)+"</td><td>"+percent(r.participacao_pct)+"</td><td>"+num.format(r.clientes)+"</td></tr>";}).join("")+"</tbody></table></div>";
}
function renderPanels(panels){
  const sets=[["Segmentos de clientes",panels.segmentos,"segments"],["Grupos de produtos",panels.produtos,"products"],["Vendedores",panels.vendedores,"sellers"],["Cidades",panels.cidades,"cities"]];
  el("panels").innerHTML=sets.map(function(s){return '<section class="card"><h2>'+s[0]+'</h2><div class="panel-grid"><div class="chart-wrap"><canvas id="'+s[2]+'"></canvas></div>'+table(s[1])+"</div></section>";}).join("");
  sets.forEach(function(s){new Chart(el(s[2]),{type:"bar",data:{labels:s[1].map(function(r){return r.nome;}),datasets:[{label:"Faturamento",data:s[1].map(function(r){return r.faturamento;}),backgroundColor:"#274c77"}]},options:{indexAxis:"y",responsive:true,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return money(ctx.raw);}}}},scales:{x:{ticks:{callback:function(v){return money(v);}}},y:{ticks:{autoSkip:false}}}}});});
}
async function loadDashboard(){
  const session=(await supa.auth.getSession()).data.session;
  if(!session) return;
  const response=await fetch(cfg.SUPABASE_URL+"/functions/v1/"+(cfg.DASHBOARD_FUNCTION||"command-center"),{headers:{apikey:cfg.SUPABASE_ANON_KEY,Authorization:"Bearer "+session.access_token}});
  if(!response.ok) throw new Error(response.status===503 ? "O resumo ainda não está disponível. Execute uma carga automática para publicá-lo." : "Não foi possível carregar o painel.");
  const data=await response.json();
  el("periodo").textContent="Período: "+dateBR(data.periodo.inicio)+" a "+dateBR(data.periodo.fim);
  el("atualizado").textContent="Base atualizada em "+new Intl.DateTimeFormat("pt-BR",{dateStyle:"medium",timeStyle:"short"}).format(new Date(data.atualizado_em));
  renderKpis(data.overview);renderMonthly(data.mensal);renderPanels(data.paineis);
  el("login").hidden=true;el("dashboard").hidden=false;el("logout").hidden=false;
}
async function start(){
  const error=el("login-error");
  if(configMissing()){error.textContent="Configure SUPABASE_URL e SUPABASE_ANON_KEY em web/config.js antes de publicar.";return;}
  supa=window.supabase.createClient(cfg.SUPABASE_URL,cfg.SUPABASE_ANON_KEY);
  try{await loadDashboard();}catch(e){error.textContent=e.message;}
  el("login-form").addEventListener("submit",async function(event){event.preventDefault();error.textContent="";const r=await supa.auth.signInWithPassword({email:el("email").value,password:el("password").value});if(r.error){error.textContent="E-mail ou senha inválidos.";return;}try{await loadDashboard();}catch(e){error.textContent=e.message;}});
  el("logout").addEventListener("click",async function(){await supa.auth.signOut();location.reload();});
}
start();
