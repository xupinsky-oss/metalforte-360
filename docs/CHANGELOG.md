# Changelog

## v2.4 Operational Control Tower

- adicionada Control Tower autenticada;
- adicionada gestão fase a fase com persistência local e JSON;
- adicionados monitor, timeline, histórico e runbook do ETL;
- criado adapter público sem token administrativo;
- criada Edge Function `etl-control` com autorização no servidor;
- ampliado `workflow_dispatch` com entradas validadas e confirmação de ambiente;
- adicionada telemetria sanitizada no bucket privado;
- adicionado botão de reconsulta do painel com `cache: no-store`;
- preservadas rotinas oficiais de extração e geração do resumo.
