# Command Center HTML

Esta versão não usa GPT durante a operação. O navegador recebe apenas um resumo agregado e privado da carga automática.

1. Implante no Supabase a Edge Function `command-center` desta pasta.
2. Em **Authentication > Users**, crie ou convide quem poderá ver o painel.
3. Em `web/config.js`, informe a URL do projeto e a chave **anon/publishable**. Nunca use `service_role` no HTML.
4. Publique a pasta `web` no GitHub Pages ou Cloudflare Pages.
5. Execute uma vez o workflow **Atualizar base comercial**. Cada carga também publica automaticamente o resumo.

As chaves administrativas e a base detalhada permanecem no Supabase privado.

## Workflow & ETL Control Tower

Abra `workflow.html` para gerir demandas e acompanhar o ETL. O disparo real usa a Edge Function autenticada `etl-control`; siga `docs/MANUAL_REFRESH_SETUP.md` antes de ativá-lo. Nenhum token do GitHub deve ser adicionado ao navegador.
