"""
automacao/instalador_apps.py
================================
"Baixa/instala um app só de dizer o nome" -- usa o `winget` (Windows
Package Manager, já vem com Windows 10/11 atualizados), que baixa de
um catálogo curado (Microsoft Store ou o próprio fabricante) -- não é
um scraper de site nenhum, é o mesmo gerenciador de pacotes oficial da
Microsoft que roda por trás da tela de "Instalar aplicativos".

Instalar um programa é tratado como ação destrutiva-adjacente (grava
software novo de verdade no sistema) -- exige `confirmed=True`
explícito, igual fechar um programa (ver seguranca/permissions.py).
"""

import shutil
import subprocess

from core.timeline import registrar
from logs.logger import get_logger
from seguranca.permissions import check_destructive_action

log = get_logger("automacao")


def available() -> bool:
    return shutil.which("winget") is not None


def buscar(nome: str, limite: int = 5) -> list:
    """Busca pacotes no catálogo do winget que combinem com `nome`."""
    if not available():
        raise RuntimeError("winget não está disponível nesse sistema (precisa do App Installer, Windows 10/11).")
    resultado = subprocess.run(
        ["winget", "search", nome, "--accept-source-agreements"],
        capture_output=True, text=True, timeout=30,
    )
    linhas = [l for l in resultado.stdout.splitlines() if l.strip()]
    candidatos = []
    comecou = False
    for linha in linhas:
        if linha.strip().startswith("---"):
            comecou = True
            continue
        if comecou:
            candidatos.append(linha.strip())
    return candidatos[:limite]


def _melhor_id(nome: str) -> str:
    """Pega o ID (ex.: 'Discord.Discord') do PRIMEIRO resultado da busca
    -- instalar por ID é bem mais confiável que por nome, que exige
    correspondência exata do rótulo (o motivo mais comum de 'não instala
    pelo nome': 'discord' != 'Discord', e sem -e o winget acha vários e
    aborta). O ID é o token no formato 'Editor.Pacote'."""
    try:
        resultado = subprocess.run(
            ["winget", "search", nome, "--accept-source-agreements", "--source", "winget"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return None
    comecou = False
    for linha in resultado.stdout.splitlines():
        if linha.strip().startswith("---"):
            comecou = True
            continue
        if comecou and linha.strip():
            for token in linha.split():
                # ID = "Editor.Pacote": tem ponto, começa com letra e não é versão.
                if "." in token and token[0].isalpha() and not token[0].isdigit():
                    return token
    return None


def instalar(nome: str, confirmed: bool = False, timeout: int = 300) -> str:
    """Instala o pacote que melhor combinar com `nome`, via winget.
    Ação destrutiva -- exige confirmed=True (ver seguranca.permissions).

    Estratégia (da mais pra menos confiável):
      1. Descobre o ID do primeiro resultado da busca e instala por ID
         (`--id ... -e`) -- evita o erro de 'nome não bate exatamente'.
      2. Se não achou ID, tenta pelo nome sem exigir correspondência exata."""
    check_destructive_action(f"instalar o programa '{nome}'", confirmed=confirmed)
    if not available():
        raise RuntimeError("winget não está disponível nesse sistema (precisa do App Installer, Windows 10/11).")

    base = ["--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"]
    pkg_id = _melhor_id(nome)
    resultado = None
    if pkg_id:
        resultado = subprocess.run(
            ["winget", "install", "--id", pkg_id, "-e", "--source", "winget", *base],
            capture_output=True, text=True, timeout=timeout,
        )
        if resultado.returncode == 0:
            registrar("app_instalado", f"{nome} ({pkg_id})")
            log.info("app instalado via winget por ID: %s", pkg_id)
            return f"'{pkg_id}' instalado.\n{resultado.stdout[-400:]}"

    # Fallback pelo nome (sem -e).
    resultado = subprocess.run(
        ["winget", "install", nome, *base],
        capture_output=True, text=True, timeout=timeout,
    )
    saida = resultado.stdout if resultado.returncode == 0 else (resultado.stderr or resultado.stdout)
    if resultado.returncode == 0:
        registrar("app_instalado", nome)
        log.info("app instalado via winget: %s", nome)
        return saida[-500:]

    # Mensagem de erro mais útil: causas comuns.
    dica = ""
    baixo = (saida or "").lower()
    if "multiple" in baixo or "vários" in baixo or "varios" in baixo:
        dica = " (o winget achou vários pacotes com esse nome -- tente um nome mais específico)"
    elif "elevat" in baixo or "administrator" in baixo or "administrador" in baixo:
        dica = " (esse pacote precisa de permissão de administrador -- rode o Ultron como admin)"
    elif "no package" in baixo or "nenhum pacote" in baixo:
        dica = f" (o winget não achou nenhum pacote chamado '{nome}')"
    return f"Não consegui instalar '{nome}'{dica}.\n{saida[-400:]}"
