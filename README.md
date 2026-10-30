# METALFORTE 360 v2.27

## Pedidos liberados × faturados — v2.27.3

O Command Center compara a carteira de pedidos cuja **Data Liberação** está no período com as notas faturadas desses mesmos pedidos até a data final selecionada. A pendência é calculada como liberado menos faturado, em R$ e kg, conciliada pelo número do pedido e detalhada por vendedor, cliente e pedido. Pedidos sem nota conciliada permanecem como pendentes; saldos negativos são sinalizados para revisão.

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
