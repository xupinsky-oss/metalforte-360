# Monitoramento do ETL

A Control Tower consulta `etl-control` usando a sessão Supabase do usuário. A função lê objetos JSON do bucket privado:

- `etl/latest.json`: execução mais recente;
- `etl/runs/<request-id>.json`: histórico por execução.

Cada registro contém somente identificadores, ambiente, escopo, solicitante, motivo, horários, estado das etapas e mensagens operacionais pré-definidas. Não contém dados comerciais brutos, cookies, senhas, tokens ou corpos de resposta das fontes.

## Estados

- `queued`: solicitação aceita;
- `in_progress`: workflow em execução;
- `success`: carga e resumo concluídos;
- `failure`: execução falhou;
- etapas: `pending`, `running`, `completed` ou `failed`.

O histórico visual mostra até 20 registros. O botão de exportação gera uma cópia local do conteúdo já autorizado ao usuário.
