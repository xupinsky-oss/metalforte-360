"""Publica telemetria sanitizada do ETL no bucket privado.

Não recebe nem registra cookies, senhas, tokens, dados brutos ou saídas das fontes.
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(".etl-status.json")
STEP_NAMES = [
    "Disparo solicitado", "Autorização e permissões", "Preparação do ambiente",
    "Coleta TOTVS / GoodData", "Validação da base", "Tratamento e normalização",
    "Publicação da base privada", "Geração de métricas e agregados",
    "Publicação do resumo", "Validação pós-carga", "Painel disponível",
]


def now():
    return datetime.now().astimezone().isoformat()


def clean(value, limit=240):
    return " ".join(str(value or "").split())[:limit]


def load_or_create(args):
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    stamp = now()
    return {
        "id": clean(args.request_id, 80), "status": "in_progress",
        "source": clean(args.source, 30), "environment": clean(args.environment, 20),
        "scope": clean(args.scope, 20), "requested_by": clean(args.requested_by, 120),
        "reason": clean(args.reason), "started_at": stamp, "updated_at": stamp,
        "steps": [{"name": name, "status": "pending", "message": "Aguardando", "at": None} for name in STEP_NAMES],
        "events": [],
    }


def publish(state):
    state["updated_at"] = now()
    payload = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"):
        from src.cloud_storage import upload_bytes
        upload_bytes(payload, f"etl/runs/{state['id']}.json", "application/json; charset=utf-8")
        upload_bytes(payload, "etl/latest.json", "application/json; charset=utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "step", "finish"])
    parser.add_argument("--request-id", default=os.getenv("ETL_REQUEST_ID", ""))
    parser.add_argument("--environment", default=os.getenv("ETL_ENVIRONMENT", "producao"))
    parser.add_argument("--scope", default=os.getenv("ETL_SCOPE", "full"))
    parser.add_argument("--requested-by", default=os.getenv("ETL_REQUESTED_BY", "github-actions"))
    parser.add_argument("--reason", default=os.getenv("ETL_REASON", "Execução agendada"))
    parser.add_argument("--source", default=os.getenv("ETL_SOURCE", "github_actions"))
    parser.add_argument("--index", type=int)
    parser.add_argument("--status", choices=["pending", "running", "completed", "failed"], default="completed")
    parser.add_argument("--message", default="Etapa atualizada")
    args = parser.parse_args()
    state = load_or_create(args)
    if args.command == "start":
        for index in (0, 1):
            state["steps"][index].update(status="completed", message="Execução autorizada", at=now())
        state["status"] = "in_progress"
    elif args.command == "step":
        if args.index is None or not 0 <= args.index < len(state["steps"]):
            raise SystemExit("Índice de etapa inválido.")
        state["steps"][args.index].update(status=args.status, message=clean(args.message), at=now())
        if args.status == "failed":
            state["status"] = "failure"
    else:
        state["status"] = "success" if args.status == "completed" else "failure"
    state["events"].append({"at": now(), "level": "error" if args.status == "failed" else "info", "message": clean(args.message)})
    state["events"] = state["events"][-60:]
    publish(state)


if __name__ == "__main__":
    main()
