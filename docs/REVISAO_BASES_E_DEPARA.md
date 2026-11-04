# Revisão das bases e do DE/PARA — 04/11/2026

## Diagnóstico confirmado

- O projeto Supabase `metalforte-360` tem bucket privado `metalforte-private`.
- Vendas, metas, estoque, fluxo e pedidos estão publicados em `bases/`; a consulta confirmou cargas em 04/11/2026 às 22:01 UTC (19:01 de Brasília).
- O arquivo `bases/DE_PARA_METALFORTE360.xlsx` não estava publicado na inspeção. Portanto, o agrupamento não poderia aparecer no painel.
- A planilha fornecida possui cabeçalho de clientes na segunda linha. O importador anterior procurava os títulos na primeira linha.
- O cache anterior podia memorizar a ausência do mapeamento durante toda a vida do processo. A chave da base considerava apenas a carga comercial, não a versão do DE/PARA.

## Organização adotada

| Informação | Fonte de produção | Processo responsável |
| --- | --- | --- |
| Vendas realizadas | Storage privado / bases/metalforte_base.csv.gz | GitHub Actions → atualizar_gooddata.py |
| Metas | Storage privado / bases/metalforte_metas.csv.gz | Mesmo processo de carga |
| Estoque atual | Storage privado / bases/metalforte_estoque.csv.gz | Mesmo processo de carga |
| Pedidos × realizado | Storage privado / bases/metalforte_pedidos_realizado.csv.gz | Mesmo processo de carga |
| Eventos operacionais | Storage privado / bases/metalforte_fluxo.csv.gz | Mesmo processo; carregado somente quando necessário |
| Grupos de clientes e vendedores | Storage privado / bases/DE_PARA_METALFORTE360.xlsx | Administrador importa no app; mesma validação no CLI |
| Matriz de produtos e cidades PIVOT | resources/ no repositório | Referências versionadas; não são extrações GoodData |
| Limites geográficos e logo | Repositório | Arquivos estáticos da interface |

`src/data_catalog.py` é o catálogo dos caminhos, compartilhado pelo leitor e pelo ETL. Os caminhos de homologação acompanham o ambiente da base principal, salvo configuração explícita. O DE/PARA é corporativo e compartilhado entre ambientes.

As pastas locais data/raw e data/backup são apoio de desenvolvimento e execução do ETL. Com Supabase configurado, o app não usa arquivos locais para substituir silenciosamente uma falha da nuvem. O computador do usuário não precisa ficar ligado para executar o agendamento do GitHub.

## Correções e desempenho

- Importação detecta o cabeçalho nas primeiras 25 linhas, retém clientes sem grupo para auditoria e envia somente as colunas de agrupamento.
- Códigos numéricos com zeros à esquerda são conciliados sem alterar nomes jurídicos ou valores financeiros.
- A versão do DE/PARA participa da chave de cache. Uma consulta leve de metadados, em cache por 60 segundos, detecta mudanças no próximo uso da tela.
- A leitura de cinco bases usa uma única função e registra a classe de falha, sem imprimir tokens ou conteúdo de respostas privadas.
- A normalização dos nomes do DE/PARA trabalha nos valores distintos; os filtros globais são aplicados uma vez ao histórico e depois o calendário recorta o resultado.
- O dicionário de nomes para os visuais é calculado uma vez por versão de dados.
- A publicação administrativa e o CLI usam `publish_depara`, que valida, envia e confere a integridade por SHA-256.

## O que falta aplicar em produção

O envio pelo navegador foi bloqueado pela configuração da extensão; o arquivo não foi publicado nesta revisão. Foi gerada uma cópia validada, sem contatos ou documentos fiscais, para importar pelo botão administrativo existente. O código corrigido precisa passar pelo fluxo de publicação do repositório para entrar no Streamlit. Não foram alterados segredos, permissões ou políticas do Supabase.

No app: abrir **DE/PARA de clientes e vendedores**, selecionar o arquivo validado e clicar em **Validar e carregar DE/PARA**. Conferir a mensagem de sucesso e a aba **Validação DE/PARA**. A cópia validada tem 63.823 clientes e 81 vendedores; 688 linhas de clientes possuem grupo preenchido, distribuídas em 124 grupos. Os demais cadastros usam a razão social.
