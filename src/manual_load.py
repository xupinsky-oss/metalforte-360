"""Carga manual dos relatórios exportados do GoodData.

O módulo não autentica no TOTVS. Ele lê os arquivos já baixados pelo usuário,
consolida a mesma base comercial do atualizador automático e, quando as
configurações locais estiverem presentes, publica o resultado no Storage.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from atualizar_gooddata import (
    ACTIVE,
    ACTIVE_FLOW,
    BACKUP,
    DATA,
    INDICATORS,
    RAW,
    build_flow_timeline,
    consolidate,
    extract_loss_reasons,
    parse_raw,
)
from src.cloud_storage import is_configured, upload_file, upload_status


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "CARGA_MANUAL"

# Estes são os relatórios que formam a base comercial já usada pelo painel.
# Os nomes são deliberadamente curtos para que o processo diário seja simples.
REQUIRED_REPORTS = {
    "faturamento": "Faturamento realizado",
    "margem": "Margem, custos e impostos",
    "clientes_pedidos": "Clientes e pedidos",
    "cliente_geo": "Cadastro geográfico de clientes",
    "cliente_classificacao": "Segmento e tipologia de clientes",
    "produto_classificacao": "Classificação de produtos",
    "preco_benchmark": "Benchmark de preço por grupo",
}

# Estes relatórios não impedem a carga comercial, mas atualizam o rastreio do
# funil quando forem disponibilizados no mesmo dia.
OPTIONAL_FLOW_REPORTS = {
    "fluxo_liberados_cif": "Pedidos liberados CIF com datas",
    "fluxo_liberados_fob": "Pedidos liberados FOB com datas",
    "op_sob_encomenda": "OP sob encomenda",
    "orcamentos_abertos_detalhe": "Orçamentos em aberto",
}
OPTIONAL_LOSS_REPORT = "perdas_por_motivo"
OPTIONAL_STOCK_REPORT = "estoque_produto"
ALLOWED_EXTENSIONS = {".csv", ".txt", ".zip"}


def prepare_input_folder() -> Path:
    """Cria a pasta de entrada e deixa o guia sempre disponível."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=True)
    return INPUT_DIR


def expected_filename(report_name: str) -> str:
    return f"{report_name}.csv"


def report_path(report_name: str) -> Path | None:
    """Localiza o arquivo por nome, aceitando CSV, TXT ou ZIP do GoodData."""
    prepare_input_folder()
    for extension in (".csv", ".txt", ".zip"):
        candidate = INPUT_DIR / f"{report_name}{extension}"
        if candidate.exists():
            return candidate
    return None


def _load_env_file() -> None:
    """Lê somente a configuração local; nunca imprime segredos na interface."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _read_report(report_name: str) -> pd.DataFrame:
    path = report_path(report_name)
    if path is None:
        raise FileNotFoundError(
            f"Arquivo ausente: {expected_filename(report_name)} em {INPUT_DIR}"
        )
    frame = parse_raw(path.read_bytes())
    if frame.empty:
        raise ValueError(f"O arquivo {path.name} não possui linhas de dados.")
    return frame


def folder_status() -> list[dict[str, object]]:
    """Retorna a situação de todos os relatórios esperados para a interface."""
    prepare_input_folder()
    items = []
    for name, label in {**REQUIRED_REPORTS, **OPTIONAL_FLOW_REPORTS}.items():
        path = report_path(name)
        items.append(
            {
                "Relatório": label,
                "Arquivo esperado": expected_filename(name),
                "Obrigatório": "Sim" if name in REQUIRED_REPORTS else "Não (funil)",
                "Situação": "Pronto" if path else "Ausente",
                "Arquivo encontrado": path.name if path else "—",
                "Modificado em": datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if path else "—",
            }
        )
    loss_path = report_path(OPTIONAL_LOSS_REPORT)
    items.append(
        {
            "Relatório": "Perdas por motivo",
            "Arquivo esperado": expected_filename(OPTIONAL_LOSS_REPORT),
            "Obrigatório": "Não (perdas)",
            "Situação": "Pronto" if loss_path else "Ausente",
            "Arquivo encontrado": loss_path.name if loss_path else "—",
            "Modificado em": datetime.fromtimestamp(loss_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if loss_path else "—",
        }
    )
    stock_path = report_path(OPTIONAL_STOCK_REPORT)
    items.append(
        {
            "Relatório": "Estoque por produto",
            "Arquivo esperado": expected_filename(OPTIONAL_STOCK_REPORT),
            "Obrigatório": "Não (estoque)",
            "Situação": "Pronto" if stock_path else "Ausente",
            "Arquivo encontrado": stock_path.name if stock_path else "—",
            "Modificado em": datetime.fromtimestamp(stock_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if stock_path else "—",
        }
    )
    return items


def save_upload(report_name: str, payload: bytes) -> Path:
    """Salva uma exportação do GoodData com o nome padrão do processo."""
    if report_name not in {*REQUIRED_REPORTS, *OPTIONAL_FLOW_REPORTS, OPTIONAL_LOSS_REPORT, OPTIONAL_STOCK_REPORT}:
        raise ValueError("Relatório desconhecido.")
    if not payload:
        raise ValueError("O arquivo enviado está vazio.")
    prepare_input_folder()
    destination = INPUT_DIR / expected_filename(report_name)
    destination.write_bytes(payload)
    return destination


def validate_manual_files() -> dict[str, object]:
    """Lê todos os arquivos obrigatórios antes de qualquer troca da base ativa."""
    missing = [name for name in REQUIRED_REPORTS if report_path(name) is None]
    if missing:
        names = ", ".join(expected_filename(name) for name in missing)
        raise ValueError(f"Faltam arquivos obrigatórios: {names}.")
    downloaded = {name: _read_report(name) for name in REQUIRED_REPORTS}
    return {
        "frames": downloaded,
        "rows_by_report": {name: len(frame) for name, frame in downloaded.items()},
    }


def _save_input_snapshot(stamp: str) -> None:
    """Mantém uma cópia de auditoria dos arquivos que originaram a carga."""
    for name in [*REQUIRED_REPORTS, *OPTIONAL_FLOW_REPORTS, OPTIONAL_LOSS_REPORT, OPTIONAL_STOCK_REPORT]:
        path = report_path(name)
        if path:
            shutil.copy2(path, RAW / f"manual_{name}_{stamp}{path.suffix}")


def run_manual_update(publish: bool = True) -> dict[str, object]:
    """Consolida, valida e opcionalmente publica a carga manual.

    A base local só é substituída depois de a consolidação e as validações de
    faturamento serem concluídas. Caso `publish` seja verdadeiro, a publicação
    no Storage ocorre antes de substituir a cópia local ativa.
    """
    _load_env_file()
    prepared = validate_manual_files()
    downloaded: dict[str, pd.DataFrame] = prepared["frames"]  # type: ignore[assignment]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _save_input_snapshot(stamp)

    base = consolidate(downloaded)
    if base.empty:
        raise ValueError("A consolidação não gerou linhas para a base comercial.")
    if base["Data"].notna().mean() < 0.99:
        raise ValueError("Cobertura de datas abaixo de 99%. A base não foi substituída.")

    source_total = pd.to_numeric(downloaded["faturamento"].iloc[:, 9], errors="coerce").sum()
    final_total = pd.to_numeric(base["Faturamento"], errors="coerce").sum()
    if source_total and abs(final_total / source_total - 1) > 0.0001:
        raise ValueError("O total de faturamento divergiu da exportação. A base não foi substituída.")

    temporary = DATA / "metalforte_base.manual.nova.csv.gz"
    base.to_csv(temporary, index=False, compression="gzip")
    flow_result: pd.DataFrame | None = None
    flow_temporary = DATA / "metalforte_fluxo.manual.novo.csv.gz"
    flow_frames = {
        name: _read_report(name)
        for name in OPTIONAL_FLOW_REPORTS
        if report_path(name) is not None
    }
    if flow_frames:
        flow_result = build_flow_timeline(flow_frames)
        if not flow_result.empty:
            flow_result.to_csv(flow_temporary, index=False, compression="gzip")

    if publish:
        if not is_configured():
            temporary.unlink(missing_ok=True)
            flow_temporary.unlink(missing_ok=True)
            raise RuntimeError(
                "A publicação online não está configurada neste computador. "
                "Preencha SUPABASE_URL e SUPABASE_SERVICE_KEY no arquivo .env local."
            )
        upload_file(temporary)
        if flow_result is not None and not flow_result.empty:
            upload_file(flow_temporary, object_path=os.getenv("SUPABASE_FLOW_PATH", "bases/metalforte_fluxo.csv.gz"))

    if ACTIVE.exists():
        shutil.copy2(ACTIVE, BACKUP / f"metalforte_base_{stamp}.csv.gz")
    temporary.replace(ACTIVE)
    if flow_result is not None and not flow_result.empty:
        if ACTIVE_FLOW.exists():
            shutil.copy2(ACTIVE_FLOW, BACKUP / f"metalforte_fluxo_{stamp}.csv.gz")
        flow_temporary.replace(ACTIVE_FLOW)
    else:
        flow_temporary.unlink(missing_ok=True)

    loss_updated = False
    if report_path(OPTIONAL_LOSS_REPORT) is not None:
        indicators = {}
        if INDICATORS.exists():
            indicators = json.loads(INDICATORS.read_text(encoding="utf-8")).get("valores", {})
        indicators[OPTIONAL_LOSS_REPORT] = extract_loss_reasons(_read_report(OPTIONAL_LOSS_REPORT))
        INDICATORS.write_text(
            json.dumps(
                {
                    "atualizado_em": datetime.now().astimezone().isoformat(),
                    "fonte": "Carga manual GoodData",
                    "valores": indicators,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        loss_updated = True

    result = {
        "status": "ok",
        "origem": "Carga manual GoodData",
        "atualizado_em": datetime.now().astimezone().isoformat(),
        "publicado_online": bool(publish),
        "linhas": len(base),
        "ultima_data": str(base["Data"].max().date()),
        "faturamento": round(float(final_total), 2),
        "relatorios": prepared["rows_by_report"],
        "eventos_funil_atualizados": 0 if flow_result is None else len(flow_result),
        "perdas_atualizadas": loss_updated,
    }
    if publish:
        upload_status(result)
    return result
