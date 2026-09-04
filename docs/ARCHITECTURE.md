# Arquitetura METALFORTE 360 v2.4

## Objetivo de negócio

Permitir que a equipe acompanhe o desempenho comercial, gerencie mudanças e solicite uma atualização de dados sem expor credenciais ou tornar a base bruta pública.

## Fluxo operacional

```text
Usuário autenticado
  -> Workflow & ETL Control Tower
  -> Edge Function etl-control
  -> GitHub Actions workflow_dispatch
  -> TOTVS Analytics / GoodData
  -> validação e consolidação
  -> Supabase Storage privado
  -> resumo agregado
  -> Edge Function command-center
  -> Command Center HTML
```

O navegador recebe somente o resumo comercial agregado e a telemetria sanitizada. O token de despacho, a chave administrativa do Supabase e a credencial TOTVS/GoodData permanecem nos ambientes secretos.

## Componentes

- `web/index.html`: painel comercial autenticado.
- `web/workflow.html`: gestão local de demandas e monitor ETL.
- `web/js/manual-refresh-adapter.js`: cliente autenticado da função `etl-control`.
- `supabase/functions/etl-control/index.ts`: autorização, despacho e consulta de histórico.
- `.github/workflows/atualizar-base.yml`: carga agendada e manual com confirmação.
- `scripts/etl_status.py`: telemetria operacional sanitizada.
- `gerar_dashboard_web.py`: resumo agregado do painel.

## Limites intencionais

- O workflow de gestão usa `localStorage` e exportação JSON; não é uma base colaborativa.
- A Control Tower não exibe logs brutos do GitHub nem respostas da TOTVS.
- A carga real só fica disponível após implantação e configuração administrativa.
