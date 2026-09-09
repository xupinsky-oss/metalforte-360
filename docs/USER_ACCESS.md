# Usuários e permissões

## Modelo de segurança

O login usa Supabase Auth. A senha é enviada pelo servidor Streamlit diretamente ao endpoint de autenticação e não é salva pelo aplicativo. A chave administrativa permanece apenas nos Secrets do Streamlit.

Autorizações são armazenadas em `app_metadata`:

- `mf_role`: perfil do usuário;
- `mf_permissions`: lista explícita de permissões;
- `etl_admin`: compatibilidade com a autorização do ETL Control Tower.

`user_metadata` contém apenas o nome de exibição e nunca controla permissões.

## Primeiro administrador

Defina `METALFORTE_ADMIN_EMAILS` nos Secrets com o e-mail de um usuário existente no Supabase Auth. Depois do primeiro acesso, esse administrador pode abrir **Gestão de acessos**, criar usuários e atribuir perfis diretamente no painel.

## Recuperação de acesso

Outro administrador pode selecionar o usuário em **Gestão de acessos**, informar uma nova senha com no mínimo oito caracteres e salvar. Senhas atuais nunca são exibidas.

## Compartilhamento

O endereço oficial é `https://metalforte-360.streamlit.app/`. Cadastre primeiro a pessoa em **Gestão de acessos** e compartilhe o e-mail e a senha inicial por canais separados. Cada usuário visualiza somente as páginas permitidas em `mf_permissions`.

## Princípio do menor privilégio

Conceda `manage_users` apenas a administradores. Libere `view_pivot` e `export_data` somente a quem realmente precisa consultar ou exportar dados detalhados.
