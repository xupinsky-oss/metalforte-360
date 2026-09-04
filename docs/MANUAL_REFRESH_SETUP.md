# Ativação segura da atualização manual

## Pré-requisitos

1. Repositório GitHub com `.github/workflows/atualizar-base.yml` na branch configurada.
2. Secrets atuais da carga preservados no GitHub Actions.
3. Edge Function `etl-control` implantada no mesmo projeto Supabase usado pela autenticação.
4. Bucket `metalforte-private` mantido privado.

## Secrets exclusivos da Edge Function

Configure no ambiente do Supabase, nunca em `web/config.js`:

- `GITHUB_DISPATCH_TOKEN`: token de escopo mínimo, limitado ao repositório e à permissão Actions: write.
- `GITHUB_REPOSITORY`: `xupinsky-oss/metalforte-360`.
- `GITHUB_WORKFLOW_FILE`: `atualizar-base.yml`.
- `GITHUB_WORKFLOW_REF`: `main`.
- `ETL_ALLOWED_EMAILS`: e-mails autorizados, separados por vírgula.
- `ETL_ALLOWED_ORIGINS`: origens web permitidas, separadas por vírgula.
- `SUPABASE_BUCKET`: `metalforte-private`.

Como alternativa à lista de e-mails, um administrador pode definir `app_metadata.etl_admin = true` no usuário. Nunca use `user_metadata` para autorização, pois o próprio usuário pode alterá-la.

## Sequência de ativação

1. Revisar o diff e confirmar que nenhum segredo foi incluído.
2. Implantar `etl-control` com verificação JWT.
3. Configurar secrets no Supabase e manter o token fora do repositório.
4. Publicar a pasta `web/`.
5. Autorizar um usuário de homologação.
6. Executar primeiro em `homologacao` e reconciliar a base/resumo.
7. Somente depois habilitar e testar `producao`.

## Proteções

- sessão Supabase obrigatória;
- allowlist ou papel administrativo em `app_metadata`;
- ambiente e escopo validados no servidor;
- confirmação adicional no workflow;
- grupo de concorrência impede cargas simultâneas;
- logs expostos na UI são sanitizados.
