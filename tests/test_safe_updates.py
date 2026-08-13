import json
from types import SimpleNamespace

import pytest


def test_update_is_blocked_without_approved_candidate(monkeypatch):
    from atualizacoes import safe_updater
    monkeypatch.setattr(safe_updater, "last_report", lambda: {})
    with pytest.raises(RuntimeError, match="candidata aprovada"):
        safe_updater.apply_validated(confirmed=True)


def test_update_is_blocked_when_remote_changed(monkeypatch):
    from atualizacoes import safe_updater
    monkeypatch.setattr(
        safe_updater, "last_report",
        lambda: {"sucesso": True, "commit_candidato": "old"})
    monkeypatch.setattr(
        safe_updater, "_run_git",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="new\n", stderr=""))
    with pytest.raises(RuntimeError, match="remota mudou"):
        safe_updater.apply_validated(confirmed=True)


def test_backup_and_rollback_restore_only_changed_paths(tmp_path, monkeypatch):
    from atualizacoes import safe_updater
    monkeypatch.setattr(safe_updater, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(safe_updater, "BACKUP_ROOT", tmp_path / "backups")
    existing = tmp_path / "core" / "item.py"
    existing.parent.mkdir()
    existing.write_text("antes", encoding="utf-8")

    archive = safe_updater._backup_changes([
        ("M", "core/item.py"), ("A", "core/novo.py")])
    existing.write_text("depois", encoding="utf-8")
    new_file = tmp_path / "core" / "novo.py"
    new_file.write_text("novo", encoding="utf-8")
    safe_updater.rollback(archive)

    assert existing.read_text(encoding="utf-8") == "antes"
    assert not new_file.exists()


def test_emergency_stop_cancels_all(monkeypatch):
    from automacao import tasks
    from core import emergency
    monkeypatch.setattr(tasks, "cancel_all", lambda: 4)
    result = emergency.stop_all()
    assert result["rotinas_interrompidas"] == 4


def test_update_check_fetches_real_remote_and_detects_remote_ahead(monkeypatch):
    from atualizacoes import updater
    calls = []

    def fake_git(args, timeout=15):
        calls.append(args)
        if args[0] == "fetch":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="local\n", stderr="")
        if args == ["rev-parse", "@{u}"]:
            return SimpleNamespace(returncode=0, stdout="remote\n", stderr="")
        if args[0] == "merge-base":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(updater, "_git_available", lambda: True)
    monkeypatch.setattr(updater, "is_git_repo", lambda: True)
    monkeypatch.setattr(updater, "_run_git", fake_git)
    report = updater.check_for_updates()
    assert report["atualizacao_disponivel"] is True
    assert ["fetch", "--prune", "--quiet"] in calls


def test_diverged_history_is_not_presented_as_automatic_update(monkeypatch):
    from atualizacoes import updater

    def fake_git(args, timeout=15):
        if args[0] == "fetch":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="local\n", stderr="")
        if args == ["rev-parse", "@{u}"]:
            return SimpleNamespace(returncode=0, stdout="remote\n", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(updater, "_git_available", lambda: True)
    monkeypatch.setattr(updater, "is_git_repo", lambda: True)
    monkeypatch.setattr(updater, "_run_git", fake_git)
    report = updater.check_for_updates()
    assert report["atualizacao_disponivel"] is False
    assert "divergiu" in report["motivo"]
