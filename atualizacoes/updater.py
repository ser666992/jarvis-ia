"""
atualizacoes/updater.py
==========================
Checagem (e, só com confirmação explícita, aplicação) de atualizações
via git.

- `check_for_updates()`: atualiza apenas referências remotas (`git
  fetch`) e verifica commits novos; nunca altera arquivos do projeto.
- `_tick()`/`iniciar()`: checagem automática periódica (config
  `atualizacoes.verificar_automaticamente`, ligado por padrão,
  `atualizacoes.intervalo_horas`, 24h por padrão) -- quando encontra
  uma atualização nova, AVISA por notificação (uma vez por commit
  remoto, não fica repetindo o mesmo aviso a cada checagem) e nunca
  aplica nada sozinha.
- `aplicar_atualizacao(confirmed=True)`: só ESTA função de fato roda
  `git pull` -- exige confirmação explícita, mesma regra de qualquer
  outra ação de alto impacto deste projeto (ver seguranca/permissions.py).
  Atualizar o código pode sobrescrever mudanças locais e muda o
  processo rodando sem reiniciar, então nunca acontece sem o usuário
  pedir de propósito.

Se o diretório não for um repositório git (ou `git` não estiver no
PATH), tudo isso reporta a limitação claramente em vez de travar ou
fingir que funcionou.
"""

import os
import shutil
import subprocess

from atualizacoes.version import VERSION

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ultimo_commit_avisado = None  # evita avisar repetidamente sobre o MESMO commit remoto pendente


def _git_available() -> bool:
    return shutil.which("git") is not None


def _run_git(args: list, timeout: int = 15):
    return subprocess.run(["git"] + args, cwd=BASE_DIR, capture_output=True, text=True, timeout=timeout)


def is_git_repo() -> bool:
    if not _git_available():
        return False
    result = _run_git(["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def check_for_updates() -> dict:
    """Retorna um relatório; pode atualizar refs remotas, nunca arquivos."""
    if not _git_available():
        return {
            "verificavel": False,
            "atualizacao_disponivel": False,
            "motivo": "'git' não encontrado no PATH.",
            "versao_local": VERSION,
        }

    if not is_git_repo():
        return {
            "verificavel": False,
            "atualizacao_disponivel": False,
            "motivo": "este diretório não é um repositório git.",
            "versao_local": VERSION,
        }

    # --dry-run não atualiza @{u}; comparar depois dele usava uma
    # referência antiga e podia esconder atualizações reais.
    fetch = _run_git(["fetch", "--prune", "--quiet"], timeout=30)
    if fetch.returncode != 0:
        return {
            "verificavel": False,
            "atualizacao_disponivel": False,
            "motivo": f"não foi possível checar o remoto: {fetch.stderr.strip()}",
            "versao_local": VERSION,
        }

    local = _run_git(["rev-parse", "HEAD"]).stdout.strip()
    remote_ref = _run_git(["rev-parse", "@{u}"])
    if remote_ref.returncode != 0:
        return {
            "verificavel": True,
            "atualizacao_disponivel": False,
            "motivo": "branch local não tem upstream configurado (sem remoto para comparar).",
            "versao_local": VERSION,
        }

    remote = remote_ref.stdout.strip()
    # Diferentes não significa necessariamente "remoto mais novo": o
    # branch local pode estar à frente ou ter divergido. Só oferecemos
    # atualização automática quando HEAD é ancestral do upstream.
    ancestor = _run_git(["merge-base", "--is-ancestor", "HEAD", "@{u}"])
    atualizacao_disponivel = local != remote and ancestor.returncode == 0
    divergiu = local != remote and ancestor.returncode != 0

    return {
        "verificavel": True,
        "atualizacao_disponivel": atualizacao_disponivel,
        "motivo": (
            "há commits novos no remoto -- valide a atualização antes de aplicar."
            if atualizacao_disponivel else
            "o histórico local divergiu do remoto; atualização automática bloqueada."
            if divergiu else
            "já está na versão mais recente do remoto configurado."
        ),
        "versao_local": VERSION,
        "commit_local": local[:8],
        "commit_remoto": remote[:8],
    }


def aplicar_atualizacao(confirmed: bool = False) -> dict:
    """Roda `git pull` de verdade -- ação de alto impacto (pode
    sobrescrever mudanças locais, muda o código do processo já
    rodando), sempre exige confirmed=True (ver seguranca/permissions.py).
    NUNCA é chamada sozinha por nenhuma rotina automática -- só quando o
    próprio usuário pede explicitamente (ver plugins/atualizacoes.py)."""
    # Compatibilidade: chamadas antigas também passam pelo candidato
    # isolado; não existe mais um caminho público de pull direto.
    from atualizacoes.safe_updater import apply_validated
    return apply_validated(confirmed=confirmed)


def _tick(jarvis=None):
    """Checagem periódica -- só avisa (uma vez por commit remoto novo,
    pra não repetir o mesmo aviso a cada rodada), nunca aplica nada."""
    global _ultimo_commit_avisado
    resultado = check_for_updates()
    if not resultado.get("atualizacao_disponivel"):
        return
    commit_remoto = resultado.get("commit_remoto")
    if commit_remoto and commit_remoto == _ultimo_commit_avisado:
        return
    _ultimo_commit_avisado = commit_remoto

    from automacao.notify import notify
    notify(
        "Ultron: atualização disponível",
        f"Há uma versão nova no repositório remoto (commit {commit_remoto or '?'}). "
        'Diga "atualiza o jarvis, confirmo" pra eu aplicar (git pull), ou rode você mesmo.',
    )


def iniciar(jarvis):
    """Chamado uma vez no startup do Ultron -- agenda a checagem
    periódica de atualizações. No-op se o módulo 'atualizacoes' estiver
    desligado, ou se atualizacoes.verificar_automaticamente for false."""
    settings = jarvis.settings
    if not settings.is_module_enabled("atualizacoes"):
        return
    if not settings.get("atualizacoes.verificar_automaticamente", True):
        return
    horas = settings.get("atualizacoes.intervalo_horas", 24)
    try:
        horas = float(horas)
    except (TypeError, ValueError):
        horas = 24
    intervalo_segundos = max(3600, horas * 3600)
    from automacao import tasks
    tasks.schedule_recurring("atualizacoes_check", intervalo_segundos, _tick, jarvis)
