"""Padronização de dimensões textuais compartilhadas pelo painel e pelo ETL."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd


_UF_BY_IBGE = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}
_PARTICLES = {"da", "das", "de", "do", "dos", "e"}
_SENTINELS = {
    "naomapeado": "Não mapeado",
    "naoinformado": "Não informado",
    "naoclassificado": "Não classificado",
}
_CITY_REFERENCE = Path(__file__).resolve().parents[1] / "municipios_centroides.csv"


def _text(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _key(value) -> str:
    text = unicodedata.normalize("NFKD", _text(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text)


def _title_pt(value: str) -> str:
    words = value.casefold().split(" ")
    return " ".join(
        word if index and word in _PARTICLES else word[:1].upper() + word[1:]
        for index, word in enumerate(words)
    )


def normalize_seller(value) -> str:
    """Gera rótulo estável: ignora caixa, acentos e espaços excedentes."""
    text = _text(value)
    if not text:
        return text
    if _key(text) in _SENTINELS:
        return _SENTINELS[_key(text)]
    # Vendedor não possui uma chave nominal oficial em todas as fontes. O rótulo
    # sem acentos torna a comparação estável entre GoodData, metas e funil.
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return _title_pt(re.sub(r"\s+", " ", plain).strip())


@lru_cache(maxsize=1)
def _official_cities():
    if not _CITY_REFERENCE.exists():
        return {}, {}
    cities = pd.read_csv(
        _CITY_REFERENCE,
        usecols=["nome", "codigo_uf"],
        dtype={"nome": "string", "codigo_uf": "Int64"},
    )
    by_state = {}
    by_name = {}
    for row in cities.itertuples(index=False):
        name = _text(row.nome)
        uf = _UF_BY_IBGE.get(int(row.codigo_uf)) if pd.notna(row.codigo_uf) else None
        name_key = _key(name)
        if not name_key:
            continue
        if uf:
            by_state[(uf, name_key)] = name
        by_name.setdefault(name_key, set()).add(name)
    unique_names = {key: next(iter(names)) for key, names in by_name.items() if len(names) == 1}
    return by_state, unique_names


def normalize_city(value, uf=None) -> str:
    """Usa a grafia oficial do município via IBGE; corrige caixa como fallback."""
    text = _text(value)
    if not text:
        return text
    if _key(text) in _SENTINELS:
        return _SENTINELS[_key(text)]
    by_state, unique_names = _official_cities()
    name_key = _key(text)
    uf_key = _text(uf).upper()
    if uf_key and (uf_key, name_key) in by_state:
        return by_state[(uf_key, name_key)]
    if name_key in unique_names:
        return unique_names[name_key]
    return _title_pt(text)


def normalize_dimensions(frame: pd.DataFrame) -> pd.DataFrame:
    """Padroniza cidade e vendedor sem alterar o grão nem somar registros."""
    if frame is None or frame.empty:
        return frame
    result = frame.copy()
    if "Vendedor" in result:
        result["Vendedor"] = result["Vendedor"].map(normalize_seller).astype("string")
    if "Município" in result:
        uf = result["UF"] if "UF" in result else pd.Series("", index=result.index)
        result["Município"] = [normalize_city(city, state) for city, state in zip(result["Município"], uf)]
    return result
