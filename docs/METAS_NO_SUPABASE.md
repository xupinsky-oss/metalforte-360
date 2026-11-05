# Metas METALFORTE 360: arquivo Excel no Supabase

## Onde fica

- Serviço: Supabase Storage.
- Bucket privado: `metalforte-private`.
- Objeto de produção: `bases/metalforte_metas.xlsx`.
- Objeto de homologação: `bases/homologacao/metalforte_metas.xlsx`.

O aplicativo só lê o arquivo. Não há campo para enviar ou editar o DE/PARA dentro do painel. A administração do DE/PARA permanece nas tabelas internas do Supabase.

## Migração inicial

Na primeira execução do ETL depois da atualização:

1. Ele procura o XLSX de metas no bucket.
2. Se não existir, tenta converter o snapshot legado `bases/metalforte_metas.csv.gz`.
3. Se também não existir, faz uma única migração do histórico de metas no GoodData para criar o Excel.
4. Se nenhuma fonte antiga estiver disponível, não publica planilha vazia nem substitui metas por zero; registra o bloqueio no log para correção.

Quando o XLSX existe, as cargas do GitHub Actions não consultam metas no GoodData e não sobrescrevem o arquivo.

## Como alterar a meta

1. No Supabase, abra **Storage → metalforte-private → bases**.
2. Baixe `metalforte_metas.xlsx) para seu computador.
3. Edite a aba **Metas** no Excel. A aba **Instruções** descreve cada coluna.
4. Mantenha uma linha para cada combinação de competência e dimensões preenchidas.
5. Preencha **Meta R$**, **Meta KG**, ou ambos. Se não houver Meta R$, o painel estima apenas as linhas sem valor oficial usando **Meta KG × preço médio ponderado do mês anterior**.
6. Salve e faça upload do mesmo arquivo para o mesmo caminho, confirmando a substituição.
7. No METALFORTE 360, clique **Atualizar visualização**. O período e filtros da barra lateral continuam aplicáveis.

## Granularidade e regras

Colunas principais: `Competência`, vendedor, grupo de produto, `Meta R$` e `Meta KG`.

Dimensões opcionais aceitas: vendedor painel, grupo do vendedor, grupo econômico/cliente, segmento/canal, tipologia, filial, UF, município, cluster PIVOT, subgrupo, tipo, especificação, espessura e produto/código do produto.

- Uma dimensão preenchida torna a meta detalhada por essa dimensão. Uma dimensão vazia deixa a meta agregada nela.
- Para cada parte da meta, escolha um único grão: não misture a linha agregada com linhas detalhadas que somam a mesma meta, pois isso duplica o total.
- Use a mesma nomenclatura dos filtros do painel. O DE/PARA interno continua sendo aplicado pelo app para harmonizar cliente e vendedor.
- A comparação de faturamento e pedidos aplica um filtro somente quando aquela dimensão está preenchida na planilha. Assim, uma meta geral não é comparada por engano com uma seleção estreita de cliente ou produto.
- Faça cópia de segurança do XLSX antes de alterações estruturais ou substituições em lote.

