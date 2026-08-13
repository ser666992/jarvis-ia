"""
controle_pc/processos.py
============================
Abrir/fechar programa (reaproveita automacao.apps, não duplica),
listar processos (reaproveita sistema.processes), e duas capacidades
NOVAS: rodar um comando de sistema arbitrário, e encerrar
especificamente um processo que está "não responde" (diferente de
fechar_programa, que mata por nome sem checar se travou de verdade).

Executar comando e encerrar processo são as ações mais poderosas deste
pacote inteiro -- por isso as duas exigem `confirmed=True` (ver
seguranca.permissions), sempre, sem exceção de "é só um comando
inofensivo" -- quem decide o risco é a confirmação do usuário (ou o
toggle global "não peça confirmação"), nunca uma lista de comandos
"seguros" que eu tentaria adivinhar.
"""

import subprocess
import sys

from core.timeline import registrar
from logs.logger import get_logger
from seguranca.permissions import check_destructive_action

log = get_logger("controle_pc")

_TIMEOUT_PADRAO_SEGUNDOS = 30


def abrir_programa(nome_ou_caminho: str):
    """Reaproveita automacao.apps.open_program -- abrir é sempre
    permitido (reversível, fechar depois resolve)."""
    from automacao import apps
    apps.open_program(nome_ou_caminho)


def fechar_programa(nome_substring: str, confirmed: bool = False) -> int:
    """Reaproveita automacao.apps.close_program (já exige confirmed)."""
    from automacao import apps
    return apps.close_program(nome_substring, confirmed=confirmed)


def listar_processos(limite: int = 20) -> list:
    """Reaproveita sistema.processes.list_processes -- leitura, sem confirmação."""
    from sistema import processes
    return processes.list_processes(limit=limite)


def executar_comando(comando: str, timeout: int = _TIMEOUT_PADRAO_SEGUNDOS, confirmed: bool = False) -> dict:
    """Roda `comando` no shell do sistema operacional. Ação destrutiva
    por padrão -- pode fazer QUALQUER coisa que o usuário poderia fazer
    manualmente no terminal, então exige confirmed=True sempre, sem
    lista de exceções "comando seguro".

    Se o comando não terminar dentro de `timeout`, é encerrado (mesmo
    comportamento de core/skill_forge.py:rodar_programa) e o resultado
    volta com `"timeout": True` em vez de levantar exceção -- quem
    chama decide o que fazer, sem crash surpresa."""
    check_destructive_action(f"executar o comando do sistema: {comando}", confirmed=confirmed)
    shell = sys.platform == "win32"
    try:
        resultado = subprocess.run(
            comando, shell=shell, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        registrar("comando_executado", f"{comando[:80]} (excedeu {timeout}s)")
        return {"stdout": e.stdout or "", "stderr": e.stderr or "", "returncode": None, "timeout": True}

    registrar("comando_executado", f"{comando[:80]} (código {resultado.returncode})")
    return {"stdout": resultado.stdout, "stderr": resultado.stderr, "returncode": resultado.returncode, "timeout": False}


def _processo_nao_responde(pid: int) -> bool:
    """No Windows, checa via IsHungAppWindow a janela principal do
    processo -- mesma API usada por visao_continua/monitor.py."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        alvo_travada = {"achou": False}

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _callback(hwnd, _lparam):
            pid_janela = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_janela))
            if pid_janela.value == pid and user32.IsWindowVisible(hwnd):
                if user32.IsHungAppWindow(hwnd):
                    alvo_travada["achou"] = True
                    return False  # para a enumeração, já achou
            return True

        user32.EnumWindows(_callback, 0)
        return alvo_travada["achou"]
    except Exception as e:
        log.warning("falha ao checar se o processo %s não responde: %s", pid, e)
        return False


def encerrar_processo_travado(nome_ou_pid, confirmed: bool = False) -> dict:
    """Encerra um processo SÓ SE ele estiver realmente 'não responde'
    (IsHungAppWindow) -- diferente de fechar_programa, que mata por
    nome sem checar isso. Ação destrutiva -- exige confirmed=True."""
    import psutil

    candidatos = []
    if isinstance(nome_ou_pid, int) or str(nome_ou_pid).isdigit():
        try:
            candidatos = [psutil.Process(int(nome_ou_pid))]
        except psutil.NoSuchProcess:
            candidatos = []
    else:
        nome = str(nome_ou_pid).lower()
        candidatos = [
            p for p in psutil.process_iter(["pid", "name"])
            if p.info.get("name") and nome in p.info["name"].lower()
        ]

    travados = [p for p in candidatos if _processo_nao_responde(p.pid)]
    if not travados:
        return {"encerrados": 0, "motivo": "nenhum processo correspondente está com o status 'não responde'"}

    check_destructive_action(
        f"encerrar processo(s) travado(s): {nome_ou_pid}", confirmed=confirmed,
    )
    encerrados = 0
    for p in travados:
        try:
            p.terminate()
            encerrados += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if encerrados:
        registrar("processo_encerrado", f"{nome_ou_pid} ({encerrados} travado(s))")
    return {"encerrados": encerrados}
