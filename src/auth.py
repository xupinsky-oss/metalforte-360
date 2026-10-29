"""Autenticação e autorização do Streamlit usando Supabase Auth.

Todas as chamadas acontecem no servidor Streamlit. A chave administrativa nunca
é enviada ao navegador e permissões são lidas exclusivamente de app_metadata.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests
import streamlit as st

from src.version import APP_RELEASE


PERMISSION_LABELS = {
    "view_overview": "Visão executiva",
    "view_clients": "Inteligência de clientes",
    "view_products": "Inteligência de produtos",
    "view_stock": "Estoque e giro de produtos",
    "view_daily": "Performance diária",
    "view_sellers": "Visão por vendedor",
    "view_pricing": "Inteligência de preços",
    "view_margin_volume": "Volume × margem",
    "view_targets": "Metas e orçamento",
    "view_map": "Mapa comercial por município",
    "view_heatmap": "Mapa mensal de positivação e faturamento",
    "view_insights": "Insights e oportunidades",
    "view_pivot": "Tabela dinâmica",
    "view_yoy": "Comparativo anual",
    "use_assistant": "Assistente analítico",
    "export_data": "Exportar relatórios",
    "manage_users": "Administrar usuários",
}

ROLE_LABELS = {
    "viewer": "Consulta",
    "seller": "Vendedor",
    "analyst": "Analista",
    "manager": "Gestor",
    "admin": "Administrador",
}

ROLE_PRESETS = {
    "viewer": {"view_overview", "view_clients", "view_products", "view_map", "view_heatmap"},
    "seller": {
        "view_overview", "view_clients", "view_products", "view_daily",
        "view_sellers", "view_targets", "view_insights",
        "view_map", "view_heatmap",
    },
    "analyst": {
        "view_overview", "view_clients", "view_products", "view_stock", "view_daily",
        "view_sellers", "view_pricing", "view_margin_volume", "view_targets", "view_insights", "view_yoy",
        "view_map", "view_heatmap",
    },
    "manager": {
        "view_overview", "view_clients", "view_products", "view_stock", "view_daily",
        "view_sellers", "view_pricing", "view_margin_volume", "view_targets", "view_insights", "view_pivot", "view_yoy",
        "view_map", "view_heatmap", "use_assistant", "export_data",
    },
    "admin": set(PERMISSION_LABELS),
}


class AuthError(RuntimeError):
    """Erro controlado de autenticação ou administração."""


class AuthUnavailable(AuthError):
    """Serviço de login fora do ar, lento ou com resposta inesperada (não é senha errada)."""


UNAVAILABLE_MESSAGE = (
    "Não foi possível conectar ao serviço de login. Tente novamente em instantes."
)


def _settings(require_admin=False):
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    public_key = os.getenv("SUPABASE_ANON_KEY", "") or service_key
    if not url or not public_key or (require_admin and not service_key):
        raise AuthError(
            "A autenticação segura ainda não foi configurada no ambiente do Streamlit."
        )
    return url, public_key, service_key


def _request(method, path, *, admin=False, token=None, payload=None, timeout=30):
    url, public_key, service_key = _settings(require_admin=admin)
    api_key = service_key if admin else public_key
    bearer = service_key if admin else token
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    try:
        response = requests.request(
            method, f"{url}{path}", headers=headers, json=payload, timeout=timeout
        )
    except requests.RequestException as exc:
        # Sem rede, DNS, recusa de conexão ou tempo esgotado: nunca expor o detalhe técnico.
        raise AuthUnavailable(UNAVAILABLE_MESSAGE) from exc
    if response.status_code >= 500 or response.status_code == 429:
        raise AuthUnavailable(UNAVAILABLE_MESSAGE)
    if response.status_code >= 400:
        try:
            body = response.json()
            detail = (body.get("msg") or body.get("message")) if isinstance(body, dict) else None
        except ValueError:
            detail = None
        raise AuthError(detail or f"Operação não concluída ({response.status_code}).")
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise AuthUnavailable(UNAVAILABLE_MESSAGE) from exc


def sign_in(email, password):
    return _request(
        "POST", "/auth/v1/token?grant_type=password",
        payload={"email": email.strip().lower(), "password": password},
    )


def _refresh_session(session):
    refreshed = _request(
        "POST", "/auth/v1/token?grant_type=refresh_token",
        payload={"refresh_token": session.get("refresh_token", "")},
    )
    st.session_state["mf_auth_session"] = refreshed
    return refreshed


def _admin_emails():
    return {
        email.strip().lower()
        for email in os.getenv("METALFORTE_ADMIN_EMAILS", "").split(",")
        if email.strip()
    }


def authorization_for(user):
    metadata = user.get("app_metadata") or {}
    email = str(user.get("email") or "").lower()
    bootstrap_admin = email in _admin_emails() or metadata.get("etl_admin") is True
    role = "admin" if bootstrap_admin else metadata.get("mf_role", "viewer")
    if role not in ROLE_PRESETS:
        role = "viewer"
    configured = metadata.get("mf_permissions")
    permissions = set(configured) if isinstance(configured, list) else set(ROLE_PRESETS[role])
    permissions &= set(PERMISSION_LABELS)
    if role == "admin" or bootstrap_admin:
        permissions = set(PERMISSION_LABELS)
    return {
        "role": role,
        "permissions": permissions,
        "seller_scope": metadata.get("mf_seller_scope", ""),
        "user": user,
    }


def _inject_login_styles():
    st.markdown(
        """<style>
        .stApp{background:linear-gradient(180deg,#FFFFFF 0,#F2F5F9 100%)}
        [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"]{display:none}
        .block-container{padding-top:clamp(1.5rem,8vh,5rem)!important;padding-bottom:2rem!important}
        .st-key-mf_login{max-width:430px;margin:0 auto;background:#FFFFFF;border:1px solid #DCE3EC;
          border-top:4px solid #F36A2D;border-radius:14px;padding:2rem 2rem 1.4rem;
          box-shadow:0 12px 36px rgba(23,32,51,.08);gap:.6rem}
        .mf-login-head{margin-bottom:1rem}
        .mf-login-eyebrow{font-size:.74rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#C54112}
        .mf-login-title{font-size:2rem!important;font-weight:800!important;color:#172033!important;
          letter-spacing:-.02em;margin:.15rem 0 .35rem!important;padding:0!important;line-height:1.15!important}
        .mf-login-sub{font-size:.95rem;color:#52647A;margin:0}
        .st-key-mf_login [data-testid="stForm"]{padding:0}
        .st-key-mf_login label p{font-size:.88rem!important;font-weight:650!important;color:#27364A!important}
        .st-key-mf_login [data-testid="stTextInputRootElement"]{background:#F7F9FC!important;border:1px solid #CBD5E1!important;
          border-radius:9px!important;transition:border-color .15s,box-shadow .15s}
        .st-key-mf_login [data-testid="stTextInputRootElement"]:hover{border-color:#94A3B8!important}
        .st-key-mf_login [data-testid="stTextInputRootElement"]:focus-within{border-color:#F36A2D!important;
          box-shadow:0 0 0 3px rgba(243,106,45,.15)!important;background:#FFFFFF!important}
        .st-key-mf_login input{background:transparent!important;color:#172033!important;font-size:.98rem!important}
        .st-key-mf_login input::placeholder{color:#8391A5!important;opacity:1!important}
        .st-key-mf_login [data-testid="stFormSubmitButton"] button{background:#F36A2D!important;border:1px solid #F36A2D!important;
          color:#FFFFFF!important;font-weight:700!important;min-height:44px;border-radius:9px!important;margin-top:.35rem}
        .st-key-mf_login [data-testid="stFormSubmitButton"] button:hover{background:#D9561D!important;border-color:#D9561D!important}
        .st-key-mf_login [data-testid="stFormSubmitButton"] button p{color:#FFFFFF!important;font-weight:700!important}
        .mf-login-foot{font-size:.78rem;color:#8391A5;text-align:center;margin-top:.4rem}
        @media(max-width:699px){.st-key-mf_login{padding:1.5rem 1.2rem 1.1rem;border-radius:12px}
          .mf-login-title{font-size:1.7rem!important}}
        </style>""",
        unsafe_allow_html=True,
    )


def require_login():
    """Mostra o login e interrompe a página até haver uma sessão válida."""
    try:
        _settings()
    except AuthError as exc:
        st.error(str(exc))
        st.caption("Configure SUPABASE_URL, SUPABASE_SERVICE_KEY e METALFORTE_ADMIN_EMAILS nos Secrets do Streamlit.")
        st.stop()

    session = st.session_state.get("mf_auth_session")
    if session:
        expires_at = float(session.get("expires_at") or 0)
        if expires_at and time.time() >= expires_at - 60:
            try:
                session = _refresh_session(session)
            except AuthUnavailable:
                if time.time() >= expires_at:
                    st.session_state.pop("mf_auth_session", None)
                    session = None
            except AuthError:
                st.session_state.pop("mf_auth_session", None)
                session = None
    if not session:
        _inject_login_styles()
        with st.container(key="mf_login"):
            logo_path = Path(__file__).resolve().parents[1] / "LOGO_METALFORTE.jpg"
            if logo_path.exists():
                st.image(str(logo_path), width=200)
            st.markdown(
                '<div class="mf-login-head">'
                '<div class="mf-login-eyebrow">Painel comercial</div>'
                '<h1 class="mf-login-title">METALFORTE 360</h1>'
                '<p class="mf-login-sub">Entre com seu e-mail corporativo para acessar o painel.</p>'
                '</div>',
                unsafe_allow_html=True,
            )
            with st.form("secure_login", border=False):
                email = st.text_input("E-mail", placeholder="nome@empresa.com.br")
                password = st.text_input("Senha", type="password", placeholder="Sua senha")
                submit = st.form_submit_button("Entrar", type="primary", width="stretch")
            if submit:
                if not email.strip() or not password:
                    st.warning("Informe e-mail e senha para entrar.")
                else:
                    try:
                        st.session_state["mf_auth_session"] = sign_in(email, password)
                        st.rerun()
                    except AuthUnavailable:
                        st.error(UNAVAILABLE_MESSAGE)
                    except AuthError:
                        st.error("E-mail ou senha inválidos.")
            st.markdown(
                f'<div class="mf-login-foot">Acesso restrito a usuários autorizados · versão {APP_RELEASE}</div>',
                unsafe_allow_html=True,
            )
        st.stop()
    return authorization_for(session.get("user") or {})


def logout():
    st.session_state.pop("mf_auth_session", None)
    st.session_state.pop("mf_page", None)


def list_users():
    response = _request("GET", "/auth/v1/admin/users?page=1&per_page=200", admin=True)
    return response.get("users", []) if isinstance(response, dict) else []


def create_user(email, password, display_name, role, permissions, seller_scope=""):
    if len(password) < 8:
        raise AuthError("A senha inicial deve ter pelo menos 8 caracteres.")
    return _request(
        "POST", "/auth/v1/admin/users", admin=True,
        payload={
            "email": email.strip().lower(),
            "password": password,
            "email_confirm": True,
            "user_metadata": {"display_name": display_name.strip()},
            "app_metadata": {
                "mf_role": role,
                "mf_permissions": sorted(set(permissions)),
                "mf_seller_scope": seller_scope.strip() if role == "seller" else "",
                "etl_admin": role == "admin",
            },
        },
    )


def update_user(user_id, role, permissions, new_password="", existing_metadata=None, seller_scope=""):
    metadata = dict(existing_metadata or {})
    metadata.update({
        "mf_role": role,
        "mf_permissions": sorted(set(permissions)),
        "mf_seller_scope": seller_scope.strip() if role == "seller" else "",
        "etl_admin": role == "admin",
    })
    payload = {
        "app_metadata": metadata
    }
    if new_password:
        if len(new_password) < 8:
            raise AuthError("A nova senha deve ter pelo menos 8 caracteres.")
        payload["password"] = new_password
    return _request("PUT", f"/auth/v1/admin/users/{user_id}", admin=True, payload=payload)


def render_user_admin(current_user, seller_options=None):
    """Cadastro, redefinição de senha e permissões, disponível só ao administrador."""
    st.subheader(
        "Gestão de acessos",
        help="Usuários são autenticados pelo Supabase Auth. Perfis, permissões e carteira do vendedor ficam em metadados protegidos do servidor e não são expostos no navegador.",
    )
    st.caption("Crie usuários, defina perfis e escolha exatamente quais áreas cada pessoa pode acessar.")
    st.info(
        "Compartilhe o painel em https://metalforte-360.streamlit.app/ e envie a senha inicial "
        "por um canal separado. Senhas nunca são exibidas ou armazenadas pelo painel."
    )

    with st.expander("Criar usuário", expanded=True):
        with st.form("create_user"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Nome")
            email = c2.text_input("E-mail")
            c3, c4 = st.columns(2)
            role = c3.selectbox(
                "Perfil", list(ROLE_LABELS),
                format_func=lambda value: ROLE_LABELS[value], key="new_user_role",
            )
            password = c4.text_input("Senha inicial", type="password")
            seller_scope = st.selectbox(
                "Carteira do vendedor",
                [""] + sorted(set(seller_options or [])),
                help="Obrigatório para o perfil Vendedor. Limita todas as páginas à própria carteira.",
                key="new_seller_scope",
            )
            default_permissions = sorted(ROLE_PRESETS[role])
            permissions = st.multiselect(
                "Permissões", list(PERMISSION_LABELS), default=default_permissions,
                format_func=lambda value: PERMISSION_LABELS[value], key=f"new_permissions_{role}",
            )
            submitted = st.form_submit_button("Criar usuário", width="stretch")
        if submitted:
            try:
                if role == "seller" and not seller_scope:
                    raise AuthError("Selecione a carteira para o perfil Vendedor.")
                create_user(email, password, name, role, permissions, seller_scope)
                st.success("Usuário criado. O acesso já está disponível.")
                st.cache_data.clear()
            except AuthError as exc:
                st.error(str(exc))

    try:
        users = list_users()
    except AuthError as exc:
        st.error(str(exc))
        return
    if not users:
        st.info("Nenhum usuário encontrado.")
        return

    rows = []
    for user in users:
        access = authorization_for(user)
        rows.append({
            "E-mail": user.get("email", ""),
            "Nome": (user.get("user_metadata") or {}).get("display_name", ""),
            "Perfil": ROLE_LABELS.get(access["role"], access["role"]),
            "Permissões": ", ".join(
                PERMISSION_LABELS[item] for item in sorted(access["permissions"])
            ),
            "Último acesso": user.get("last_sign_in_at") or "—",
        })
    st.dataframe(rows, width="stretch", hide_index=True)

    own_id = current_user.get("id")
    editable = [user for user in users if user.get("id") != own_id]
    if not editable:
        st.info("Não há outro usuário para editar.")
        return
    st.markdown("#### Alterar perfil, permissões ou senha")
    selected_id = st.selectbox(
        "Selecione o usuário", [user["id"] for user in editable],
        format_func=lambda user_id: next(user.get("email", user_id) for user in editable if user["id"] == user_id),
    )
    selected = next(user for user in editable if user["id"] == selected_id)
    selected_access = authorization_for(selected)
    with st.form("edit_user"):
        role = st.selectbox(
            "Perfil", list(ROLE_LABELS), index=list(ROLE_LABELS).index(selected_access["role"]),
            format_func=lambda value: ROLE_LABELS[value], key=f"edit_role_{selected_id}",
        )
        permissions = st.multiselect(
            "Permissões", list(PERMISSION_LABELS),
            default=sorted(selected_access["permissions"]),
            format_func=lambda value: PERMISSION_LABELS[value], key=f"edit_permissions_{selected_id}",
        )
        password = st.text_input("Nova senha (opcional)", type="password")
        saved_scope = selected_access.get("seller_scope", "")
        scope_options = [""] + sorted(set((seller_options or []) + ([saved_scope] if saved_scope else [])))
        seller_scope = st.selectbox(
            "Carteira do vendedor", scope_options,
            index=scope_options.index(saved_scope) if saved_scope in scope_options else 0,
            help="Obrigatório para o perfil Vendedor.", key=f"edit_scope_{selected_id}",
        )
        submitted = st.form_submit_button("Salvar alterações", width="stretch")
    if submitted:
        try:
            if role == "seller" and not seller_scope:
                raise AuthError("Selecione a carteira para o perfil Vendedor.")
            update_user(selected_id, role, permissions, password, selected.get("app_metadata"), seller_scope)
            st.success("Permissões e acesso atualizados.")
            st.rerun()
        except AuthError as exc:
            st.error(str(exc))
