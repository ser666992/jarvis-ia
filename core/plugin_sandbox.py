"""Inspeção estática, snapshots e rollback de plugins."""

import ast
import os
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
VERSIONS_DIR = os.path.join(BASE_DIR, "data", "plugin_versions")
_DANGEROUS_CALLS = {"eval", "exec", "compile", "__import__"}


def inspect_plugin(path: str) -> dict:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _DANGEROUS_CALLS:
                findings.append(f"chamada dinâmica: {node.func.id} (linha {node.lineno})")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "socket"):
                    findings.append(f"import sensível: {alias.name} (linha {node.lineno})")
    return {"ok": not findings, "findings": findings, "syntax_ok": True}


def snapshot(path: str) -> str:
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    name = os.path.basename(path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = os.path.join(VERSIONS_DIR, f"{name}.{stamp}.bak")
    shutil.copy2(path, dest)
    return dest


def versions(plugin_filename: str) -> list:
    if not os.path.isdir(VERSIONS_DIR):
        return []
    prefix = os.path.basename(plugin_filename) + "."
    return sorted(
        [os.path.join(VERSIONS_DIR, f) for f in os.listdir(VERSIONS_DIR)
         if f.startswith(prefix) and f.endswith(".bak")],
        reverse=True,
    )


def restore(plugin_path: str, version_path: str):
    expected = os.path.abspath(VERSIONS_DIR) + os.sep
    resolved = os.path.abspath(version_path)
    if not resolved.startswith(expected):
        raise ValueError("versão fora do diretório seguro")
    snapshot(plugin_path)
    shutil.copy2(resolved, plugin_path)
