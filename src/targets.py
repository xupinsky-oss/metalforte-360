"""Normalização, conciliação e alocação auditável das metas comerciais."""

from __future__ import annotations

import os
import re
import unicodedata

import pandas as pd


TARGET_COLUMNS = [
    "Competência", "Vendedor", "Grupo Produto", "Meta KG", "Meta R$",
    "Fonte Meta KG", "Fonte Meta R$", "Metodologia R$",
]


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
        "Grupo Produto": meta_kg[group].astype("string").str.strip(),
        "Meta KG": _number(meta_kg[monthly]),
    }).dropna(subset=["Vendedor", "Grupo Produto", "Meta KG"])
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
    if existing is None or existing.empty:
        return current.copy()
    old = existing.copy()
    old["Competência"] = pd.to_datetime(old["Competência"], errors="coerce").dt.to_period("M").dt.start_time
    keys = current[["Competência"]].drop_duplicates()["Competência"]
    old = old[~old["Competência"].isin(keys)]
    return pd.concat([old[TARGET_COLUMNS], current[TARGET_COLUMNS]], ignore_index=True).sort_values(
        ["Competência", "Vendedor", "Grupo Produto"]
    )


def target_scope(targets, start_date, end_date, sellers=None, groups=None):
    """Aplica período e escopo comercial sem multiplicar a meta."""
    if targets is None or targets.empty:
        return pd.DataFrame(columns=TARGET_COLUMNS)
    scoped = targets.copy()
    scoped["Competência"] = pd.to_datetime(scoped["Competência"], errors="coerce").dt.to_period("M").dt.start_time
    first = pd.Timestamp(start_date).to_period("M").start_time
    last = pd.Timestamp(end_date).to_period("M").start_time
    scoped = scoped[scoped["Competência"].between(first, last)]
    if sellers:
        scoped = scoped[scoped["Vendedor"].astype(str).isin(set(map(str, sellers)))]
    if groups:
        scoped = scoped[scoped["Grupo Produto"].astype(str).isin(set(map(str, groups)))]
    return scoped


def allocate_target(targets, history, dimension):
    """Aloca vendedor×grupo para cliente/SKU pelas participações dos 12 meses anteriores."""
    if targets.empty:
        return pd.DataFrame(), {"Meta R$": 0.0, "Meta KG": 0.0}
    if dimension in ("Vendedor", "Grupo Produto"):
        return targets.groupby(dimension, as_index=False)[["Meta R$", "Meta KG"]].sum(), {"Meta R$": 0.0, "Meta KG": 0.0}
    if dimension not in history:
        return pd.DataFrame(), {"Meta R$": float(targets["Meta R$"].sum()), "Meta KG": float(targets["Meta KG"].sum())}

    allocations = []
    unallocated = {"Meta R$": 0.0, "Meta KG": 0.0}
    for competence, monthly_target in targets.groupby("Competência"):
        start = competence - pd.DateOffset(months=12)
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
                _revenue=("Faturamento", lambda values: values.clip(lower=0).sum()),
                _weight=("Peso", lambda values: values.clip(lower=0).sum()),
            ).reset_index()
            for metric, basis in (("Meta R$", "_revenue"), ("Meta KG", "_weight")):
                total = float(weights[basis].sum())
                if total <= 0:
                    unallocated[metric] += float(cell[metric])
                    weights[metric] = 0.0
                else:
                    weights[metric] = float(cell[metric]) * weights[basis] / total
            allocations.append(weights[[dimension, "Meta R$", "Meta KG"]])
    if not allocations:
        return pd.DataFrame(columns=[dimension, "Meta R$", "Meta KG"]), unallocated
    result = pd.concat(allocations, ignore_index=True).groupby(dimension, dropna=False, as_index=False)[["Meta R$", "Meta KG"]].sum()
    return result.sort_values("Meta R$", ascending=False), unallocated
