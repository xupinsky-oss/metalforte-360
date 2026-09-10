# METALFORTE 360 v2.10

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
