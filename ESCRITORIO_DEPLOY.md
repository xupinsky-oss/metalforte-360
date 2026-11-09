# Escritório METALFORTE 360

Esta é uma implantação separada do METALFORTE 360, na branch `escritorio-metalforte`, com entrada Streamlit `escritorio.py`. O app principal em `main` não foi alterado.

## Publicar como um segundo app Streamlit

1. No Streamlit Community Cloud, escolha **Create app**.
2. Selecione o repositório `xupinsky-oss/metalforte-360`.
3. Selecione a branch `escritorio-metalforte`.
4. Informe `escritorio.py` como **Main file path**.
5. Em **Advanced settings > Secrets**, copie os Secrets da implantação atual do METALFORTE 360. Não coloque valores de segredo no repositório ou em mensagens.
6. Publique e entre com um usuário que tenha perfil de administração, gestão ou análise.

## Fontes usadas

O Escritório importa os carregadores já utilizados pelo app principal:

- vendas, metas, estoque e fluxo por `src.data`;
- DE/PARA de clientes e vendedores pelo Supabase configurado no projeto;
- anexos auxiliares enviados para o bucket privado Supabase já configurado.

Os painéis não substituem nem copiam as bases. Eles consultam as mesmas referências configuradas para o METALFORTE 360.

## Entregas

As abas dos sete colaboradores exibem análises calculadas a partir do período mais recente disponível. Quando uma fonte não contém o dado necessário, a tela sinaliza a ausência e evita criar valores fictícios. O fluxo de vendas exibido ao Trade representa sell-in; a fonte atual não inclui sell-out das revendas.
