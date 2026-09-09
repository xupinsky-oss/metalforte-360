# Changelog

## v2.8 — gestão de acessos

- renomeada e destacada a área administrativa como **Gestão de acessos**;
- mantidos cadastro de usuários, perfis, permissões e redefinição de senha;
- adicionada visualização das permissões efetivas na lista de usuários;
- incluídas orientações de compartilhamento seguro dentro do painel;
- preservada a autorização exclusivamente por `app_metadata` no servidor.

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
