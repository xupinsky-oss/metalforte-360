"""Leitura e gravação da base em um bucket privado do Supabase Storage."""

import json
import os
import base64
from pathlib import Path
from urllib.parse import quote
from urllib.parse import urlparse

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


def download_status(timeout=30):
    """Retorna os metadados da última carga publicada junto com a base."""
    if not is_configured():
        return {}
    _, _, _, object_path = _settings()
    status_path = str(Path(object_path).with_name("status.json")).replace("\\", "/")
    response = requests.get(_object_url(status_path), headers=_headers(), timeout=timeout)
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    return response.json()


def upload_file(local_path, timeout=180):
    if not is_configured():
        return False
    source_path = Path(local_path)
    base_url, api_key, bucket, object_path = _settings()
    project_host = urlparse(base_url).hostname or ""
    project_ref = project_host.split(".", 1)[0]
    tus_url = f"https://{project_ref}.storage.supabase.co/storage/v1/upload/resumable"

    def encoded(value):
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    create_headers = {
        "Authorization": f"Bearer {api_key}",
        "apikey": api_key,
        "Tus-Resumable": "1.0.0",
        "Upload-Length": str(source_path.stat().st_size),
        "Upload-Metadata": ",".join(
            [
                f"bucketName {encoded(bucket)}",
                f"objectName {encoded(object_path)}",
                f"contentType {encoded('application/gzip')}",
                f"cacheControl {encoded('no-cache')}",
            ]
        ),
        "x-upsert": "true",
    }
    response = requests.post(tus_url, headers=create_headers, timeout=timeout)
    if response.status_code not in (201, 204):
        raise RuntimeError(
            f"Supabase não iniciou o upload ({response.status_code}): {response.text[:500]}"
        )

    upload_url = response.headers.get("Location")
    if not upload_url:
        raise RuntimeError("Supabase não retornou a URL do upload resumível.")
    if upload_url.startswith("/"):
        upload_url = f"https://{project_ref}.storage.supabase.co{upload_url}"

    offset = 0
    chunk_size = 6 * 1024 * 1024
    with source_path.open("rb") as source:
        while chunk := source.read(chunk_size):
            patch_headers = {
                "Authorization": f"Bearer {api_key}",
                "apikey": api_key,
                "Tus-Resumable": "1.0.0",
                "Upload-Offset": str(offset),
                "Content-Type": "application/offset+octet-stream",
            }
            response = requests.patch(
                upload_url, headers=patch_headers, data=chunk, timeout=timeout
            )
            if response.status_code != 204:
                raise RuntimeError(
                    f"Supabase interrompeu o upload ({response.status_code}): "
                    f"{response.text[:500]}"
                )
            offset = int(response.headers.get("Upload-Offset", offset + len(chunk)))
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
