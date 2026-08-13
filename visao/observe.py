"""
visao/observe.py
===================
"Ver" o que o usuário está fazendo no computador agora, de forma leve
e sem gravar nada: janela em foco (via ctypes/user32, stdlib puro no
Windows -- sem dependência extra), processo dono da janela (requer
`psutil`, opcional) e texto visível na tela (OCR, via visao/ocr.py,
também opcional). Serve de base para comentários automáticos sobre a
atividade -- ver plugins/observation.py.

Só olha o que já está na tela no momento da chamada -- não grava vídeo
nem roda em segundo plano sozinho (isso é responsabilidade de quem
chama, ex.: automacao.tasks.schedule_recurring).
"""

import sys

from logs.logger import get_logger

log = get_logger("visao")


def active_window_title():
    """Título da janela em foco. Só funciona no Windows (usa
    ctypes/user32, sem dependência extra); em outros sistemas retorna
    None -- degrada graciosamente, como o resto do projeto."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return None
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value or None
    except Exception as e:
        log.warning("falha ao ler janela em foco: %s", e)
        return None


def active_process_name():
    """Nome do processo dono da janela em foco (Windows + `psutil`)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import psutil
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            return psutil.Process(pid.value).name()
    except Exception as e:
        log.warning("falha ao identificar processo em foco: %s", e)
    return None


def visible_screen_text(monitor_index: int = 1, lang: str = "por", max_chars: int = 500):
    """Texto visível na tela via OCR -- None se a dependência opcional
    (pytesseract + binário Tesseract) não estiver disponível."""
    try:
        from visao.ocr import available as ocr_available
        if not ocr_available():
            return None
        from visao.screen import read_screen_text
        texto = read_screen_text(monitor_index=monitor_index, lang=lang).strip()
        return texto[:max_chars] if texto else None
    except Exception as e:
        log.warning("falha ao ler texto da tela: %s", e)
        return None


def describe_activity(monitor_index: int = 1, lang: str = "por") -> dict:
    """Retrato simples do que está acontecendo na tela agora: janela em
    foco, processo e texto visível. Cada campo pode vir None se a
    informação (ou a dependência opcional por trás dela) não estiver
    disponível -- quem consome isto precisa lidar com None em todos."""
    return {
        "janela": active_window_title(),
        "processo": active_process_name(),
        "texto_tela": visible_screen_text(monitor_index=monitor_index, lang=lang),
    }
