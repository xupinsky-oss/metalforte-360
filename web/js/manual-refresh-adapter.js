(function(){
  const cfg=window.METALFORTE_CONFIG||{};
  const functionName=cfg.ETL_CONTROL_FUNCTION||"etl-control";
  function endpoint(query){return cfg.SUPABASE_URL+"/functions/v1/"+functionName+(query||"");}
  async function call(session,options,query){
    if(!cfg.SUPABASE_URL||!cfg.SUPABASE_ANON_KEY) throw new Error("Integração Supabase não configurada.");
    const response=await fetch(endpoint(query),Object.assign({cache:"no-store",headers:{apikey:cfg.SUPABASE_ANON_KEY,Authorization:"Bearer "+session.access_token,"Content-Type":"application/json"}},options||{}));
    let body={};try{body=await response.json();}catch(_e){}
    if(!response.ok) throw new Error(body.error||body.message||"A integração ETL não respondeu.");
    return body;
  }
  window.MetalforteEtlApi={
    latest:(session)=>call(session,{method:"GET"},"?view=latest"),
    history:(session)=>call(session,{method:"GET"},"?view=history"),
    trigger:(session,payload)=>call(session,{method:"POST",body:JSON.stringify(payload)}),
  };
})();
