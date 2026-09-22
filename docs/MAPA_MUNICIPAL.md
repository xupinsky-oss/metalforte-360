# Mapa comercial por município

## Medidas

- **Clientes totais:** clientes distintos com histórico até a data final selecionada, respeitando os filtros laterais.
- **Clientes ativos:** clientes com faturamento líquido positivo no período selecionado.
- **Taxa de ativação:** clientes ativos divididos pelos clientes totais.
- **Potencial R$:** faturamento positivo do mesmo intervalo do ano anterior.
- **Potencial não atendido R$:** diferença positiva entre o faturamento do mesmo período do ano anterior e o faturamento atual.
- **Preço médio/kg:** faturamento dividido pelo peso faturado.
- **Margem %:** margem em reais dividida pelo faturamento.

Os pontos são posicionados por centroides municipais. A interface informa a cobertura de municípios reconhecidos e mantém os não reconhecidos na tabela de detalhamento.

## Referência geográfica

O arquivo `municipios_centroides.csv` contém centroides públicos de municípios brasileiros, obtidos do projeto [Municípios Brasileiros](https://github.com/kelvins/Municipios-Brasileiros), que consolida códigos do IBGE e coordenadas municipais. Ele não contém dados comerciais, clientes ou credenciais.
