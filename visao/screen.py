"""
visao/screen.py
==================
Captura e leitura de tela via `mss` (rápido, multi-monitor). Também
serve de base para "compartilhamento de tela" (gravar um vídeo curto
da tela usando `mss` + `opencv`, ambos leves).
"""

from logs.logger import get_logger

log = get_logger("visao")

try:
    import mss
    import numpy as np
    HAS_MSS = True
except ImportError:
    HAS_MSS = False


def available() -> bool:
    return HAS_MSS


def screenshot(monitor_index: int = 1):
    """Retorna um frame numpy BGR da tela (compatível com visao.ocr/visao.objects)."""
    if not HAS_MSS:
        raise RuntimeError("Instale 'mss' para captura de tela (pip install mss).")
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        raw = sct.grab(monitor)
        return np.array(raw)[:, :, :3]  # BGRA -> BGR


def save_screenshot(path: str, monitor_index: int = 1) -> bool:
    if not HAS_MSS:
        raise RuntimeError("Instale 'mss' para captura de tela.")
    with mss.mss() as sct:
        sct.shot(mon=monitor_index, output=path)
    return True


def read_screen_text(monitor_index: int = 1, lang: str = "por") -> str:
    """Combina captura de tela + OCR (visao.ocr) para 'ler' o que está na tela."""
    from visao.ocr import read_text_from_frame
    frame = screenshot(monitor_index)
    return read_text_from_frame(frame, lang=lang)


def record_screen(path: str, seconds: float = 5.0, fps: int = 10, monitor_index: int = 1) -> str:
    """Grava um vídeo curto da tela em `path` (.mp4) -- base para
    'compartilhamento de tela' pedido no escopo original."""
    if not HAS_MSS:
        raise RuntimeError("Instale 'mss' e 'opencv-python' para gravar a tela.")
    import time
    import cv2

    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        width, height = monitor["width"], monitor["height"]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(path, fourcc, fps, (width, height))

        try:
            start = time.time()
            interval = 1.0 / fps
            while time.time() - start < seconds:
                frame = np.array(sct.grab(monitor))[:, :, :3]
                writer.write(frame)
                time.sleep(interval)
        finally:
            # Sem o finally, um erro no meio da gravação (ex.: troca de
            # resolução, monitor desconectado, tela bloqueada) pulava
            # o release() -- para um cv2.VideoWriter isso não só
            # vazava o handle do encoder, como deixava o .mp4 sem o
            # trailer final, corrompido/incompleto.
            writer.release()
    return path
