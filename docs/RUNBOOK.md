# Runbook operacional

## A carga não inicia

1. Confirme que o usuário está autenticado e autorizado.
2. Confirme nomes dos secrets sem exibir seus valores.
3. Verifique se o token tem apenas acesso ao repositório correto e Actions: write.
4. Confirme branch e nome do workflow.

## Falha de autenticação TOTVS/GoodData

Revise a credencial apenas no ambiente secreto. Não cole cookies, senha ou sessão em issue, chat, log ou arquivo do projeto. Depois de corrigir, faça nova carga em homologação.

## Timeout ou indisponibilidade da fonte

O workflow tenta até três vezes. Se todas falharem, preserve a última base válida, aguarde a recuperação da fonte e reexecute.

## Validação bloqueou a carga

Não reduza limites apenas para fazer a carga passar. Investigue linhas, datas, faturamento e cobertura de classificação. A base anterior deve permanecer válida.

## Meta oficial não aparece ou não reconcilia

1. Execute primeiro em homologação.
2. Confirme a competência e compare `meta_kg` e `meta_valor` do status sanitizado com os cartões oficiais do dashboard TOTVS.
3. Confirme se o relatório 044 está em toneladas; o multiplicador padrão para KG é `1000`.
4. Se o relatório 045 retornar mais de uma linha, valide os filtros do dashboard antes de promover.
5. Não altere o multiplicador ou distribua saldos manualmente apenas para forçar a conciliação.

Relatórios de cartão do GoodData podem ter uma única coluna. O ETL aceita esse formato somente na etapa de indicadores; as fontes transacionais continuam exigindo múltiplas colunas para impedir que mensagens de erro sejam interpretadas como dados.

As metas são consultadas competência a competência, por padrão de 12 meses anteriores a 12 meses futuros. Competências anteriores já presentes no histórico privado não são consultadas de novo a cada hora; o mês atual e os futuros continuam sendo renovados, e competências históricas ausentes são completadas. Competências sem orçamento positivo são registradas como indisponíveis e não são inventadas. Os limites podem ser ajustados por `TOTVS_TARGET_OFFSET_FROM` e `TOTVS_TARGET_OFFSET_TO`, entre -24 e 24 meses. Se metas ou estoque ficarem temporariamente indisponíveis, a carga principal de vendas segue e a última fotografia auxiliar válida é mantida.

O relatório detalhado 044 entrega a meta em toneladas e usa `TOTVS_TARGET_KG_MULTIPLIER=1000`. Os cartões de meta e carteira já chegam em kg e usam `TOTVS_INDICATOR_WEIGHT_MULTIPLIER=1`. Não iguale os multiplicadores: isso infla as pendências em mil vezes.

## Resumo ou painel indisponível

Verifique a publicação no bucket privado, a função `command-center` e a sessão do usuário. Não transforme o objeto em público.

## Revogação de emergência

Revogue ou rotacione `GITHUB_DISPATCH_TOKEN`, remova o usuário da allowlist e desabilite a função `etl-control`. A carga agendada pode continuar independente do botão da central.

### Carga agendada de hora em hora

O workflow `.github/workflows/atualizar-base.yml` cria duas oportunidades por hora, nos minutos 17 e 47 UTC. Antes da coleta, consulta a última execução bem-sucedida e ignora a janela se uma carga terminou há menos de 55 minutos. Assim, uma janela perdida ou uma falha pode ser recuperada na seguinte sem repetir cargas que já deram certo.

O GitHub Actions continua sendo um agendador de melhor esforço e pode atrasar ou descartar eventos. Em **Actions → Atualizar base comercial**, confirme o evento `schedule`, o início e o resultado. Se o intervalo entre execuções bem-sucedidas superar uma hora, o atraso é do agendador externo; se houver falha da coleta, consulte o nome sanitizado do indicador ou relatório no log. Metas incompletas preservam o histórico publicado e não bloqueiam a atualização das vendas; indicadores complementares vazios também não bloqueiam a carga principal.
