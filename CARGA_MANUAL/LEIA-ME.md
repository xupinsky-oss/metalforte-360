# Pasta de carga manual

Coloque aqui os arquivos exportados do GoodData. O painel `Abrir_Carga_Manual.bat` também permite selecionar os arquivos e grava cada um com o nome correto.

## Arquivos obrigatórios

- `faturamento.csv`
- `margem.csv`
- `clientes_pedidos.csv`
- `cliente_geo.csv`
- `cliente_classificacao.csv`
- `produto_classificacao.csv`
- `preco_benchmark.csv`

## Arquivos complementares

- `fluxo_liberados_cif.csv`
- `fluxo_liberados_fob.csv`
- `op_sob_encomenda.csv`
- `orcamentos_abertos_detalhe.csv`
- `perdas_por_motivo.csv`

Os complementares atualizam o funil e as perdas. Os sete arquivos obrigatórios atualizam a base comercial principal.

Use CSV ou o ZIP exportado pelo GoodData. Não altere os nomes definidos acima.

Para publicar a carga no painel online, mantenha o arquivo `.env` configurado
na pasta principal do projeto. Use `.env.example` como modelo e não compartilhe
esse arquivo, pois ele contém a chave de publicação.
