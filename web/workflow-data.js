window.METALFORTE_WORKFLOW_DEFAULTS = {
  version: 2,
  stages: ["Backlog", "Em desenho", "Em desenvolvimento", "Em validação", "Concluído"],
  tasks: [
    {id:"MF360-010",title:"ETL Monitor + atualização manual",owner:"Inteligência Comercial",priority:"Alta",environment:"HOMOLOGAÇÃO",status:"Em validação",acceptance:"Monitorar execução e disparar workflow sem expor segredos."},
    {id:"MF360-011",title:"Configurar autorização da Edge Function",owner:"Administrador",priority:"Alta",environment:"HOMOLOGAÇÃO",status:"Backlog",acceptance:"Definir allowlist e secrets no ambiente seguro."},
    {id:"MF360-012",title:"Homologar carga manual real",owner:"Operação",priority:"Alta",environment:"HOMOLOGAÇÃO",status:"Backlog",acceptance:"Executar carga, validar telemetria e reconciliar o resumo publicado."}
  ]
};
