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

## Resumo ou painel indisponível

Verifique a publicação no bucket privado, a função `command-center` e a sessão do usuário. Não transforme o objeto em público.

## Revogação de emergência

Revogue ou rotacione `GITHUB_DISPATCH_TOKEN`, remova o usuário da allowlist e desabilite a função `etl-control`. A carga agendada pode continuar independente do botão da central.
