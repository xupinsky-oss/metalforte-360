"""Completa margens e clientes por SKU no resumo já publicado, sem nova coleta."""
import gzip
import json
import math
import os
from datetime import datetime, timezone

import pandas as pd

from gerar_dashboard_web import _monthly_sales_payload
from src.cloud_storage import download_bytes, upload_bytes
from src.data import load_data


DASHBOARD_PATH = os.getenv("SUPABASE_DASHBOARD_PATH", "dashboard/command-center.json")


def sku_key(row):
    return tuple(str(row.get(field, "")) for field in ("mes", "vendedor", "grupo", "codigo", "produto"))


def main():
    original = download_bytes(object_path=DASHBOARD_PATH)
    compressed = original.startswith(b"\x1f\x8b")
    snapshot = json.loads(gzip.decompress(original) if compressed else original)
    existing = snapshot.get("mensal_skus")
    if not isinstance(existing, list) or not existing:
        raise RuntimeError("Resumo publicado sem linhas de SKU; atualização interrompida.")

    sales = load_data()
    last_date = pd.to_datetime(sales["Data"], errors="coerce").max().normalize()
    snapshot_date = pd.Timestamp(snapshot["periodo"]["fim"]).normalize()
    if pd.isna(last_date) or last_date != snapshot_date:
        raise RuntimeError("A data da base comercial difere da data do resumo publicado.")

    months = max(1, (last_date.year - 2024) * 12 + last_date.month)
    _, calculated = _monthly_sales_payload(sales, last_date, months=months)
    by_key = {sku_key(row): row for row in calculated}
    old_keys = {sku_key(row) for row in existing}
    if len(by_key) != len(calculated) or len(old_keys) != len(existing) or old_keys != set(by_key):
        raise RuntimeError("As chaves de SKU da base e do resumo não coincidem; nenhum dado foi alterado.")

    for row in existing:
        source = by_key[sku_key(row)]
        for field in ("faturamento", "peso"):
            if not math.isclose(float(row[field]), float(source[field]), rel_tol=1e-8, abs_tol=0.02):
                raise RuntimeError(f"Total de {field} divergente em um SKU; nenhum dado foi alterado.")
        row["margem"] = source["margem"]
        row["clientes_ids"] = source["clientes_ids"]

    now = datetime.now(timezone.utc)
    snapshot["detalhe_sku_atualizado_em"] = now.isoformat()
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if compressed:
        payload = gzip.compress(payload, mtime=0)
    backup = f"dashboard/backups/command-center-{now:%Y%m%dT%H%M%SZ}.json"
    if not upload_bytes(original, backup, "application/json; charset=utf-8", timeout=120):
        raise RuntimeError("Não foi possível criar cópia do resumo anterior.")
    if not upload_bytes(payload, DASHBOARD_PATH, "application/json; charset=utf-8", timeout=120):
        raise RuntimeError("Não foi possível publicar o resumo com detalhe de SKU.")
    print(f"Resumo atualizado com margem e clientes em {len(existing)} linhas de SKU.")


if __name__ == "__main__":
    main()
