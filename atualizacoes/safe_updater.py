"""Pipeline transacional de atualização do Neutron.

Uma versão remota nunca é testada em cima da instalação ativa. Ela é
clonada numa área isolada, compilada e testada primeiro. A aplicação só
é permitida em uma árvore limpa e usa ``git pull --ff-only``. Os arquivos
afetados são guardados antes da troca para permitir rollback pontual.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from atualizacoes.updater import BASE_DIR, _run_git, is_git_repo

STAGING_ROOT = Path(BASE_DIR) / "data" / "update_staging"
BACKUP_ROOT = Path(BASE_DIR) / "data" / "update_backups"
REPORT_PATH = Path(BASE_DIR) / "data" / "last_update_report.json"


def _run(args, cwd, timeout=300):
    return subprocess.run(
        args, cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )


def working_tree_status() -> list[str]:
    if not is_git_repo():
        return ["não é um repositório git"]
    result = _run_git(["status", "--porcelain"], timeout=20)
    return [line for line in result.stdout.splitlines() if line.strip()]


def _remote_url() -> str:
    result = _run_git(["remote", "get-url", "origin"])
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("O repositório não possui um remoto 'origin'.")
    return result.stdout.strip()


def _save_report(report: dict) -> dict:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def last_report() -> dict:
    try:
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def validate_candidate(test_timeout=600) -> dict:
    """Clona e testa o candidato remoto sem modificar a instalação."""
    if not is_git_repo():
        return _save_report({"sucesso": False, "fase": "preparo",
                             "erro": "Este diretório não é um repositório git."})
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix="candidate_", dir=STAGING_ROOT))
    report = {"sucesso": False, "fase": "clone", "candidato": str(candidate)}
    try:
        clone = _run(["git", "clone", "--depth", "1", _remote_url(), str(candidate)],
                     BASE_DIR, timeout=180)
        report["clone"] = (clone.stdout + clone.stderr)[-4000:]
        if clone.returncode:
            report["erro"] = "Falha ao baixar a versão candidata."
            return _save_report(report)

        report["fase"] = "compilacao"
        compile_result = _run(
            [sys.executable, "-m", "compileall", "-q", "."], candidate, timeout=180)
        report["compilacao"] = (compile_result.stdout + compile_result.stderr)[-4000:]
        if compile_result.returncode:
            report["erro"] = "A versão candidata possui erro de compilação."
            return _save_report(report)

        report["fase"] = "testes"
        tests = _run([sys.executable, "-m", "pytest", "-q"], candidate,
                     timeout=test_timeout)
        report["testes"] = (tests.stdout + tests.stderr)[-8000:]
        report["sucesso"] = tests.returncode == 0
        report["fase"] = "aprovado" if report["sucesso"] else "reprovado"
        if not report["sucesso"]:
            report["erro"] = "Os testes da versão candidata falharam."
        head = _run(["git", "rev-parse", "HEAD"], candidate)
        report["commit_candidato"] = head.stdout.strip()
        report["validado_em"] = datetime.now().isoformat(timespec="seconds")
        return _save_report(report)
    except subprocess.TimeoutExpired:
        report.update({"fase": "timeout", "erro": "A validação excedeu o tempo limite."})
        return _save_report(report)


def _changed_paths() -> list[tuple[str, str]]:
    result = _run_git(["diff", "--name-status", "HEAD..@{u}"], timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Não consegui listar os arquivos da atualização.")
    changes = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            status = parts[0][0]
            if status in ("R", "C") and len(parts) >= 3:
                changes.append(("D", parts[1]))
                changes.append(("A", parts[2]))
            else:
                changes.append((status, parts[1]))
    return changes


def _safe_path(relative: str) -> Path:
    root = Path(BASE_DIR).resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise RuntimeError(f"Caminho inseguro na atualização: {relative}")
    return target


def _backup_changes(changes) -> Path:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = BACKUP_ROOT / f"update_{stamp}.zip"
    manifest = {"ausentes": [], "arquivos": []}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, relative in changes:
            target = _safe_path(relative)
            if target.is_file():
                zf.write(target, relative)
                manifest["arquivos"].append(relative)
            elif not target.exists():
                manifest["ausentes"].append(relative)
        zf.writestr("_manifest.json", json.dumps(manifest, ensure_ascii=False))
    return archive


def rollback(archive: str | Path) -> None:
    """Restaura somente os caminhos tocados pela atualização."""
    archive = Path(archive)
    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read("_manifest.json"))
        for relative in manifest["ausentes"]:
            target = _safe_path(relative)
            if target.is_file():
                target.unlink()
        for relative in manifest["arquivos"]:
            target = _safe_path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(relative) as source, open(target, "wb") as dest:
                shutil.copyfileobj(source, dest)


def apply_validated(confirmed=False) -> dict:
    """Aplica apenas um candidato aprovado e restaura em caso de falha."""
    from seguranca.permissions import check_destructive_action
    check_destructive_action("aplicar atualização validada do Neutron", confirmed=confirmed)
    report = last_report()
    if not report.get("sucesso"):
        raise RuntimeError("Não existe uma versão candidata aprovada nos testes.")
    upstream = _run_git(["rev-parse", "@{u}"], timeout=20)
    if upstream.returncode or upstream.stdout.strip() != report.get("commit_candidato"):
        raise RuntimeError(
            "A versão remota mudou depois da validação. Teste novamente antes de aplicar.")
    dirty = working_tree_status()
    if dirty:
        raise RuntimeError(
            f"Atualização bloqueada: existem {len(dirty)} alterações locais. "
            "Salve/commite esse trabalho antes de atualizar.")
    changes = _changed_paths()
    archive = _backup_changes(changes)
    pull = _run_git(["pull", "--ff-only"], timeout=180)
    output = (pull.stdout or "") + (pull.stderr or "")
    if pull.returncode:
        rollback(archive)
        return {"sucesso": False, "rollback": True, "saida": output.strip(),
                "backup": str(archive)}
    smoke = _run([sys.executable, "-m", "compileall", "-q", "."], BASE_DIR, timeout=180)
    if smoke.returncode:
        rollback(archive)
        return {"sucesso": False, "rollback": True,
                "saida": "Compilação posterior falhou; versão anterior restaurada.",
                "backup": str(archive)}
    return {"sucesso": True, "rollback": False, "saida": output.strip(),
            "backup": str(archive), "arquivos": len(changes)}
