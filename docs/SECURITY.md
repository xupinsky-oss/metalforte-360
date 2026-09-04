# Segurança

## Dados e credenciais protegidos

- `web/config.js` contém apenas configuração pública do Supabase e deve manter somente a chave anon/publishable.
- `SUPABASE_SERVICE_ROLE_KEY` existe apenas no ambiente da Edge Function.
- `SUPABASE_SERVICE_KEY`, `TOTVS_LOGIN` e `TOTVS_PASSWORD` existem apenas nos GitHub Actions secrets.
- `GITHUB_DISPATCH_TOKEN` existe apenas nos secrets da Edge Function.
- a base comercial bruta continua no bucket privado.

## Proibições

Nunca registrar valores secretos, respostas integrais da fonte, cookies, sessão, dados brutos ou cabeçalhos de autorização. Nunca adicionar esses valores ao HTML, JavaScript público, arquivos `.env`, artefatos de Actions ou mensagens de erro.

## Auditoria

A telemetria registra solicitante, motivo, ambiente, estado e horário. Os logs completos continuam restritos ao GitHub Actions. A interface recebe somente mensagens operacionais controladas.
