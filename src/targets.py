"""Normalização, conciliação e alocação auditável das metas comerciais."""

from __future__ import annotations

import os
import re
import unicodedata
import io

import pandas as pd

from src.dimensions import normalize_dimensions, normalize_seller
from src.product_groups import normalize_product_group


TARGET_COLUMNS = [
    "Competência", "Vendedor", "Grupo Produto", "Meta KG", "Meta R$",
    "Fonte Meta KG", "Fonte Meta R$", "Metodologia R$",
]
TARGET_OPTIONAL_DIMENSIONS = [
    "Vendedor Painel", "Grupo Vendedor", "Grupo Econômico Cliente",
    "Cliente Painel", "Cliente", "Segmento Cliente", "Produto", "Produto Codigo",
]
TARGET_WORKBOOK_COLUMNS = [
    "Competência", "Vendedor", "Vendedor Painel", "Grupo Vendedor",
    "Grupo Produto", "Grupo Econômico Cliente", "Cliente Painel", "Cliente",
    "Segmento Cliente", "Produto", "Produto Codigo", "Meta R$", "Meta KG",
    "Observação",
]


def read_targets_workbook(payload):
    """Lê o arquivo de metas editável, aceitando a aba Metas ou a primeira aba."""
    workbook = pd.ExcelFile(io.BytesIO(payload))
    sheet = next((name for name in workbook.sheet_names if _plain(name) == "metas"), workbook.sheet_names[0])
    frame = pd.read_excel(workbook, sheet_name=sheet)
    frame.columns = [str(column).strip() for column in frame.columns]
    if frame.empty:
        return pd.DataFrame(columns=[*TARGET_WORKBOOK_COLUMNS, "Fonte Meta KG", "Fonte Meta R$", "Metodologia R$"])
    if "Competência" not in frame.columns:
        raise ValueError("A planilha de metas precisa da coluna Competência.")
    for column in ("Meta KG", "Meta R$"):
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = _number(frame[column]).fillna(0)
    for column in TARGET_OPTIONAL_DIMENSIONS:
        if column not in frame.columns:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    frame["Competência"] = pd.to_datetime(frame["Competência"], errors="coerce").dt.to_period("M").dt.start_time
    frame = frame.dropna(subset=["Competência"])
    return frame


def targets_workbook_bytes(frame):
    """Serializa metas em workbook Excel com instruções e dimensões opcionais."""
    data = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    for column in TARGET_WORKBOOK_COLUMNS:
        if column not in data.columns:
            data[column] = ""
    data = data[[*TARGET_WORKBOOK_COLUMNS, *[c for c in data.columns if c not in TARGET_WORKBOOK_COLUMNS]]]
    output = io.BytesIO()
    instructions = pd.DataFrame({
        "Campo": TARGET_WORKBOOK_COLUMNS,
        "Como preencher": [
            "Mês da meta, preferencialmente como data no primeiro dia do mês.",
            "Vendedor responsável. Deixe vazio apenas quando a meta não for atribuída a vendedor.",
            "Nome consolidado exibido no painel, se a meta estiver nessa granularidade.",
            "Grupo do vendedor, se aplicável.",
            "Grupo de produto conforme a nomenclatura do painel.",
            "Grupo econômico do cliente, conforme o DE/PARA interno.",
            "Nome consolidado do cliente, se a meta estiver nessa granularidade.",
            "Razão social ou nome do cliente, se a meta estiver nessa granularidade.",
            "Segmento do cliente, se a meta estiver nessa granularidade.",
            "Produto/SKU, se a meta estiver nessa granularidade.",
            "Código do produto, se a meta estiver nessa granularidade.",
            "Meta em reais. Pode ficar vazia se a meta for definida somente em KG.",
            "Meta em quilogramas. Pode ficar vazia se a meta for definida somente em R$.",
            "Observação livre para auditoria.",
        ],
    })
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        data.to_excel(writer, sheet_name="Metas", index=False)
        instructions.to_excel(writer, sheet_name="Instruções", index=False)
        for sheet_name in ("Metas", "Instruções"):
            ws = writer.book[sheet_name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for column_cells in ws.columns:
                width = min(max(max(len(str(cell.value or "")) for cell in column_cells) + 2, 14), 42)
                ws.column_dimensions[column_cells[0].column_letter].width = width
    return output.getvalue()


def empty_targets_workbook_bytes():
    return targets_workbook_bytes(pd.DataFrame(columns=TARGET_WORKBOOK_COLUMNS))


def _plain(value):
    text = unicodedata.normalize("NFKD", str(value))
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in text if not unicodedata.combining(ch)).lower()).strip()


def _number(series):
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    text = series.astype("string").str.strip().str.replace(r"[^0-9,.-]", "", regex=True)
    brazilian = text.str.contains(",", na=False)
    text.loc[brazilian] = text.loc[brazilian].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce")


def _column(frame, *candidates):
    normalized = {_plain(column): column for column in frame.columns}
    for candidate in candidates:
        if _plain(candidate) in normalized:
            return normalized[_plain(candidate)]
    for key, original in normalized.items():
        if any(_plain(candidate) in key for candidate in candidates):
            return original
    raise ValueError(f"Coluna de meta não encontrada: {', '.join(candidates)}")


def consolidate_targets(meta_kg, meta_value, competence=None):
    """Converte os relatórios oficiais em uma meta mensal conciliada."""
    competence = pd.Timestamp(competence or pd.Timestamp.today()).to_period("M").start_time
    seller = _column(meta_kg, "Vendedor")
    group = _column(meta_kg, "Grupo Prod.", "Grupo Produto")
    monthly = _column(meta_kg, "Meta Mês", "Meta Mes")
    value_column = _column(meta_value, "Vlr Orçamento", "Vlr Orcamento", "Orçamento", "Orcamento")

    detail = pd.DataFrame({
        "Vendedor": meta_kg[seller].astype("string").str.strip(),
        "Grupo Produto": meta_kg[group].map(normalize_product_group),
        "Meta KG": _number(meta_kg[monthly]),
    }).dropna(subset=["Vendedor", "Grupo Produto", "Meta KG"])
    detail = normalize_dimensions(detail)
    detail = detail[(detail["Vendedor"] != "") & (detail["Grupo Produto"] != "")]
    detail = detail.groupby(["Vendedor", "Grupo Produto"], as_index=False)["Meta KG"].sum()
    multiplier = float(os.getenv("TOTVS_TARGET_KG_MULTIPLIER", "1000"))
    detail["Meta KG"] *= multiplier

    official_value = float(_number(meta_value[value_column]).sum())
    total_kg = float(detail["Meta KG"].sum())
    if detail.empty or total_kg <= 0:
        raise ValueError("O relatório oficial não retornou uma meta mensal de KG positiva.")
    if official_value <= 0:
        raise ValueError("O relatório oficial não retornou uma meta mensal em R$ positiva.")

    detail["Competência"] = competence
    detail["Meta R$"] = official_value * detail["Meta KG"] / total_kg
    detail["Fonte Meta KG"] = "Rel.044 Comercial - Analítico Metas"
    detail["Fonte Meta R$"] = "Rel.045 Comercial - Indicador R$ Meta Venda"
    detail["Metodologia R$"] = "Total oficial alocado proporcionalmente à meta de KG"
    return detail[TARGET_COLUMNS].sort_values(["Competência", "Vendedor", "Grupo Produto"])


def merge_target_history(existing, current):
    """Substitui as competências consultadas e preserva as demais competências."""
    current = current.copy()
    current = normalize_dimensions(current)
    current["Grupo Produto"] = current["Grupo Produto"].map(normalize_product_group)
    if existing is None or existing.empty:
        return current
    old = existing.copy()
    old = normalize_dimensions(old)
    old["Competência"] = pd.to_datetime(old["Competência"], errors="coerce").dt.to_period("M").dt.start_time
    old["Grupo Produto"] = old["Grupo Produto"].map(normalize_product_group)
    keys = current[["Competência"]].drop_duplicates()["Competência"]
    old = old[~old["Competência"].isin(keys)]
    combined = pd.concat([old[TARGET_COLUMNS], current[TARGET_COLUMNS]], ignore_index=True)
    aggregations = {"Meta KG": "sum", "Meta R$": "sum"}
    aggregations.update({column: "first" for column in TARGET_COLUMNS[5:]})
    return combined.groupby(
        ["Competência", "Vendedor", "Grupo Produto"], as_index=False, dropna=False
    ).agg(aggregations).sort_values(["Competência", "Vendedor", "Grupo Produto"])


def target_scope(targets, start_date, end_date, sellers=None, groups=None):
    """Aplica período e escopo comercial sem multiplicar a meta."""
    if targets is None or targets.empty:
        return pd.DataFrame(columns=TARGET_COLUMNS)
    scoped = targets.copy()
    scoped = normalize_dimensions(scoped)
    scoped["Grupo Produto"] = scoped["Grupo Produto"].map(normalize_product_group)
    scoped["Competência"] = pd.to_datetime(scoped["Competência"], errors="coerce").dt.to_period("M").dt.start_time
    first = pd.Timestamp(start_date).to_period("M").start_time
    last = pd.Timestamp(end_date).to_period("M").start_time
    scoped = scoped[scoped["Competência"].between(first, last)]
    if sellers:
        normalized_sellers = {normalize_seller(seller) for seller in sellers}
        scoped = scoped[scoped["Vendedor"].astype(str).isin(normalized_sellers)]
    if groups:
        normalized_groups = {normalize_product_group(group) for group in groups}
        scoped = scoped[scoped["Grupo Produto"].isin(normalized_groups)]
    return scoped


def allocate_target(targets, history, dimension):
    """Aloca vendedor×grupo para cliente/SKU pelo peso faturado nos 3 meses anteriores."""
    if targets.empty:
        return pd.DataFrame(), {"Meta R$": 0.0, "Meta KG": 0.0}
    targets = normalize_dimensions(targets)
    targets["Grupo Produto"] = targets["Grupo Produto"].map(normalize_product_group)
    history = normalize_dimensions(history)
    if "Data" in history:
        history["Data"] = pd.to_datetime(history["Data"], errors="coerce")
    if "Grupo Produto" in history:
        history["Grupo Produto"] = history["Grupo Produto"].map(normalize_product_group)
    if dimension in ("Vendedor", "Grupo Produto"):
        return targets.groupby(dimension, as_index=False)[["Meta R$", "Meta KG"]].sum(), {"Meta R$": 0.0, "Meta KG": 0.0}
    if dimension not in history and dimension not in targets:
        return pd.DataFrame(), {"Meta R$": float(targets["Meta R$"].sum()), "Meta KG": float(targets["Meta KG"].sum())}

    allocations = []
    unallocated = {"Meta R$": 0.0, "Meta KG": 0.0}
    if dimension in targets.columns:
        explicit = targets[targets[dimension].fillna("").astype(str).str.strip().ne("")]
        if not explicit.empty:
            allocations.append(explicit.groupby(dimension, dropna=False, as_index=False)[["Meta R$", "Meta KG"]].sum())
        targets = targets[targets[dimension].fillna("").astype(str).str.strip().eq("")]
    if targets.empty:
        if not allocations:
            return pd.DataFrame(columns=[dimension, "Meta R$", "Meta KG"]), unallocated
        combined = pd.concat(allocations, ignore_index=True).groupby(dimension, dropna=False, as_index=False)[["Meta R$", "Meta KG"]].sum()
        return combined.sort_values("Meta R$", ascending=False), unallocated
    if dimension not in history:
        return pd.DataFrame(columns=[dimension, "Meta R$", "Meta KG"]), {
            "Meta R$": float(targets["Meta R$"].sum()), "Meta KG": float(targets["Meta KG"].sum())
        }
    for competence, monthly_target in targets.groupby("Competência"):
        # Três meses-calendário completos imediatamente anteriores à competência.
        start = competence - pd.DateOffset(months=3)
        end = competence - pd.Timedelta(days=1)
        base = history[(history["Data"] >= start) & (history["Data"] <= end)].copy()
        for (seller, group), cell in monthly_target.groupby(["Vendedor", "Grupo Produto"]):
            cell = cell[["Meta R$", "Meta KG"]].sum()
            reference = base[(base["Vendedor"].astype(str) == str(seller)) & (base["Grupo Produto"].astype(str) == str(group))]
            if reference.empty:
                unallocated["Meta R$"] += float(cell["Meta R$"])
                unallocated["Meta KG"] += float(cell["Meta KG"])
                continue
            weights = reference.groupby(dimension, dropna=False).agg(
                _weight=("Peso", lambda values: values.clip(lower=0).sum()),
            ).reset_index()
            total = float(weights["_weight"].sum())
            for metric in ("Meta R$", "Meta KG"):
                if total <= 0:
                    unallocated[metric] += float(cell[metric])
                    weights[metric] = 0.0
                else:
                    weights[metric] = float(cell[metric]) * weights["_weight"] / total
            allocations.append(weights[[dimension, "Meta R$", "Meta KG"]])
    if not allocations:
        return pd.DataFrame(columns=[dimension, "Meta R$", "Meta KG"]), unallocated
    result = pd.concat(allocations, ignore_index=True).groupby(dimension, dropna=False, as_index=False)[["Meta R$", "Meta KG"]].sum()
    return result.sort_values("Meta R$", ascending=False), unallocated
