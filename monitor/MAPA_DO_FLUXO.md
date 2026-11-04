# Mapa do fluxo de dados METALFORTE 360

Este documento explica, sem exigir conhecimento técnico, de onde vêm os números, qual programa os prepara, onde ficam guardados e como chegam ao painel.

## O caminho em uma imagem

```text
┌──────────────────────────┐
│ TOTVS Analytics /        │
│ GoodData                 │
│ Relatório 11078478       │
└────────────┬─────────────┘
             │ dados de vendas e dimensões comerciais
             ▼
┌──────────────────────────┐
│ GitHub Actions           │  Repositório: xupinsky-oss/metalforte-360
│ .github/workflows/       │  Branch: main
│ atualizar-base.yml       │  Tentativas às :17 e :47
└────────────┬─────────────┘
             │ inicia o computador temporário e instala Python 3.12
             ▼
┌──────────────────────────┐
│ Python                   │
│ atualizar_gooddata.py    │  coleta, valida, organiza e empacota bases
│ scripts/etl_status.py    │  registra etapas e mensagens sem dados brutos
│ gerar_dashboard_web.py   │  monta o resumo JSON para o HTML
└────────────┬─────────────┘
             │ arquivos preparados e telemetria
             ▼
┌──────────────────────────┐
│ Supabase Storage         │  Bucket privado: metalforte-private
│ Guarda a base publicada  │
│ e o status da carga      │
└────────────┬─────────────┘
             │ leitura quando necessário
             ├───────────────────────────────┐
             ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│ Streamlit                │    │ Monitor local            │
│ app.py → src/data.py →   │    │ monitor/server.py        │
│ src/operational_dashboard│    │ mostra agenda, etapas,   │
│ mostra o painel comercial│    │ versões e erros resumidos│
└──────────────────────────┘    └──────────────────────────┘
```

## Quais dados passam em cada etapa?

| Informação | Origem | Programa que prepara | Destino no Supabase | Onde aparece |
|---|---|---|---|---|
| Faturamento, KG, margem e dimensões de vendas | TOTVS Analytics / GoodData, relatório 11078478 | `atualizar_gooddata.py` | `bases/metalforte_base.csv.gz`; metadados em `bases/status.json` | Streamlit, por meio de `src/data.py` e `src/operational_dashboard.py` |
| Metas | Relatórios de metas configurados no ETL | `atualizar_gooddata.py` | `bases/metalforte_metas.csv.gz` | Aba Metas; carregada quando a aba é aberta |
| Estoque | Relatório de estoque configurado no ETL | `atualizar_gooddata.py` | `bases/metalforte_estoque.csv.gz` | Aba Estoque; carregada quando a aba é aberta |
| Eventos operacionais / funil | Relatório auxiliar configurado no ETL | `atualizar_gooddata.py` | `bases/metalforte_fluxo.csv.gz` | Áreas do painel que consultam o funil |
| Pedido × Realizado | Relatório auxiliar de pedidos, quando habilitado | `atualizar_gooddata.py` | `bases/metalforte_pedidos_realizado.csv.gz` | Área do painel correspondente, sob demanda |
| Estado da carga | Mensagens do workflow, sem conteúdo bruto | `scripts/etl_status.py` | `etl/latest.json` e `etl/runs/{id}.json` | Monitor local e torre de controle |
| Resumo do Command Center HTML | Base e indicadores já tratados | `gerar_dashboard_web.py` | `dashboard/command-center.json` | Resumo HTML |

Os nomes dos arquivos auxiliares podem mudar se forem configurados caminhos diferentes no workflow. O bucket de produção é privado; as chaves não devem ser colocadas no HTML nem enviadas ao Git.

## O que atualiza quando?

| Parte | Quando | O que isso significa |
|---|---|---|
| Extração de dados | GitHub Actions tenta às :17 e :47 de cada hora; regra de intervalo exige 55 min desde a última carga bem-sucedida | O GitHub inicia o trabalho. O minuto é uma janela de tentativa, não uma garantia de início exato. |
| Preparação Python | Dentro da execução do GitHub Actions | O Python coleta os relatórios, organiza e publica os arquivos. O processo pode durar vários minutos. |
| Publicação Supabase | No fim de cada publicação válida | Os arquivos e o status passam a representar a carga publicada. |
| Painel Streamlit | Quando o app consulta os dados | O Streamlit não dispara a extração. Ele busca a cópia do Supabase e usa cache de até 2 horas; uma publicação nova pode gerar uma nova chave de cache. |
| Monitor local | Consulta automática a cada 60 segundos | Só atualiza o que ele lê de GitHub, Supabase e do teste de saúde do Streamlit. Não inicia uma carga. |
| Código do Streamlit | Quando a mudança chega a `main` e o Streamlit Cloud implanta a revisão | É uma atualização do aplicativo, separada da atualização horária dos dados. |
| HTML em GitHub Pages | Ao alterar `web/` em `main`, ou ao disparar manualmente `publicar-command-center-html.yml` | Publica o site HTML estático; não publica o app Streamlit. |

## Em que lugar ficam os logs e as senhas?

- **Senhas TOTVS e chave de serviço Supabase:** GitHub → repositório → Settings → Secrets and variables → Actions. Não são arquivos do painel e nunca devem aparecer no navegador.
- **Log detalhado de execução:** GitHub → Actions → workflow “Atualizar base comercial” → execução escolhida. O monitor abre essa página por um link.
- **Resumo sanitizado das etapas:** objeto `etl/latest.json` no bucket privado. Ele mostra status e mensagens operacionais, não o conteúdo integral do log.
- **Código e configuração:** pasta do repositório `xupinsky-oss/metalforte-360`, branch `main`; workflow em `.github/workflows/atualizar-base.yml`.

## O que o monitor consegue confirmar

- GitHub: revisão de código configurada, versão declarada, estado e histórico recente do workflow.
- Python: versão do runtime declarada no workflow e horário da execução.
- Supabase: hora da base publicada e telemetria sanitizada, quando o acesso privado está configurado localmente.
- Streamlit: se a aplicação responde ao teste público de saúde. O serviço não revela publicamente qual versão está implantada; por isso, versão esperada do código e saúde do serviço são mostradas separadamente.
- TOTVS/GoodData: horário registrado para a etapa de extração. A integração atual não informa uma versão própria do relatório.
