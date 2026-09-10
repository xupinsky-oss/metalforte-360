# Estado do projeto

- Versão preparada: 2.10 Metas e Orçamento.
- Painel principal: preservado e acrescido de reconsulta sem cache e acesso à gestão.
- Workflow: gestão local de demandas, importação e exportação JSON.
- ETL Monitor: timeline, histórico, status, eventos sanitizados e runbook.
- Disparo manual: implementado no código via Edge Function autenticada e `workflow_dispatch`.
- Execução real: workflow seguro disponível; a nova fonte de metas exige uma execução em homologação e reconciliação com o dashboard oficial antes da promoção para produção.
- Metas: Rel.044 (KG por vendedor × grupo) e Rel.045 (total R$), em objeto privado separado.
- Cliente e produto: alocações gerenciais auditáveis pela participação no peso faturado dos 3 meses-calendário anteriores, sem duplicar a meta oficial.
- Segredos: nenhum valor novo incluído; `web/config.js` preservado.
- Origem desta reconstrução: pacote-base anexado, pois o ZIP v2.3 citado no histórico não estava disponível no host.
