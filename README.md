# Metalforte 360 Python v06.1

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

O app inclui os IDs validados de faturamento, margem, clientes/pedidos, geografia, classificação de produto, benchmark de preço e regra de desconto.

## Central de Monitoramento

A primeira tela reúne o comando executivo da operação:

- faturamento e margem YTD comparados ao período equivalente;
- projeção anual, meta de crescimento de 10% e ritmo do mês;
- alertas priorizados de meta, margem, clientes A inativos, geografia e cobertura de benchmark;
- pulso mensal de receita e margem, desempenho por vendedor e fila de ação comercial;
- indicadores de margem negativa e receita praticada abaixo do benchmark.

Todos os indicadores respeitam os filtros globais da barra lateral.

## Gestão de acessos

Administradores podem abrir **Gestão de acessos** para criar usuários, escolher perfis, liberar páginas individualmente, vincular vendedores às suas carteiras e redefinir senhas. O acesso é compartilhado pelo endereço `https://metalforte-360.streamlit.app/`; envie a senha inicial por um canal separado.

O primeiro administrador é definido por `METALFORTE_ADMIN_EMAILS` nos Secrets do Streamlit. As permissões ficam em `app_metadata`, alterável somente pelo servidor administrativo. Nenhuma chave secreta é enviada ao navegador.


## v06.1
- Corrigido filtro de Ano (`list` não usa `.tolist()`).
- Proteções para filtros sem dados.
- Forecast, insights e oportunidades toleram conjuntos vazios.
