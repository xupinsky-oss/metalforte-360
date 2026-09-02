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


## v06.1
- Corrigido filtro de Ano (`list` não usa `.tolist()`).
- Proteções para filtros sem dados.
- Forecast, insights e oportunidades toleram conjuntos vazios.
