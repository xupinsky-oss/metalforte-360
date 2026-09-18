const cfg = window.METALFORTE_CONFIG || {};
const brl = new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0});
const num = new Intl.NumberFormat("pt-BR",{maximumFractionDigits:0});
const percent = (v) => new Intl.NumberFormat("pt-BR",{style:"percent",minimumFractionDigits:2,maximumFractionDigits:2}).format(v || 0);
const money = (v) => brl.format(v || 0);
let supa, monthlyChart, funnelChart;
const el = (id) => document.getElementById(id);
function configMissing(){ return !cfg.SUPABASE_URL || !cfg.SUPABASE_ANON_KEY; }
function dateBR(value){ return new Intl.DateTimeFormat("pt-BR",{dateStyle:"medium"}).format(new Date(value+"T12:00:00")); }
function renderKpis(o){
  const cards=[["Faturamento no período",money(o.faturamento)],["Margem",percent(o.margem_pct)],["Peso faturado",num.format(o.peso)+" kg"],["Clientes compradores",num.format(o.clientes)],["Preço médio",money(o.preco_medio_kg)+"/kg"],["Produtos vendidos",num.format(o.produtos)]];
  el("kpis").innerHTML=cards.map(function(c){return '<article class="kpi"><span>'+c[0]+'</span><strong>'+c[1]+'</strong></article>';}).join("");
}
function renderCommercial(o){
  const section=el("metas-pedidos");
  if(!o || !(o.meta_valor || o.meta_peso || o.pedidos_liberados_valor || o.pedidos_nao_faturados_valor)){section.hidden=true;return;}
  const cards=[
    ["Meta de faturamento",money(o.meta_valor)],
    ["Atingimento da meta",o.atingimento_valor_pct==null?"—":percent(o.atingimento_valor_pct)],
    ["Meta de peso",num.format(o.meta_peso)+" kg"],
    ["Atingimento do peso",o.atingimento_peso_pct==null?"—":percent(o.atingimento_peso_pct)],
    ["Pedidos liberados",money(o.pedidos_liberados_valor)],
    ["Peso liberado",num.format(o.pedidos_liberados_peso)+" kg"],
    ["A faturar",money(o.pedidos_nao_faturados_valor)],
    ["Peso a faturar",num.format(o.pedidos_nao_faturados_peso)+" kg"]
  ];
  el("metas-pedidos-kpis").innerHTML=cards.map(function(c){return '<article class="kpi secondary"><span>'+c[0]+'</span><strong>'+c[1]+'</strong></article>';}).join("");
  section.hidden=false;
}
function renderFunnel(rows){
  const section=el("funil-acompanhamento");
  const visible=(rows||[]).filter(function(r){return r.valor!=null || r.peso!=null;});
  if(!visible.length){section.hidden=true;return;}
  if(funnelChart) funnelChart.destroy();
  const operational=visible.filter(function(r){return r.peso!=null && r.tipo!=="comercial" && !r.agregado;});
  funnelChart=new Chart(el("funnel-chart"),{type:"bar",data:{labels:operational.map(function(r){return r.etapa;}),datasets:[{label:"Peso na etapa (kg)",data:operational.map(function(r){return r.peso;}),backgroundColor:operational.map(function(r){return r.tipo==="resultado"?"#147a52":"#f26b21"})}]},options:{indexAxis:"y",responsive:true,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return num.format(ctx.raw)+" kg";}}}},scales:{x:{ticks:{callback:function(v){return num.format(v)+" kg";}},y:{ticks:{autoSkip:false}}}}}});
  el("funnel-table").innerHTML='<div class="table-wrap"><table><thead><tr><th>Etapa</th><th>Valor</th><th>Peso</th></tr></thead><tbody>'+visible.map(function(r){return "<tr><td>"+r.etapa+"</td><td>"+(r.valor==null?"—":money(r.valor))+"</td><td>"+(r.peso==null?"—":num.format(r.peso)+" kg")+"</td></tr>";}).join("")+"</tbody></table></div>";
  section.hidden=false;
}
function renderFlowDates(data){
  let section=el("rastreabilidade-datas");
  if(!section){
    section=document.createElement("section");section.id="rastreabilidade-datas";section.className="card";
    section.innerHTML='<h2>Rastreabilidade por datas</h2><p class="muted">Movimentações ocorridas no período e prazos medianos entre etapas.</p><div id="flow-date-kpis" class="kpis"></div><div id="flow-date-table"></div>';
    el("funil-acompanhamento").after(section);
  }
  const stages=(data&&data.etapas)||[];
  if(!stages.length){section.hidden=true;return;}
  const delays=(data.prazos||[]);
  el("flow-date-kpis").innerHTML=delays.map(function(r){return '<article class="kpi secondary"><span>'+r.etapa+'</span><strong>'+num.format(r.dias_medianos)+' dias</strong><small>'+num.format(r.amostra)+' registros</small></article>';}).join("");
  el("flow-date-table").innerHTML='<div class="table-wrap"><table><thead><tr><th>Movimentação</th><th>Registros</th><th>Peso</th><th>Valor</th></tr></thead><tbody>'+stages.map(function(r){return '<tr><td>'+r.etapa+'</td><td>'+num.format(r.registros)+'</td><td>'+num.format(r.peso)+' kg</td><td>'+money(r.valor)+'</td></tr>';}).join("")+'</tbody></table></div>';
  section.hidden=false;
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
function escapeHtml(value){return String(value==null?"—":value).replace(/[&<>'"]/g,function(char){return ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"})[char];});}
function unifiedValue(column,value){
  if(value==null||value==="") return "—";
  if(column==="Margem %") return percent(value);
  if(column.includes("(R$)")) return money(value);
  if(column.includes("(kg)")) return num.format(value)+" kg";
  if(column==="Clientes"||column==="Produtos"||column==="Registros"||column==="Prazo mediano (dias)") return num.format(value);
  return escapeHtml(value);
}
function renderUnified(rows){
  let section=el("consulta-unificada");
  if(!section){section=document.createElement("section");section.id="consulta-unificada";section.className="card";el("panels").after(section);}
  const sourceRows=rows||[];
  if(!sourceRows.length){section.hidden=true;return;}
  const sources=[...new Set(sourceRows.map(function(row){return row.Fonte;}))];
  section.innerHTML='<h2>Consulta unificada</h2><p class="muted">Recorte agregado das informações publicadas. Selecione a fonte e exporte o resultado; dados detalhados permanecem protegidos.</p><label>Fonte <select id="unified-source"><option value="">Todas</option>'+sources.map(function(source){return '<option value="'+escapeHtml(source)+'">'+escapeHtml(source)+'</option>';}).join("")+'</select></label> <button id="export-unified" type="button">Exportar recorte</button><div id="unified-table"></div>';
  const render=function(){
    const selected=el("unified-source").value;
    const view=selected?sourceRows.filter(function(row){return row.Fonte===selected;}):sourceRows;
    const columns=["Fonte","Recorte","Item","Faturamento (R$)","Peso (kg)","Margem (R$)","Margem %","Meta (R$)","Meta (kg)","Valor da carteira (R$)","Peso da carteira (kg)","Clientes","Produtos","Registros","Prazo mediano (dias)"];
    const available=columns.filter(function(column){return view.some(function(row){return row[column]!=null;});});
    el("unified-table").innerHTML='<div class="table-wrap"><table><thead><tr>'+available.map(function(column){return '<th>'+escapeHtml(column)+'</th>';}).join("")+'</tr></thead><tbody>'+view.map(function(row){return '<tr>'+available.map(function(column){return '<td>'+unifiedValue(column,row[column])+'</td>';}).join("")+'</tr>';}).join("")+'</tbody></table></div>';
    el("export-unified").onclick=function(){const csv=[available.join(";")].concat(view.map(function(row){return available.map(function(column){return '"'+String(row[column]??"").replaceAll('"','""')+'"';}).join(";")})).join("\n");const link=document.createElement("a");link.href=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));link.download="consulta_unificada_metalforte.csv";link.click();URL.revokeObjectURL(link.href);};
  };
  el("unified-source").onchange=render;render();section.hidden=false;
}
async function loadDashboard(){
  const session=(await supa.auth.getSession()).data.session;
  if(!session) return;
  const response=await fetch(cfg.SUPABASE_URL+"/functions/v1/"+(cfg.DASHBOARD_FUNCTION||"command-center"),{cache:"no-store",headers:{apikey:cfg.SUPABASE_ANON_KEY,Authorization:"Bearer "+session.access_token}});
  if(!response.ok) throw new Error(response.status===503 ? "O resumo ainda não está disponível. Execute uma carga automática para publicá-lo." : "Não foi possível carregar o painel.");
  const data=await response.json();
  el("periodo").textContent="Período: "+dateBR(data.periodo.inicio)+" a "+dateBR(data.periodo.fim);
  el("atualizado").textContent="Base atualizada em "+new Intl.DateTimeFormat("pt-BR",{dateStyle:"medium",timeStyle:"short"}).format(new Date(data.atualizado_em));
  renderKpis(data.overview);renderCommercial(data.metas_e_pedidos);renderFunnel(data.funil_acompanhamento);renderFlowDates(data.rastreabilidade_datas);renderMonthly(data.mensal);renderPanels(data.paineis);renderUnified(data.consulta_unificada);
  el("login").hidden=true;el("dashboard").hidden=false;el("logout").hidden=false;
}
async function start(){
  const error=el("login-error");
  if(configMissing()){error.textContent="Configure SUPABASE_URL e SUPABASE_ANON_KEY em web/config.js antes de publicar.";return;}
  supa=window.supabase.createClient(cfg.SUPABASE_URL,cfg.SUPABASE_ANON_KEY);
  try{await loadDashboard();}catch(e){error.textContent=e.message;}
  el("login-form").addEventListener("submit",async function(event){event.preventDefault();error.textContent="";const r=await supa.auth.signInWithPassword({email:el("email").value,password:el("password").value});if(r.error){error.textContent="E-mail ou senha inválidos.";return;}try{await loadDashboard();}catch(e){error.textContent=e.message;}});
  el("logout").addEventListener("click",async function(){await supa.auth.signOut();location.reload();});
  el("refresh-dashboard").addEventListener("click",async function(event){event.currentTarget.disabled=true;try{await loadDashboard();}catch(e){error.textContent=e.message;}finally{event.currentTarget.disabled=false;}});
}
start();
