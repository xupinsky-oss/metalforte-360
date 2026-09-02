"""Leitura e gravação da base em um bucket privado do Supabase Storage."""

import json
import os
from pathlib import Path
from urllib.parse import quote

import requests


def _settings():
    base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    api_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    bucket = os.getenv("SUPABASE_BUCKET", "metalforte-private")
    object_path = os.getenv("SUPABASE_DATA_PATH", "bases/metalforte_base.csv.gz")
    if not base_url or not api_key:
        return None
    return base_url, api_key, bucket, object_path


def is_configured():
    return _settings() is not None


def _object_url(path=None):
    base_url, _, bucket, default_path = _settings()
    object_name = path or default_path
    return f"{base_url}/storage/v1/object/{quote(bucket)}/{quote(object_name, safe='/')}"


def _headers(content_type=None):
    _, api_key, _, _ = _settings()
    headers = {"apikey": api_key, "Authorization": f"Bearer {api_key}"}
    if content_type:
        headers.update({"Content-Type": content_type, "x-upsert": "true"})
    return headers


def download_bytes(timeout=120):
    if not is_configured():
        raise RuntimeError("Supabase não configurado.")
    response = requests.get(_object_url(), headers=_headers(), timeout=timeout)
    response.raise_for_status()
    return response.content


def upload_file(local_path, timeout=180):
    if not is_configured():
        return False
    with Path(local_path).open("rb") as source:
        response = requests.post(_object_url(), headers=_headers("application/gzip"), data=source, timeout=timeout)
    response.raise_for_status()
    return True


def upload_status(status, timeout=30):
    if not is_configured():
        return False
    _, _, _, object_path = _settings()
    status_path = str(Path(object_path).with_name("status.json")).replace("\\", "/")
    payload = json.dumps(status, ensure_ascii=False).encode("utf-8")
    response = requests.post(_object_url(status_path), headers=_headers("application/json; charset=utf-8"), data=payload, timeout=timeout)
    response.raise_for_status()
    return True
