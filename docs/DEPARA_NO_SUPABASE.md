# Editar clientes e vendedores no Supabase

O DE/PARA do METALFORTE 360 passou a ser mantido em tabelas do projeto Supabase metalforte-360. A planilha foi usada para a carga inicial. Clientes sem grupo continuam aparecendo pela razão social.

1. Abra https://supabase.com/dashboard/project/uaqekqgnwxpbfetqxmnb/editor e selecione o schema public.
2. Na tabela **depara_clientes**, procure o cadastro pelo código ou razão social e edite **grupo_economico**.
3. Na tabela **depara_vendedores**, procure **vendedor_cadastro** e edite **vendedor_painel** e **classificacao**.
4. Salve a alteração no Supabase e clique em **Atualizar visualização** no painel. A revisão também é consultada no próximo uso da tela, com cache de até 60 segundos.

Preserve codigo_cliente, loja e vendedor_cadastro: esses campos fazem o vínculo com os registros de origem. Para cadastrar uma nova correspondência, adicione uma linha com a mesma identificação da base. O campo ativo=false permite desativar uma correspondência sem apagar o cadastro.

## Carga e conferência

Foram importados 63.823 clientes e 81 vendedores. Na planilha inicial, 688 cadastros de clientes tinham grupo preenchido, em 124 grupos distintos. Código+loja e vendedor_cadastro foram conferidos sem duplicidade. A carga contém somente os campos de agrupamento; contatos e CPF/CNPJ não foram importados.

## Funcionamento e acesso

- O app consulta metalforte_depara_version para verificar a revisão e metalforte_depara_snapshot para carregar a referência completa de forma consistente.
- As tabelas usam RLS e não concedem leitura aos papéis anon ou authenticated. A leitura do app ocorre exclusivamente no servidor com o acesso já configurado. O Table Editor é acessado por quem possui permissão no projeto Supabase.
- Os gatilhos atualizam a revisão após inclusão, alteração ou exclusão de cadastros. As consultas usam SECURITY INVOKER; não elevam privilégios de usuários.
- A planilha no Storage é apenas compatibilidade para instalações ainda não migradas. Com as tabelas prontas, o app usa as tabelas e a importação antiga é bloqueada para não sobrescrever ou ocultar edições manuais.
- Estrutura aplicada no Supabase: migração depara_clientes_vendedores; cópia do SQL em supabase/depara_schema.sql. Os dados privados não entram no GitHub.
