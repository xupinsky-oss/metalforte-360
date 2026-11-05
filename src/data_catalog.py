"""Catálogo único das bases publicadas; arquivos locais são apenas desenvolvimento."""
import os
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "sales": ("SUPABASE_DATA_PATH", "metalforte_base.csv.gz"),
    "targets": ("SUPABASE_TARGET_XLSX_PATH", "metalforte_metas.xlsx"),
    "stock": ("SUPABASE_STOCK_PATH", "metalforte_estoque.csv.gz"),
    "flow": ("SUPABASE_FLOW_PATH", "metalforte_fluxo.csv.gz"),
    "orders": ("SUPABASE_ORDERS_ACTUAL_PATH", "metalforte_pedidos_realizado.csv.gz"),
    "depara": ("SUPABASE_DEPARA_PATH", "DE_PARA_METALFORTE360.xlsx"),
}

def object_path(dataset):
    variable, filename = DATASETS[dataset]
    configured = os.getenv(variable)
    if configured:
        return configured.replace("\\", "/")
    parent = PurePosixPath(os.getenv("SUPABASE_DATA_PATH", "bases/metalforte_base.csv.gz")).parent
    # O DE/PARA é uma referência corporativa, compartilhada entre ambientes.
    return str(PurePosixPath("bases") / filename) if dataset == "depara" else str(parent / filename)

def local_path(dataset):
    return ROOT / "data" / DATASETS[dataset][1]
