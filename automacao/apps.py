"""
automacao/apps.py
====================
Abrir/fechar programas e sites. Abrir é sempre permitido (ação
reversível — fechar o programa depois resolve). Fechar um processo é
uma ação mais delicada: exige `seguranca.check_destructive_action`
com confirmação explícita antes de executar.
"""

import os
import platform
import subprocess
import webbrowser

from core.timeline import registrar
from logs.logger import get_logger
from seguranca.permissions import check_destructive_action

log = get_logger("automacao")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def open_url(url: str):
    webbrowser.open(url)


def open_program(path_or_name: str):
    """Abre um programa pelo caminho do executável (no Windows também
    aceita apenas o nome, se associado/no PATH)."""
    system = platform.system()
    if system == "Windows":
        os.startfile(path_or_name)
    elif system == "Darwin":
        subprocess.Popen(["open", path_or_name])
    else:
        subprocess.Popen([path_or_name])
    registrar("app_aberto", path_or_name)


def close_program(name_substring: str, confirmed: bool = False) -> int:
    """Encerra processos cujo nome contenha `name_substring`. Ação
    destrutiva -- exige confirmed=True (ver seguranca.permissions).
    Retorna quantos processos foram encerrados.

    Uma busca vazia bateria com TODO processo nomeado no sistema (toda
    string contém a string vazia) -- recusada aqui na raiz, não só nos
    chamadores, porque esta função também é chamada como API direta
    (controle_pc/processos.py:fechar_programa) por código que pode não
    ter o mesmo guard que plugins/system_control.py já tinha."""
    if not name_substring or not name_substring.strip():
        raise ValueError(
            "Preciso do nome (ou parte dele) do programa pra fechar -- uma busca vazia "
            "bateria com todos os processos rodando."
        )
    check_destructive_action(f"fechar programa '{name_substring}'", confirmed=confirmed)
    if not HAS_PSUTIL:
        raise RuntimeError("Instale 'psutil' para fechar programas por nome.")

    closed = 0
    name_substring = name_substring.lower()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.info.get("name") and name_substring in p.info["name"].lower():
                p.terminate()
                closed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if closed:
        registrar("app_fechado", f"{name_substring} ({closed} processo(s))")
    return closed
