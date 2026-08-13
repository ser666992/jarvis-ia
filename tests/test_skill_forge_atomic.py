import os

import pytest


_PLUGIN = '''
from core.plugin_manager import BasePlugin
class DemoPlugin(BasePlugin):
    name = "demo"
    description = "demo"
    triggers = ["comando muito especifico"]
    def handle(self, text, context):
        return None
'''


def test_failed_plugin_replacement_preserves_active_version(tmp_path, monkeypatch):
    from core import skill_forge
    pending = tmp_path / "pending"
    plugins = tmp_path / "plugins"
    pending.mkdir()
    plugins.mkdir()
    draft = pending / "demo.py"
    active = plugins / "demo.py"
    draft.write_text(_PLUGIN + "\nVERSION = 'new'\n", encoding="utf-8")
    active.write_text(_PLUGIN + "\nVERSION = 'old'\n", encoding="utf-8")
    monkeypatch.setattr(skill_forge, "PENDING_DIR", str(pending))
    monkeypatch.setattr(skill_forge, "PLUGINS_DIR", str(plugins))

    def fail_replace(source, destination):
        raise OSError("disco ocupado")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        skill_forge.aprovar_habilidade("demo")

    assert "VERSION = 'old'" in active.read_text(encoding="utf-8")
    assert draft.exists()


def test_plugin_replacement_is_atomic(tmp_path, monkeypatch):
    from core import skill_forge
    pending = tmp_path / "pending"
    plugins = tmp_path / "plugins"
    pending.mkdir()
    plugins.mkdir()
    draft = pending / "demo.py"
    active = plugins / "demo.py"
    draft.write_text(_PLUGIN + "\nVERSION = 'new'\n", encoding="utf-8")
    active.write_text(_PLUGIN + "\nVERSION = 'old'\n", encoding="utf-8")
    monkeypatch.setattr(skill_forge, "PENDING_DIR", str(pending))
    monkeypatch.setattr(skill_forge, "PLUGINS_DIR", str(plugins))

    skill_forge.aprovar_habilidade("demo")

    assert "VERSION = 'new'" in active.read_text(encoding="utf-8")
    assert not draft.exists()
