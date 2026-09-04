(function(){
  const KEY="metalforte360.workflow.v2";
  const defaults=window.METALFORTE_WORKFLOW_DEFAULTS;
  let state;
  const el=(id)=>document.getElementById(id);
  const escapeHtml=(value)=>String(value||"").replace(/[&<>"']/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function load(){try{const saved=JSON.parse(localStorage.getItem(KEY));if(saved&&Array.isArray(saved.tasks))return saved;}catch(_e){}return JSON.parse(JSON.stringify(defaults));}
  function save(){localStorage.setItem(KEY,JSON.stringify(state));render();document.dispatchEvent(new CustomEvent("workflow:updated",{detail:state}));}
  function nextStatus(current){const i=state.stages.indexOf(current);return state.stages[Math.min(i+1,state.stages.length-1)];}
  function render(){
    el("workflow-board").innerHTML=state.stages.map((stage)=>{
      const tasks=state.tasks.filter((task)=>task.status===stage);
      return '<section class="workflow-column"><h3>'+escapeHtml(stage)+' · '+tasks.length+'</h3>'+tasks.map((task)=>'<article class="task-card"><h4>'+escapeHtml(task.id)+' · '+escapeHtml(task.title)+'</h4><p>'+escapeHtml(task.acceptance||"Sem critério de aceite")+'</p><div class="task-tags"><span class="tag">'+escapeHtml(task.priority)+'</span><span class="tag">'+escapeHtml(task.environment)+'</span><span class="tag">'+escapeHtml(task.owner||"Sem responsável")+'</span></div><div class="card-actions">'+(stage!==state.stages[state.stages.length-1]?'<button data-advance="'+escapeHtml(task.id)+'">Avançar</button>':'')+'<button class="ghost" data-remove="'+escapeHtml(task.id)+'">Excluir</button></div></article>').join("")+'</section>';
    }).join("");
  }
  function exportJson(){const blob=new Blob([JSON.stringify(state,null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="metalforte360-workflow.json";a.click();URL.revokeObjectURL(a.href);}
  async function importJson(file){const data=JSON.parse(await file.text());if(!data||!Array.isArray(data.tasks)||!Array.isArray(data.stages))throw new Error("Arquivo de workflow inválido.");state=data;save();}
  function init(){
    state=load();render();
    el("new-task").onclick=()=>el("task-form").classList.add("visible");el("cancel-task").onclick=()=>el("task-form").classList.remove("visible");
    el("task-form").onsubmit=(event)=>{event.preventDefault();const serial=String(Math.max(12,...state.tasks.map((t)=>Number(String(t.id).replace(/\D/g,""))||0))+1).padStart(3,"0");state.tasks.push({id:"MF360-"+serial,title:el("task-title").value.trim(),owner:el("task-owner").value.trim(),priority:el("task-priority").value,environment:el("task-environment").value,status:state.stages[0],acceptance:el("task-acceptance").value.trim()});event.target.reset();event.target.classList.remove("visible");save();};
    el("workflow-board").onclick=(event)=>{const advance=event.target.dataset.advance,remove=event.target.dataset.remove;if(advance){const task=state.tasks.find((t)=>t.id===advance);task.status=nextStatus(task.status);save();}if(remove&&confirm("Excluir esta demanda do estado local?")){state.tasks=state.tasks.filter((t)=>t.id!==remove);save();}};
    el("export-workflow").onclick=exportJson;el("import-workflow").onchange=async(event)=>{try{await importJson(event.target.files[0]);}catch(e){alert(e.message);}event.target.value="";};
  }
  window.MetalforteWorkflow={init,getState:()=>state};
})();
