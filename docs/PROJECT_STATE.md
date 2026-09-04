# Estado do projeto

- Versão preparada: 2.4 Operational Control Tower.
- Painel principal: preservado e acrescido de reconsulta sem cache e acesso à gestão.
- Workflow: gestão local de demandas, importação e exportação JSON.
- ETL Monitor: timeline, histórico, status, eventos sanitizados e runbook.
- Disparo manual: implementado no código via Edge Function autenticada e `workflow_dispatch`.
- Execução real: pendente de implantação e secrets externos.
- Segredos: nenhum valor novo incluído; `web/config.js` preservado.
- Origem desta reconstrução: pacote-base anexado, pois o ZIP v2.3 citado no histórico não estava disponível no host.
