"""Gera resumos privados por vendedor a partir do resumo comercial publicado."""
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cloud_storage import download_bytes, upload_bytes

DASHBOARD_PATH = os.getenv("SUPABASE_DASHBOARD_PATH", "dashboard/command-center.json")
SELLER_PREFIX = os.getenv("SUPABASE_SELLER_PREFIX", "dashboard/sellers")


def scoped_payload(snapshot, seller):
    cuts = [row for row in snapshot.get("mensal_recortes", []) if row.get("vendedor") == seller]
    skus = [row for row in snapshot.get("mensal_skus", []) if row.get("vendedor") == seller]
    orders = [row for row in snapshot.get("pedidos_recortes", []) if row.get("vendedor") == seller]
    order_details = [row for row in snapshot.get("pedidos_detalhe", []) if row.get("vendedor") == seller]
    portfolio = dict(snapshot.get("clientes_carteira") or {})
    portfolio["clientes"] = [row for row in portfolio.get("clientes", []) if row.get("Vendedor") == seller]

    def filtered_portfolio(item):
        result = dict(item)
        customers = [row for row in item.get("clientes", []) if row.get("Vendedor") == seller]
        result["clientes"] = customers
        result["contagens"] = {
            "total": len(customers),
            "novos": sum(row.get("Status") == "Novo" for row in customers),
            "ativos": sum(row.get("Status") == "Ativo" for row in customers),
            "em_risco": sum(row.get("Status") == "Em risco" for row in customers),
            "inativos": sum(row.get("Status") == "Inativo" for row in customers),
        }
        return result

    portfolio = filtered_portfolio(portfolio)
    customer_months = [filtered_portfolio(row) for row in snapshot.get("clientes_mensais", [])]
    months = {}
    for row in cuts:
        month = months.setdefault(row["mes"], {"mes": row["mes"], "faturamento": 0, "peso": 0, "margem": 0, "clientes_ids": set(), "produtos_ids": set()})
        month["faturamento"] += float(row.get("faturamento") or 0)
        month["peso"] += float(row.get("peso") or 0)
        month["margem"] += float(row.get("margem") or 0)
        month["clientes_ids"].update(row.get("clientes_ids") or [])
        month["produtos_ids"].update(row.get("produtos_ids") or [])
    monthly = []
    for month in sorted(months.values(), key=lambda item: item["mes"]):
        month["margem_pct"] = month["margem"] / month["faturamento"] if month["faturamento"] else 0
        month["clientes_ids"] = sorted(month["clientes_ids"])
        month["produtos_ids"] = sorted(month["produtos_ids"])
        monthly.append(month)
    revenue = sum(row["faturamento"] for row in monthly)
    weight = sum(row["peso"] for row in monthly)
    margin = sum(row["margem"] for row in monthly)

    def panel(dimension):
        groups = {}
        for row in cuts:
            name = str(row.get(dimension) or "Não mapeado")
            item = groups.setdefault(name, {"nome": name, "faturamento": 0, "peso": 0, "margem": 0, "clientes_ids": set()})
            item["faturamento"] += float(row.get("faturamento") or 0)
            item["peso"] += float(row.get("peso") or 0)
            item["margem"] += float(row.get("margem") or 0)
            item["clientes_ids"].update(row.get("clientes_ids") or [])
        result = []
        for item in groups.values():
            result.append({
                "nome": item["nome"], "faturamento": item["faturamento"], "peso": item["peso"],
                "margem_pct": item["margem"] / item["faturamento"] if item["faturamento"] else 0,
                "participacao_pct": item["faturamento"] / revenue if revenue else 0,
                "clientes": len(item["clientes_ids"]),
            })
        return sorted(result, key=lambda item: item["faturamento"], reverse=True)

    return {
        "periodo": snapshot.get("periodo"),
        "atualizado_em": snapshot.get("atualizado_em"),
        "mensal": monthly,
        "mensal_recortes": cuts,
        "mensal_skus": skus,
        "pedidos_recortes": orders,
        "pedidos_detalhe": order_details,
        "clientes_carteira": portfolio,
        "clientes_mensais": customer_months,
        "base_vendedores": [row for row in snapshot.get("base_vendedores", []) if row.get("nome") == seller],
        "paineis": {"cidades": panel("cidade"), "produtos": panel("grupo"), "segmentos": panel("segmento"), "vendedores": panel("vendedor")},
        "overview": {
            "faturamento": revenue, "peso": weight, "margem": margin,
            "margem_pct": margin / revenue if revenue else 0,
            "preco_medio_kg": revenue / weight if weight else 0,
            "clientes": len(set().union(*(row["clientes_ids"] for row in monthly))) if monthly else 0,
            "produtos": len(set().union(*(row["produtos_ids"] for row in monthly))) if monthly else 0,
            "variacao_faturamento_pct": 0, "delta_margem_pp": 0,
        },
        "metas_e_pedidos": {
            "pedidos_liberados_valor": sum(float(row.get("pedidos_liberados_valor") or 0) for row in orders),
            "pedidos_liberados_peso": sum(float(row.get("pedidos_liberados_peso") or 0) for row in orders),
        },
    }


def main():
    original = download_bytes(object_path=DASHBOARD_PATH)
    snapshot = json.loads(gzip.decompress(original) if original.startswith(bytes([31, 139])) else original)
    sellers = sorted({str(row.get("vendedor") or "").strip() for row in snapshot.get("mensal_recortes", []) if row.get("vendedor")})
    if not sellers:
        raise RuntimeError("Resumo sem recortes por vendedor; nenhum arquivo foi publicado.")
    written = 0
    for seller in sellers:
        payload = scoped_payload(snapshot, seller)
        path = f"{SELLER_PREFIX}/{hashlib.sha256(seller.encode('utf-8')).hexdigest()}.json"
        data = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0)
        if not upload_bytes(data, path, "application/json", timeout=120):
            raise RuntimeError(f"Falha ao publicar resumo do vendedor {seller}.")
        written += 1
    print(f"{written} resumos por vendedor publicados.")


if __name__ == "__main__":
    main()
