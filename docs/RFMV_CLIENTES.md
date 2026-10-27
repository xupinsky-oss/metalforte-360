# Matriz RFMV de clientes

## Objetivo

Permitir que a equipe comercial identifique rapidamente os clientes mais consolidados, os clientes com potencial de desenvolvimento e aqueles que precisam de recuperação.

## Componentes

- **R — Relacionamento:** cada ano-calendário com pelo menos 6 pedidos distintos é considerado elegível. Como a base disponível começa em 2024, a quantidade de anos elegíveis é normalizada entre 1 e 5 pela janela disponível até a data final.
- **F — Frequência:** pedidos distintos nos últimos 12 meses.
- **M — Faturamento:** faturamento positivo acumulado nos últimos 12 meses.
- **V — Volume:** KG positivos faturados nos últimos 12 meses.

F, M e V são transformados em notas de 1 a 5 pela posição relativa do cliente na carteira filtrada. Empates recebem a mesma posição média. A Nota RFMV é a soma das quatro notas e pode chegar a 20 pontos.

## Classes

| Classe | Score médio |
| --- | ---: |
| A | de 16 a 20 |
| B | de 11 a 15 |
| C | de 6 a 10 |
| D | de 0 a 5 |

## Uso no painel

- Ao selecionar um cliente, o painel mostra a classe, a nota total e as quatro notas.
- Na visão geral, o painel apresenta a distribuição da carteira por classe.
- A tabela **Carteira e movimentação** inclui a classe, o código e as notas RFMV.
- A exportação da carteira preserva os campos RFMV para análises externas.

## Observações

- A classificação respeita os filtros globais aplicados à carteira.
- O cálculo usa somente vendas positivas até a data final selecionada.
- RFMV é uma priorização relativa e não substitui análise de crédito, margem, potencial ou estratégia do vendedor.
