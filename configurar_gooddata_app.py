import streamlit as st
from pathlib import Path
from src.secure_credentials import save_credential

st.set_page_config(page_title='Configurar GoodData | Metalforte 360',page_icon='🔐',layout='centered')
st.title('🔐 Configurar atualização GoodData')
st.write('A credencial será criptografada pelo Windows e vinculada ao seu usuário. Ela não será exibida nem gravada no código.')
with st.form('credential'):
    login=st.text_input('E-mail do TOTVS Analytics')
    password=st.text_input('Senha',type='password')
    submitted=st.form_submit_button('Salvar credencial',type='primary',width='stretch')
if submitted:
    if not login.strip() or not password: st.error('Preencha o e-mail e a senha.')
    else:
        target=Path(__file__).parent/'.streamlit'/'gooddata_credential.bin'
        save_credential(target,login.strip(),password)
        st.success('Credencial salva e protegida pelo Windows. Você já pode fechar esta página.')
