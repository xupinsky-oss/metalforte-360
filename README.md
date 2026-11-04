# METALFORTE 360 v2.27.25

## Desempenho e origem dos dados — v2.27.25

- O Streamlit consulta a versão publicada no status privado do Supabase e mantém a base de vendas em cache até a próxima publicação (limite de 2 horas). Ao detectar nova carga, usa uma nova chave de cache.
- Metas, estoque e Pedido × Realizado são lidos apenas quando o usuário abre a página correspondente; a trilha de eventos continua alimentando o resumo HTML e não é baixada sem necessidade pelo Streamlit.
- Competências de metas históricas já publicadas são preservadas; a extração horária renova a competência atual e as futuras e busca períodos passados somente quando ainda faltam no histórico.
- Falhas nas fontes auxiliares de metas ou estoque não cancelam uma carga válida de faturamento. A publicação auxiliar anterior é preservada e o status registra se o estoque foi atualizado nessa execução.
- Quando o Supabase está configurado, o app usa os objetos publicados como fonte de verdade. Arquivos locais servem apenas para desenvolvimento sem a conexão privada.
- A matriz de classificação de produto e a matriz de cidades PIVOT são referências versionadas derivadas das planilhas enviadas pela METALFORTE; não vêm do GoodData. O mapa de municípios/estados também é uma referência geográfica pública. As bases comerciais e as fotografias operacionais continuam vindo dos relatórios GoodData/TOTVS e são publicadas no bucket privado do Supabase.
- Cidades usam a grafia oficial da referência municipal do IBGE; vendedor é padronizado sem diferença de acentos, caixa ou espaços entre GoodData, metas, funil e pedidos.

## Painel comercial — v2.27.24

O Command Center resume o desempenho faturado no período e compara o resultado com o mês e o ano anteriores. A aba Metas compara o faturamento realizado com as metas cadastradas para vendedor e grupo de produto.

Os cartões e a seção de conciliação de pedidos liberados foram removidos do painel porque os números não estavam reconciliados. Os indicadores de faturamento realizado, KG, margem e preço médio permanecem disponíveis.

O Command Center mostra novos clientes (primeira compra observada no período) e clientes inativos (compraram antes do período, mas não faturaram nele), com comparação ao mês e ao ano anteriores. Clientes ativos e positivados são a mesma métrica: aparece uma única vez como **Clientes positivados**. A tendência mensal permite acompanhar positivados, novos e inativos.

A página **Fechamento e exportação** gera relatórios PDF e PowerPoint por competência, com fechamento mensal e YTD, comparações com o mês anterior e com o mesmo intervalo do ano anterior, e tabelas por vendedor, grupo de cliente e grupo de produto. É possível escolher a dimensão de grupo de cliente e o número de linhas; os filtros globais do painel são aplicados ao relatório.

## Estoque atual e giro — v2.27

- Fotografia oficial do estoque atual, preservada separadamente da base de faturamento.
- Curva ABC por peso vendido ou faturamento nos últimos 3, 6 ou 12 meses.
- Giro alto, médio, baixo ou sem giro e cobertura em dias: ruptura, baixo, adequado e alto.
- Alertas de excesso potencial, reserva e necessidade de reposição para 30 dias.

## Navegação e classificação — v2.26

- A aba **Funil** foi retirada da navegação e da gestão de permissões.
- O menu principal foi reorganizado em uma grade alinhada e responsiva para desktop, tablet e celular.
- A Nota RFMV passa a ser a soma de R, F, M e V, com até 20 pontos: D de 0 a 5; C de 6 a 10; B de 11 a 15; A de 16 a 20.

## Matriz RFMV — v2.25

A aba **Clientes** passa a exibir a classificação RFMV integrada à carteira e ao cliente isolado: relacionamento, frequência, faturamento e volume recebem notas de 1 a 5, uma nota total e classes de A a D. A exportação da carteira inclui as notas e o código RFMV.

## Inteligência comercial — v2.24

Esta versão acrescenta três visões operacionais inspiradas no material **Geração de Valor**:

- **Saúde da carteira**, dentro de Vendedores: cobertura de clientes nos últimos 90 dias, clientes novos, em risco e inativos, com fila de ação exportável.
- **Inteligência de preços**: matriz produto × segmento com preço médio ponderado, referências P25/mediana/P75, tendência recente, cobertura e sinal de confiabilidade.
- **Volume × margem**: dispersão por produto, cliente, vendedor ou segmento, separada nos quadrantes Proteger, Desenvolver, Reprecificar e Rever.

As novas páginas usam somente dados já carregados no painel, respeitam os filtros e as permissões existentes e não armazenam credenciais. A referência de margem da análise é configurável e não substitui a política comercial aprovada.

## Como executar

### Windows
Dê duplo clique em `INICIAR_METALFORTE.bat`.

### Terminal
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Integração TOTVS
Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e informe a sessão apenas no seu computador. Nunca publique o cookie.

O app inclui os IDs validados de faturamento, margem, clientes/pedidos, geografia, classificação de produto, benchmark de preço, meta de KG e orçamento em R$. As credenciais existem somente nos Secrets do ambiente.

## Central de Monitoramento

A primeira tela reúne o comando executivo da operação:

- faturamento e margem YTD comparados ao período equivalente;
- comparações com mês anterior, ano anterior e período anterior;
- alertas priorizados de meta, margem, clientes A inativos, geografia e cobertura de benchmark;
- pulso mensal de receita e margem, desempenho por vendedor e fila de ação comercial;
- indicadores de margem negativa e receita praticada abaixo do benchmark.

Todos os indicadores respeitam os filtros globais da barra lateral.

## Metas e orçamento

A aba **Metas** compara os resultados às metas oficiais mensais. Vendedor e grupo de produto preservam o grão oficial. Cliente e produto são alocações gerenciais identificadas, calculadas pela participação no peso faturado dos 3 meses-calendário anteriores à competência, com saldo sem histórico mantido como não alocado.

## Gestão de acessos

Administradores podem abrir **Gestão de acessos** para criar usuários, escolher perfis, liberar páginas individualmente, vincular vendedores às suas carteiras e redefinir senhas. O acesso é compartilhado pelo endereço `https://metalforte-360.streamlit.app/`; envie a senha inicial por um canal separado.

O primeiro administrador é definido por `METALFORTE_ADMIN_EMAILS` nos Secrets do Streamlit. As permissões ficam em `app_metadata`, alterável somente pelo servidor administrativo. Nenhuma chave secreta é enviada ao navegador.


## v2.10

- Meta oficial de KG e orçamento R$ em camada privada separada.
- Atingimento e saldo por vendedor, grupo, cliente e produto.
- Permissão específica para a nova aba e reconciliação automatizada.
