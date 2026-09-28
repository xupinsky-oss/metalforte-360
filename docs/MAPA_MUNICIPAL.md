# Mapa comercial por município

## Medidas

- **Clientes totais:** clientes distintos com histórico até a data final selecionada, respeitando os filtros laterais.
- **Clientes ativos:** clientes com faturamento líquido positivo no período selecionado.
- **Taxa de ativação:** clientes ativos divididos pelos clientes totais.
- **Potencial R$:** faturamento positivo do mesmo intervalo do ano anterior.
- **Potencial não atendido R$:** diferença positiva entre o faturamento do mesmo período do ano anterior e o faturamento atual.
- **Preço médio/kg:** faturamento dividido pelo peso faturado.
- **Margem %:** margem em reais dividida pelo faturamento.

Cada município reconhecido é exibido como uma região preenchida. A escala começa em azul médio, usa bordas brancas e limita a influência visual dos 5% maiores valores; assim, valores baixos permanecem legíveis sem alterar os números reais exibidos no hover, na tabela e na exportação. Municípios não reconhecidos continuam na tabela de detalhamento.

## Clusters de cidades PIVOT

A mesma página consolida os municípios pela matriz de cidades PIVOT. A visão apresenta a performance comercial por cluster e mantém taxas e médias recalculadas a partir de seus componentes, sem somar percentuais. A cobertura territorial corresponde aos municípios com ao menos um cliente na carteira divididos pelo total de municípios cadastrados no cluster.

O potencial apresentado no cluster segue a metodologia comercial do mapa municipal: faturamento positivo do mesmo período do ano anterior. Ele não representa um potencial de mercado externo ou estimado pela matriz de cidades.

## Referência geográfica

O arquivo `municipios_centroides.csv` contém códigos do IBGE e centroides públicos, obtidos do projeto [Municípios Brasileiros](https://github.com/kelvins/Municipios-Brasileiros). O arquivo compactado `municipios_brasil.geojson.gz` contém somente os limites municipais públicos do projeto [geodata-br](https://github.com/tbrugz/geodata-br). Nenhum deles contém dados comerciais, clientes ou credenciais.
