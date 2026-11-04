"""Local, read-only monitor for the METALFORTE 360 data pipeline.

Run with Python 3.12+: python monitor/server.py
The HTTP server binds only to loopback. Credentials are read server-side and
are never returned to the browser.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MONITOR = Path(__file__).resolve().parent
HOST, PORT = "127.0.0.1", int(os.getenv("METALFORTE_MONITOR_PORT", "8765"))
REPO = os.getenv("GITHUB_REPOSITORY", "xupinsky-oss/metalforte-360")
BRANCH = os.getenv("GITHUB_BRANCH", "main")
APP_URL = os.getenv("STREAMLIT_APP_URL", "https://metalforte-360.streamlit.app/").rstrip("/")
TZ = ZoneInfo("America/Sao_Paulo")
API = "https://api.github.com"
WORKFLOW = "atualizar-base.yml"
_STATE_CACHE = {"at": None, "data": None}


def load_settings():
    """Load optional local config without displaying or returning secrets."""
    for file in (ROOT / ".env", MONITOR / ".env.monitor"):
        if file.exists():
            for line in file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    secret_file = ROOT / ".streamlit" / "secrets.toml"
    if secret_file.exists():
        try:
            values = tomllib.loads(secret_file.read_text(encoding="utf-8"))
            for key in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_BUCKET", "GITHUB_TOKEN"):
                if values.get(key):
                    os.environ.setdefault(key, str(values[key]))
        except (OSError, tomllib.TOMLDecodeError):
            pass


def utc_parse(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def iso_local(value):
    parsed = utc_parse(value)
    return parsed.astimezone(TZ).isoformat() if parsed else None


def github_token():
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        return token
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL, timeout=5).strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def http_json(url, headers=None, timeout=10):
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "metalforte360-monitor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def github_request(path, token, raw=False, timeout=12):
    headers = {"User-Agent": "metalforte360-monitor", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(API + path, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        return body if raw else json.loads(body.decode("utf-8"))


def next_window(last_success):
    now = datetime.now(TZ)
    # Workflow offers :17 and :47 attempts, gated to at most one successful
    # production load per 55 minutes. This is a next attempt window, not SLA.
    candidates = []
    for delta in range(0, 4):
        date = (now + timedelta(days=delta)).date()
        for minute in (17, 47):
            candidate = datetime(date.year, date.month, date.day, now.hour if delta == 0 else 0, minute, tzinfo=TZ)
            if delta:
                candidate = datetime(date.year, date.month, date.day, 0, minute, tzinfo=TZ)
            if candidate > now and (not last_success or (candidate.astimezone(timezone.utc) - last_success).total_seconds() >= 3300):
                candidates.append(candidate)
        if delta == 0:
            for hour in range(now.hour + 1, 24):
                for minute in (17, 47):
                    candidate = datetime(date.year, date.month, date.day, hour, minute, tzinfo=TZ)
                    if not last_success or (candidate.astimezone(timezone.utc) - last_success).total_seconds() >= 3300:
                        candidates.append(candidate)
    for delta in range(1, 8):
        date = (now + timedelta(days=delta)).date()
        for hour in range(24):
            for minute in (17, 47):
                candidate = datetime(date.year, date.month, date.day, hour, minute, tzinfo=TZ)
                if not last_success or (candidate.astimezone(timezone.utc) - last_success).total_seconds() >= 3300:
                    candidates.append(candidate)
                    break
            if candidates and candidates[-1].date() == date:
                break
        if candidates:
            break
    return candidates[0].isoformat() if candidates else None


def clean_telemetry(state):
    if not isinstance(state, dict):
        return {}
    steps = []
    for step in state.get("steps", []) if isinstance(state.get("steps"), list) else []:
        if isinstance(step, dict):
            steps.append({"name": str(step.get("name", "Etapa"))[:100], "status": str(step.get("status", "unknown"))[:20],
                          "message": str(step.get("message", ""))[:200], "at": iso_local(step.get("at"))})
    events = []
    for event in state.get("events", []) if isinstance(state.get("events"), list) else []:
        if isinstance(event, dict):
            events.append({"level": str(event.get("level", "info"))[:12], "message": str(event.get("message", ""))[:200], "at": iso_local(event.get("at"))})
    return {"id": str(state.get("id", ""))[:80], "status": str(state.get("status", "unknown"))[:20],
            "source": str(state.get("source", ""))[:30], "updated_at": iso_local(state.get("updated_at")),
            "started_at": iso_local(state.get("started_at")), "steps": steps, "events": events}


def supabase_json(object_path):
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    bucket = os.getenv("SUPABASE_BUCKET", "metalforte-private")
    if not base or not key:
        raise RuntimeError("Supabase não configurado neste computador.")
    path = urllib.parse.quote(object_path, safe="/")
    url = f"{base}/storage/v1/object/{urllib.parse.quote(bucket)}/{path}"
    req = urllib.request.Request(url, headers={"apikey": key, "Authorization": f"Bearer {key}", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Supabase respondeu HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("Não foi possível consultar o Supabase") from None


def public_streamlit_version():
    try:
        req = urllib.request.Request(APP_URL + "/_stcore/health", headers={"User-Agent": "METALFORTE-360-monitor"})
        with urllib.request.urlopen(req, timeout=8) as response:
            return {"ok": 200 <= response.status < 300, "http": response.status}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "http": exc.code}
    except (urllib.error.URLError, TimeoutError):
        return {"ok": False, "http": None}


def get_state():
    cached_at = _STATE_CACHE.get("at")
    if cached_at and (datetime.now(timezone.utc) - cached_at).total_seconds() < 45:
        return _STATE_CACHE["data"]
    load_settings()
    now = datetime.now(TZ)
    token = github_token()
    data = {"generated_at": now.isoformat(), "repository": REPO, "branch": BRANCH, "app_url": APP_URL,
            "schedule": "Tentativas :17 e :47 (America/Sao_Paulo); limite mínimo de 55 min após sucesso", "sources": {}, "errors": []}
    version = None
    version_commit = None
    runs, workflow_py = [], None
    if token:
        try:
            encoded_repo = urllib.parse.quote(REPO, safe="/")
            runs_data = github_request(f"/repos/{encoded_repo}/actions/workflows/{WORKFLOW}/runs?per_page=20", token)
            runs = runs_data.get("workflow_runs", [])
            content = github_request(f"/repos/{encoded_repo}/contents/src/version.py?ref={urllib.parse.quote(BRANCH)}", token)
            import base64
            version_text = base64.b64decode(content["content"]).decode("utf-8")
            match = re.search(r'APP_RELEASE\s*=\s*["\']([^"\']+)', version_text)
            version = match.group(1) if match else None
            head_commit = github_request(f"/repos/{encoded_repo}/commits/{urllib.parse.quote(BRANCH)}", token)
            version_commit = head_commit.get("sha", "")[:7]
            workflow_content = github_request(f"/repos/{encoded_repo}/contents/.github/workflows/{WORKFLOW}?ref={urllib.parse.quote(BRANCH)}", token)
            workflow_text = base64.b64decode(workflow_content["content"]).decode("utf-8")
            match = re.search(r"python-version:\s*[\"']?([0-9.]+)", workflow_text)
            workflow_py = match.group(1) if match else "não declarado"
            latest = runs[0] if runs else None
            success = next((r for r in runs if r.get("conclusion") == "success"), None)
            data["sources"]["github"] = {"status": "online", "version": f"{version or 'não identificada'} · {version_commit or 'sem SHA'}",
                "updated_at": iso_local(latest.get("updated_at")) if latest else None,
                "last_run": {"id": latest.get("id"), "name": latest.get("name"), "status": latest.get("status"), "conclusion": latest.get("conclusion"),
                             "event": latest.get("event"), "url": latest.get("html_url"), "created_at": iso_local(latest.get("created_at")), "updated_at": iso_local(latest.get("updated_at"))} if latest else None,
                "last_success": iso_local(success.get("updated_at")) if success else None,
                "next_update": next_window(utc_parse(success.get("updated_at")) if success else None), "python": workflow_py,
                "runs": [{"id": r.get("id"), "status": r.get("status"), "conclusion": r.get("conclusion"), "url": r.get("html_url"),
                          "updated_at": iso_local(r.get("updated_at")), "name": r.get("name")} for r in runs[:10]]}
        except Exception as exc:
            data["sources"]["github"] = {"status": "error", "message": str(exc)[:180], "runs": []}
    else:
        data["sources"]["github"] = {"status": "needs_setup", "message": "Conecte o GitHub CLI (gh auth login) ou defina GITHUB_TOKEN localmente.", "runs": []}

    try:
        telemetry_raw = supabase_json("etl/latest.json")
        data_path = os.getenv("SUPABASE_DATA_PATH", "bases/metalforte_base.csv.gz")
        status_path = str(PurePosixPath(data_path).with_name("status.json"))
        base_status = supabase_json(status_path)
        telemetry = clean_telemetry(telemetry_raw)
        base_stamp = (base_status or {}).get("atualizado_em") if isinstance(base_status, dict) else None
        data["sources"]["supabase"] = {"status": "online" if telemetry_raw is not None or base_status is not None else "no_data",
            "version": "Bucket privado · telemetria sanitizada", "updated_at": iso_local(base_stamp) or telemetry.get("updated_at"),
            "base_updated_at": iso_local(base_stamp), "telemetry": telemetry, "bucket": os.getenv("SUPABASE_BUCKET", "metalforte-private")}
        data["sources"]["gooddata"] = {"status": "online" if telemetry else "no_data", "version": "Relatório fonte 11078478 · sem versão própria exposta",
            "updated_at": next((s["at"] for s in telemetry.get("steps", []) if s["name"].startswith("Coleta TOTVS") and s["at"]), telemetry.get("updated_at")),
            "details": "Acompanha a etapa de extração publicada no estado ETL; a fonte não fornece uma versão de relatório pela integração atual."}
        if telemetry:
            failures = [e for e in telemetry.get("events", []) if e.get("level") == "error"]
            failures += [{"level": "error", "message": f"{s['name']}: {s['message']}", "at": s["at"]} for s in telemetry.get("steps", []) if s.get("status") == "failed"]
            data["errors"].extend(failures[-12:])
    except Exception as exc:
        configured = bool(os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")))
        message = str(exc)[:180]
        if configured:
            data["sources"]["supabase"] = {"status": "error", "message": message}
            data["sources"]["gooddata"] = {"status": "unknown", "message": "A última extração está registrada no Supabase, ainda sem conexão."}
        else:
            data["sources"]["supabase"] = {"status": "needs_setup", "message": "Adicione a URL e a chave privada local do Supabase ao arquivo monitor/.env.monitor."}
            data["sources"]["gooddata"] = {"status": "needs_setup", "message": "A etapa de extração vem da telemetria privada do Supabase."}

    data["sources"]["python"] = {"status": "online" if workflow_py else ("needs_setup" if not token else "unknown"),
        "version": f"Python {workflow_py} no workflow" if workflow_py else "Versão do runtime não lida", "updated_at": iso_local(runs[0].get("updated_at")) if runs else None,
        "details": "Versão declarada no workflow de ETL; código/release consultados na branch configurada."}
    streamlit = public_streamlit_version()
    data["sources"]["streamlit"] = {"status": "online" if streamlit["ok"] else "offline", "version": f"Código esperado {version}" if version else "Versão implantada não verificável publicamente",
        "updated_at": iso_local(runs[0].get("updated_at")) if runs else None, "health_http": streamlit["http"], "url": APP_URL,
        "details": "A verificação pública confirma apenas se o serviço responde; a versão mostrada dentro do app exige autenticação."}

    for run in runs:
        if run.get("conclusion") == "failure":
            data["errors"].append({"level": "error", "message": f"GitHub Actions: execução #{run.get('run_number')} falhou ({run.get('name', 'ETL')}).", "at": iso_local(run.get("updated_at")), "url": run.get("html_url")})
    data["errors"] = data["errors"][-20:]
    _STATE_CACHE.update(at=datetime.now(timezone.utc), data=data)
    return data


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            try:
                payload = json.dumps(get_state(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
            except Exception as exc:
                payload = json.dumps({"error": str(exc)[:180]}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path in ("/", "/index.html"):
            content = (MONITOR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        # Avoid writing request content or credentials to stdout.
        print("[monitor] " + (fmt % args))


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Painel local METALFORTE 360 Monitor: http://{HOST}:{PORT}")
    print("Este servidor aceita conexões somente deste computador; credenciais ficam no processo local.")
    webbrowser.open(f"http://{HOST}:{PORT}")
    server.serve_forever()
