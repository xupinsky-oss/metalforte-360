# DE/PARA de clientes e vendedores

O painel usa os agrupamentos do arquivo `DE_PARA_METALFORTE360.xlsx` sem substituir os nomes ou códigos originais das bases GoodData/TOTVS.

## Campos derivados

- `Grupo Econômico Cliente`: obtido pelo código e loja do cliente; usa o nome normalizado como alternativa quando não há chave numérica correspondente.
- `Vendedor Painel`: nome consolidado definido na aba `DE_PARA_VENDEDOR`.
- `Grupo Vendedor`: classificação da aba `DE_PARA_VENDEDOR`.

As novas dimensões aparecem nos filtros laterais, na análise de vendedores, na Batalha Naval (grupos econômicos) e na Tabela dinâmica. Registros sem correspondência são identificados como `Não mapeado`; eles não são unidos artificialmente.

## Como carregar

1. Publique o código atualizado no repositório conectado ao Streamlit.
2. Entre no METALFORTE 360 com um usuário administrador.
3. Na barra lateral, abra **DE/PARA de clientes e vendedores**.
4. Escolha o arquivo `DE_PARA_METALFORTE360.xlsx` e clique em **Validar e carregar DE/PARA**.
5. O app valida as abas e colunas, remove colunas que não são usadas e envia apenas o arquivo reduzido para o bucket privado.
6. A página recarrega e exibe **Agrupamentos privados carregados** quando o objeto estiver acessível.

O objeto é salvo por padrão em `bases/DE_PARA_METALFORTE360.xlsx` no bucket configurado em `SUPABASE_BUCKET` (por padrão, `metalforte-private`). Se necessário, defina `SUPABASE_DEPARA_PATH` nas variáveis privadas do Streamlit. A chave de serviço do Supabase nunca deve ser colocada no código nem no arquivo `.env.example`.

## Campos que são armazenados

Antes do envio, o aplicativo cria uma cópia reduzida contendo somente:

- Vendedores: `VENDEDOR CADASTRO`, `CLASSIFICAÇÃO` e `VENDEDOR PAINEL`.
- Clientes: código, loja (quando disponível), nome do cliente e `GRUPO ECONOMICO`.

E-mail, telefone, CPF/CNPJ, endereço e demais dados da planilha não são enviados ao armazenamento privado.

## Atualizações posteriores

Para substituir o DE/PARA, carregue uma nova versão pelo mesmo painel administrativo. A versão nova substitui o objeto privado e a base em cache é recarregada na sessão.

