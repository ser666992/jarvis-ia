"""
sistema/ociosidade.py
========================
Detecta há quanto tempo o computador está sem uso (sem teclado/mouse) --
base do "Modo Autônomo": só trabalha sozinho quando ninguém está usando
o PC de verdade, nunca durante o uso ativo.

Windows: `GetLastInputInfo` (API nativa do próprio Windows pra "idle
time", a mesma que a proteção de tela/bloqueio automático usa) via
ctypes -- sem dependência nova. Fora do Windows, `available()` retorna
False (honesto: não implementado pra Linux/macOS aqui).
"""

import sys

from logs.logger import get_logger

log = get_logger("sistema")


def available() -> bool:
    return sys.platform == "win32"


def segundos_ocioso() -> float:
    """Segundos desde o último movimento de mouse/tecla pressionada.
    Levanta RuntimeError se não disponível (chame available() antes)."""
    if not available():
        raise RuntimeError("Detecção de ociosidade só implementada no Windows.")
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        raise RuntimeError("GetLastInputInfo falhou.")
    tick_agora = ctypes.windll.kernel32.GetTickCount()
    # Ambos em milissegundos desde o boot -- GetTickCount() retorna um
    # unsigned de 32 bits e "vira" (overflow) a cada ~49.7 dias; se isso
    # acontecer bem no meio da leitura, o resultado pode vir negativo
    # por um instante -- max(0, ...) evita reportar ociosidade absurda.
    ms_ocioso = max(0, tick_agora - info.dwTime)
    return ms_ocioso / 1000.0


def esta_ocioso(limite_minutos: float) -> bool:
    """True se o usuário está sem mexer no PC há >= limite_minutos.
    Sempre False (nunca dispara autonomia) se a detecção não estiver
    disponível -- degrade seguro."""
    if not available():
        return False
    try:
        return segundos_ocioso() >= limite_minutos * 60.0
    except Exception as e:
        log.warning("ociosidade: falha ao checar (%s) -- assumindo em uso", e)
        return False
