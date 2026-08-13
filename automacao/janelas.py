"""
automacao/janelas.py
=======================
Controle de janelas de OUTROS programas já abertos: minimizar,
maximizar, restaurar, trazer pra frente (focar) -- por nome/título,
igual a automacao/apps.py já faz pra abrir/fechar programas.

Diferente de fechar um programa (automacao/apps.py:close_program,
mata o processo): aqui a janela continua existindo, só muda de estado
visual. Por isso não passa por seguranca.permissions -- é reversível
na hora (minimizar de novo desfaz, maximizar de novo desfaz).

100% opcional -- requer `pygetwindow` (requirements-automacao.txt).
Sem essa dependência instalada, `available()` retorna False e quem
chama (plugins/system_control.py) avisa o usuário, sem travar nada.
"""

import sys
import time

from core.timeline import registrar

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False


def available() -> bool:
    return HAS_PYGETWINDOW


def _encontrar(titulo_substring: str):
    # Busca vazia bateria com a primeira janela de título não-vazio (toda
    # string contém a string vazia) -- mesma classe de bug já corrigida em
    # controle_pc/elementos.py, recusada aqui também.
    alvo = (titulo_substring or "").strip().lower()
    if not alvo:
        return None
    for w in gw.getAllWindows():
        if w.title and alvo in w.title.lower():
            return w
    return None


def minimizar(titulo_substring: str) -> bool:
    if not HAS_PYGETWINDOW:
        raise RuntimeError("Instale 'pygetwindow' (requirements-automacao.txt) para eu controlar janelas.")
    janela = _encontrar(titulo_substring)
    if not janela:
        return False
    janela.minimize()
    registrar("janela_controlada", f"minimizar {titulo_substring}")
    return True


def maximizar(titulo_substring: str) -> bool:
    if not HAS_PYGETWINDOW:
        raise RuntimeError("Instale 'pygetwindow' (requirements-automacao.txt) para eu controlar janelas.")
    janela = _encontrar(titulo_substring)
    if not janela:
        return False
    janela.maximize()
    registrar("janela_controlada", f"maximizar {titulo_substring}")
    return True


def restaurar(titulo_substring: str) -> bool:
    if not HAS_PYGETWINDOW:
        raise RuntimeError("Instale 'pygetwindow' (requirements-automacao.txt) para eu controlar janelas.")
    janela = _encontrar(titulo_substring)
    if not janela:
        return False
    janela.restore()
    registrar("janela_controlada", f"restaurar {titulo_substring}")
    return True


def focar(titulo_substring: str) -> bool:
    if not HAS_PYGETWINDOW:
        raise RuntimeError("Instale 'pygetwindow' (requirements-automacao.txt) para eu controlar janelas.")
    janela = _encontrar(titulo_substring)
    if not janela:
        return False
    try:
        if janela.isMinimized:
            janela.restore()
        janela.activate()
    except Exception:
        # Em alguns casos o Windows recusa ativação entre processos
        # (SetForegroundWindow restrito) -- restore() já deixa a janela
        # visível mesmo que não venha totalmente pra frente.
        pass
    registrar("janela_controlada", f"focar {titulo_substring}")
    return True


def listar_titulos() -> list:
    if not HAS_PYGETWINDOW:
        return []
    return sorted({w.title for w in gw.getAllWindows() if w.title})


def _encontrar_hwnd_win32(titulo_substring: str):
    """Acha o handle de uma janela visível por substring do título, via
    WinAPI direta (EnumWindows) -- não depende do pygetwindow, que já se
    mostrou inconsistente pra enumerar janelas que existem de verdade
    (ver forcar_foco abaixo pro motivo de precisar do hwnd bruto)."""
    import ctypes
    from ctypes import wintypes

    alvo = (titulo_substring or "").strip().lower()
    if not alvo:
        return None
    user32 = ctypes.windll.user32
    encontrados = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if alvo in buf.value.lower():
            encontrados.append(hwnd)
        return True

    user32.EnumWindows(_callback, 0)
    return encontrados[0] if encontrados else None


def _forcar_foco_hwnd_win32(hwnd) -> bool:
    """AttachThreadInput: o workaround documentado da Microsoft pro
    bloqueio de foco do Windows (um processo não consegue roubar o foco
    de quem está em primeiro plano com SetForegroundWindow sozinho) --
    mesma técnica de gui/app.py:_forcar_foco_win32, usada lá pra janela
    do próprio Ultron. Aqui serve pra janelas de OUTROS programas que o
    Ultron abre (Spotify, navegador tocando música, etc.), que sofrem do
    mesmo bloqueio: o programa abre de verdade, mas fica atrás de tudo
    porque quem o abriu (Ultron) não era o processo em primeiro plano no
    momento -- parecendo pro usuário que "não abriu"/"não tocou nada"."""
    import ctypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    foreground_hwnd = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
    current_thread = kernel32.GetCurrentThreadId()
    anexado = False
    if foreground_thread and foreground_thread != current_thread:
        anexado = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))
    try:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        return True
    finally:
        if anexado:
            user32.AttachThreadInput(foreground_thread, current_thread, False)


def forcar_foco(titulo_substring: str, tentativas: int = 6, intervalo: float = 0.5) -> bool:
    """Traz de verdade pra frente a janela de outro programa que o
    Ultron acabou de abrir (Spotify, navegador). Diferente de focar()
    (que usa pygetwindow.activate(), sujeito ao mesmo bloqueio do
    Windows), usa AttachThreadInput -- funciona mesmo quando quem chama
    (o próprio Ultron) não é o processo em primeiro plano, que é
    justamente o caso normal aqui. Tenta algumas vezes com intervalo
    porque o programa alvo pode ainda estar abrindo a janela na primeira
    tentativa (ex.: Spotify saindo da bandeja, navegador carregando)."""
    if sys.platform != "win32":
        return False
    for _ in range(max(1, tentativas)):
        hwnd = _encontrar_hwnd_win32(titulo_substring)
        if hwnd:
            try:
                return _forcar_foco_hwnd_win32(hwnd)
            except Exception:
                return False
        time.sleep(intervalo)
    return False
