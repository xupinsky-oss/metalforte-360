"""Painel local para receber e publicar a carga manual do GoodData."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.manual_load import (
    INPUT_DIR,
    OPTIONAL_FLOW_REPORTS,
    OPTIONAL_LOSS_REPORT,
    OPTIONAL_STOCK_REPORT,
    REQUIRED_REPORTS,
    folder_status,
    prepare_input_folder,
    run_manual_update,
    run_gooddata_update,
    save_upload,
)
from gerar_painel_privado import generate_private_dashboard


st.set_page_config(page_title="Carga manual | METALFORTE 360", page_icon="📥", layout="wide")
prepare_input_folder()

st.title("Carga manual do METALFORTE 360")
st.caption("Exporte os relatórios no GoodData, salve nesta pasta e publique a carga após a validação.")
st.info(f"Pasta de entrada: {INPUT_DIR}")

st.markdown(
    """
    **Rotina diária**

    1. Exporte os relatórios do GoodData em CSV ou ZIP.
    2. Arraste os arquivos abaixo ou coloque-os diretamente na pasta de entrada com os nomes indicados.
    3. Confira se os sete relatórios obrigatórios estão como **Pronto**.
    4. Clique em **Validar e atualizar painel**.
    """
)

st.subheader("Atualização automática — recomendada")
st.caption("Usa as rotinas oficiais já atualizadas no TOTVS/GoodData: comercial, pedidos, clientes, produtos, produção e estoque.")
auto_confirm = st.checkbox("Confirmo que desejo consultar o GoodData/TOTVS agora.", key="auto_confirm")
if st.button("Atualizar base pelo GoodData/TOTVS", type="primary", disabled=not auto_confirm, width="stretch"):
    with st.spinner("Consultando GoodData/TOTVS, consolidando a base e validando os totais..."):
        try:
            automatic_result = run_gooddata_update()
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("Base atualizada pelo GoodData/TOTVS. Agora clique em Gerar painel privado.")
            st.json(automatic_result)

st.divider()
st.subheader("Carga manual — contingência")
st.caption("Use esta opção somente se precisar trabalhar com arquivos CSV/ZIP exportados manualmente.")

st.subheader("Situação dos arquivos")
status = pd.DataFrame(folder_status())
st.dataframe(status, width="stretch", hide_index=True)

with st.expander("Adicionar ou substituir arquivos", expanded=False):
    st.caption("O painel salva cada arquivo com o nome padrão; o nome original do download não importa.")
    for key, label in REQUIRED_REPORTS.items():
        uploaded = st.file_uploader(
            f"{label} — obrigatório ({key}.csv)",
            type=["csv", "txt", "zip"],
            key=f"upload_{key}",
        )
        if uploaded is not None and st.button(f"Salvar {key}", key=f"save_{key}"):
            save_upload(key, uploaded.getvalue())
            st.success(f"{key}.csv salvo.")
    st.divider()
    st.caption("Complementares: atualizam datas do funil e o quadro de perdas.")
    for key, label in OPTIONAL_FLOW_REPORTS.items():
        uploaded = st.file_uploader(f"{label} — opcional ({key}.csv)", type=["csv", "txt", "zip"], key=f"upload_{key}")
        if uploaded is not None and st.button(f"Salvar {key}", key=f"save_{key}"):
            save_upload(key, uploaded.getvalue())
            st.success(f"{key}.csv salvo.")
    uploaded = st.file_uploader("Perdas por motivo — opcional (perdas_por_motivo.csv)", type=["csv", "txt", "zip"], key="upload_perdas")
    if uploaded is not None and st.button("Salvar perdas por motivo", key="save_perdas"):
        save_upload(OPTIONAL_LOSS_REPORT, uploaded.getvalue())
        st.success("perdas_por_motivo.csv salvo.")
    uploaded = st.file_uploader("Estoque por produto — opcional (estoque_produto.csv)", type=["csv", "txt", "zip"], key="upload_estoque")
    if uploaded is not None and st.button("Salvar estoque por produto", key="save_estoque"):
        save_upload(OPTIONAL_STOCK_REPORT, uploaded.getvalue())
        st.success("estoque_produto.csv salvo.")

st.divider()
st.subheader("Publicação da carga manual")
confirm = st.checkbox("Confirmo que os arquivos foram extraídos para o período correto.")
if st.button("Validar e atualizar painel", type="primary", disabled=not confirm, width="stretch"):
    with st.spinner("Validando arquivos, consolidando a base e publicando o painel..."):
        try:
            result = run_manual_update(publish=True)
        except Exception as exc:
            st.error(f"A carga não foi publicada: {exc}")
        else:
            st.success("Carga publicada com sucesso. O painel online lerá a nova versão em poucos instantes.")
            cols = st.columns(4)
            cols[0].metric("Linhas consolidadas", f"{result['linhas']:,}".replace(",", "."))
            cols[1].metric("Faturamento validado", f"R$ {result['faturamento']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            cols[2].metric("Última data na base", result["ultima_data"])
            cols[3].metric("Eventos do funil", result["eventos_funil_atualizados"])
            st.json(result)

st.divider()
st.subheader("Painel HTML privado")
st.caption("Gera um arquivo local, separado do METALFORTE 360, para uso exclusivo da gestão comercial.")
if st.button("Gerar painel privado", width="stretch"):
    try:
        html_file = generate_private_dashboard()
    except Exception as exc:
        st.error(f"Não foi possível gerar o painel privado: {exc}")
    else:
        st.success("Painel HTML privado gerado.")
        st.code(str(html_file))

st.caption("A carga anterior é preservada automaticamente em data/backup antes da substituição.")
