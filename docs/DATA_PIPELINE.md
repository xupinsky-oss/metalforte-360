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

## Metas e orçamento

- `Rel.044 Comercial - Analítico Metas` (`11081881`) fornece a meta mensal de peso por vendedor e grupo de produto.
- `Rel.045 Comercial - Indicador R$ Meta Venda` (`11096333`) fornece o total oficial mensal em reais.
- O total em reais é distribuído no grão vendedor × grupo proporcionalmente à meta oficial de KG e reconciliado ao centavo antes da publicação.
- A competência corrente substitui somente o mesmo mês; competências já publicadas são preservadas no histórico privado `metalforte_metas.csv.gz`.
- Cliente e produto não são metas nativas desses relatórios. O painel os identifica como alocações gerenciais: Meta R$ e Meta KG usam a participação positiva no peso faturado dos 3 meses-calendário anteriores à competência, sempre dentro da célula oficial vendedor × grupo. Células sem peso histórico permanecem como saldo não alocado.
- `Fat. por clientes` (`51540859`) está catalogado como fonte complementar de carteira. A alocação operacional usa a base consolidada, que já contém vendedor, cliente, produto e grupo no mesmo grão e evita duplicidade de faturamento.

O relatório 044 usa `TOTVS_TARGET_KG_MULTIPLIER` (padrão `1000`, toneladas para KG). Os indicadores de peso da carteira usam `TOTVS_INDICATOR_WEIGHT_MULTIPLIER` (padrão `1`, pois já chegam em KG). A homologação deve reconciliar o total do mês ao dashboard oficial antes da promoção para produção.

## Garantias mantidas

- três tentativas de coleta antes de falhar;
- volume mínimo de linhas;
- cobertura mínima de datas;
- reconciliação do faturamento;
- reconciliação das metas oficiais de R$ e KG;
- cobertura mínima da classificação de clientes;
- bucket privado e autenticação na Edge Function;
- concorrência serializada no GitHub Actions.

As etapas 4 a 7 são reportadas após a conclusão do processo monolítico existente. A telemetria não afirma progresso interno que a rotina ainda não expõe.
