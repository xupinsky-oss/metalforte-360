# Changelog

## v2.16 — carteira completa e exploração comercial

- O filtro de vendedor agora mantém todos os clientes da carteira no overview, inclusive quem não comprou no período atual nem no período de comparação.
- O mapa mensal de clientes permite exibir toda a carteira quando há um único vendedor no recorte.
- Os gráficos de performance diária permitem selecionar um dia e abrir as vendas faturadas, documentos, clientes e itens correspondentes.
- A página Produtos ganhou filtro próprio por cliente e uma batalha naval mensal por produto, com faturamento, positivação, preço médio/kg e margem %.
- O seletor global de clientes passou a respeitar filial, UF e vendedor já escolhidos.
- Adicionados testes de regressão para clientes inativos da carteira, matriz mensal e seleção de data.

## v2.15 — mapa regional e revisão de qualidade

- substituído o mapa de bolhas por regiões municipais preenchidas e identificadas pelo código IBGE;
- aumentados o contraste da escala, as bordas e a legibilidade de valores baixos;
- limitada a influência visual dos 5% maiores valores sem alterar números, detalhes ou exportações;
- padronizadas as legendas do mapa para R$, kg, contagem e percentuais;
- preservados como sem base os preços médios e as margens sem denominador válido;
- ampliada a validação automatizada para todas as páginas, inclusive gestão de acessos.

## v2.14 — Login compacto

- reduzida a logo da tela de login para 220 px, preservando o formulário e a adaptação a telas menores.

## v2.13 — Rateio de metas pelo peso recente

- Meta R$ e Meta KG por cliente e produto passam a seguir a participação no peso faturado;
- a janela usa os 3 meses-calendário completos anteriores a cada competência;
- o cálculo continua restrito à célula oficial vendedor × grupo e preserva os totais oficiais;
- valores sem peso histórico permanecem identificados como saldo não alocado.

## v2.9 — insights estáveis e experiência tablet

- corrigida a colisão entre os botões de exportação das quatro filas de Insights;
- restaurado o funcionamento das abas Sazonalidade e Recuperação de mix;
- formatado o campo **Potencial R$** como moeda brasileira, com duas casas decimais;
- adicionadas explicações de metodologia nos painéis e em cada fila de Insights;
- adicionada a marca METALFORTE na tela de login;
- otimizado o layout para tablets, com navegação adaptável, indicadores compactos e tabelas responsivas;
- preservadas autenticação, permissões e credenciais exclusivamente no servidor.

## v2.8 — gestão de acessos

- renomeada e destacada a área administrativa como **Gestão de acessos**;
- mantidos cadastro de usuários, perfis, permissões e redefinição de senha;
- adicionada visualização das permissões efetivas na lista de usuários;
- incluídas orientações de compartilhamento seguro dentro do painel;
- preservada a autorização exclusivamente por `app_metadata` no servidor.

## v2.4 Operational Control Tower

- adicionada Control Tower autenticada;
- adicionada gestão fase a fase com persistência local e JSON;
- adicionados monitor, timeline, histórico e runbook do ETL;
- criado adapter público sem token administrativo;
- criada Edge Function `etl-control` com autorização no servidor;
- ampliado `workflow_dispatch` com entradas validadas e confirmação de ambiente;
- adicionada telemetria sanitizada no bucket privado;
- adicionado botão de reconsulta do painel com `cache: no-store`;
- preservadas rotinas oficiais de extração e geração do resumo.
# v2.10 — Metas oficiais e alocação auditável

- integração dos relatórios oficiais 044 (KG) e 045 (R$);
- histórico mensal de metas em objeto privado separado;
- aba Metas com realizado, atingimento e saldo em R$ e KG;
- detalhamento oficial por vendedor e grupo e alocações identificadas por cliente e produto;
- permissão independente `view_targets` e controles de reconciliação.
- correção do parser para aceitar relatórios-indicador legítimos com uma única coluna, mantendo relatórios transacionais sujeitos à validação multicoluna.
- layout responsivo para tablet com cartões que se reorganizam sem quebrar valores.
- metas com seletor próprio de competências anteriores e futuras, detalhamento por vendedor, cliente e produto e pendências oficiais da carteira.
- unidade dos cartões de peso corrigida: os indicadores já chegam em kg; conversão por mil permanece apenas no relatório detalhado de metas.
