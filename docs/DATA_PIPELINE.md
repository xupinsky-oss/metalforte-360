# Pipeline de dados

## Etapas monitoradas

1. Disparo solicitado.
2. Autorização e permissões.
3. Preparação do ambiente.
4. Coleta TOTVS / GoodData.
5. Validação da base.
6. Tratamento e normalização.
7. Publicação da base privada.
8. Geração de métricas e agregados.
9. Publicação do resumo.
10. Validação pós-carga.
11. Painel disponível.

`atualizar_gooddata.py` continua sendo a rotina oficial de extração, consolidação, controles mínimos e publicação da base. `gerar_dashboard_web.py` continua gerando somente o resumo agregado.

## Garantias mantidas

- três tentativas de coleta antes de falhar;
- volume mínimo de linhas;
- cobertura mínima de datas;
- reconciliação do faturamento;
- cobertura mínima da classificação de clientes;
- bucket privado e autenticação na Edge Function;
- concorrência serializada no GitHub Actions.

As etapas 4 a 7 são reportadas após a conclusão do processo monolítico existente. A telemetria não afirma progresso interno que a rotina ainda não expõe.
