# Modelo SQL Comercial 360

O arquivo [`sql/comercial_360_unificado.sql`](../sql/comercial_360_unificado.sql) define a base única do Command Center e do METALFORTE 360.

## Regra central

Valores comerciais são calculados no grão **filial + pedido + item**. Uma mesma venda pode ter várias liberações, ordens de produção, cargas e notas; juntar essas tabelas diretamente repetiria faturamento, peso e margem. Por isso:

- `analytics.vw_comercial_item_360` é a visão para indicadores, tabelas, clientes, vendedores e produtos.
- `analytics.vw_fluxo_evento_360` é a visão para cronologia, lead time e rastreio do funil.
- O funil deve classificar cada pedido/item pela sua `etapa_atual`; nunca deve somar valores de todas as etapas.

## Campos operacionais cobertos

| Área | Informações |
| --- | --- |
| Comercial | orçamento, pedido, preço, desconto, valor, peso e margem |
| Cliente | segmento/classificação, cidade, UF, rota e cadastro |
| Produto | grupo, subgrupo, família e especificação |
| Vendas | vendedor, categoria e equipe |
| Processo | emissão do PV, desejo do cliente, liberação, OP, OS, carga, NF e saída |
| Exceções | bloqueio de crédito, estoque, perda/rejeição e motivo da perda |

## Próxima etapa de implantação

1. Criar as tabelas e visões no SQL Editor do Supabase.
2. Alterar o extrator para preencher as tabelas `stg` a partir do TOTVS/GoodData.
3. Rodar as quatro consultas de validação no final do script.
4. Só então trocar o app para ler `analytics.vw_comercial_item_360`.

O modelo não deve receber credenciais dentro do repositório nem do script SQL.
