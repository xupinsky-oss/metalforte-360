"""Agrupamento da navegação por área sem ampliar as permissões do usuário."""

from collections import OrderedDict


PAGE_GROUPS = {
    "view_overview": "Visão geral",
    "view_order_actual": "Visão geral",
    "export_reports": "Visão geral",
    "view_clients": "Comercial",
    "view_products": "Comercial",
    "view_sellers": "Comercial",
    "view_targets": "Comercial",
    "view_daily": "Operações",
    "view_stock": "Operações",
    "view_dimension_validation": "Operações",
    "view_pricing": "Inteligência",
    "view_margin_volume": "Inteligência",
    "view_map": "Inteligência",
    "view_heatmap": "Inteligência",
    "view_insights": "Inteligência",
    "view_commercial_direction": "Inteligência",
    "view_pivot": "Inteligência",
    "view_yoy": "Inteligência",
    "use_assistant": "Inteligência",
    "manage_users": "Administração",
}

GROUP_ORDER = (
    "Visão geral",
    "Comercial",
    "Operações",
    "Inteligência",
    "Administração",
)


def group_pages(pages):
    """Organiza apenas as páginas recebidas; permissões continuam definindo o acesso."""
    grouped = OrderedDict()
    for group in GROUP_ORDER:
        selected = [page for page in pages if PAGE_GROUPS.get(page[1]) == group]
        if selected:
            grouped[group] = selected
    ungrouped = [page for page in pages if page[1] not in PAGE_GROUPS]
    if ungrouped:
        grouped["Outras visões"] = ungrouped
    return grouped
