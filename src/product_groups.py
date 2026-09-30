"""Nomenclatura canônica dos grupos de produtos da METALFORTE."""

from __future__ import annotations

import re
import unicodedata


# A numeração e os nomes seguem a matriz comercial de produtos publicada no app.
PRODUCT_GROUPS_BY_CODE = {
    "0002": "0002 Bobininha",
    "0003": "0003 Chapa",
    "0004": "0004 Corte e Dobra PE",
    "0007": "0007 Isotermicos",
    "0008": "0008 Laminado",
    "0009": "0009 Perfil",
    "0011": "0011 Serralheria",
    "0013": "0013 Telha",
    "0014": "0014 Tubos",
    "0021": "0021 EPI",
    "0022": "0022 Corte e Dobra SE",
    "0023": "0023 Metalforte Solucoes",
    "0025": "0025 PROMOCAO",
    "0028": "0028 Construcao Seca",
}


def _plain(value) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(character for character in text if not unicodedata.combining(character)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


_ALIASES = {
    "bobina": "0002",
    "bobininha": "0002",
    "chapa": "0003",
    "chapas": "0003",
    "corte dobra pe": "0004",
    "corte e dobra pe": "0004",
    "isotermico": "0007",
    "isotermicos": "0007",
    "laminado": "0008",
    "laminados": "0008",
    "perfil": "0009",
    "perfis": "0009",
    "serralheria": "0011",
    "telha": "0013",
    "telhas": "0013",
    "tubo": "0014",
    "tubos": "0014",
    "epi": "0021",
    "epis": "0021",
    "corte dobra se": "0022",
    "corte e dobra se": "0022",
    "metalforte solucoes": "0023",
    "solucoes metalforte": "0023",
    "promocao": "0025",
    "construcao seca": "0028",
    "construcao a seco": "0028",
}


def normalize_product_group(value) -> str:
    """Converte códigos e nomes legados no rótulo oficial usado pelo realizado."""
    original = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    if not original or original.lower() in {"nan", "none", "<na>"}:
        return "Não mapeado"

    # Quando o relatório fornece o código, ele é a chave mais confiável.
    code_match = re.match(r"^0*(\d{1,4})(?:\.0+)?(?:\D|$)", original)
    if code_match:
        code = code_match.group(1).zfill(4)
        if code in PRODUCT_GROUPS_BY_CODE:
            return PRODUCT_GROUPS_BY_CODE[code]

    key = _plain(original)
    if key in {"nao mapeado", "sem grupo"}:
        return "Não mapeado"
    tokens = [token for token in key.split() if token not in {"grupo", "produto", "prod"}]
    if tokens and tokens[0].isdigit():
        code = tokens.pop(0).zfill(4)
        if code in PRODUCT_GROUPS_BY_CODE:
            return PRODUCT_GROUPS_BY_CODE[code]
    alias_key = " ".join(tokens)
    code = _ALIASES.get(alias_key)
    if code:
        return PRODUCT_GROUPS_BY_CODE[code]

    # Nomes fora da matriz permanecem visíveis, mas deixam de se dividir por caixa.
    return original.upper()

