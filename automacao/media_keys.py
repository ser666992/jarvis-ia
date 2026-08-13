"""
automacao/media_keys.py
==========================
Simula teclas de mídia do teclado (volume, mudo) via
`ctypes`/`user32.keybd_event` -- 100% stdlib no Windows, o mesmo
mecanismo que um teclado físico usa pra mandar esses eventos, então
funciona em qualquer app/sistema de som, sem precisar de nenhuma lib
de áudio nova.
"""

import sys

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def available() -> bool:
    return sys.platform == "win32"


def _press(vk_code: int, times: int = 1):
    if not available():
        raise RuntimeError("Controle de volume por tecla de mídia só está implementado no Windows.")
    import ctypes
    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def volume_up(steps: int = 5):
    """Cada 'step' corresponde a um toque na tecla de mídia (~2% de
    volume no Windows) -- o padrão de 5 dá um salto perceptível."""
    _press(VK_VOLUME_UP, steps)


def volume_down(steps: int = 5):
    _press(VK_VOLUME_DOWN, steps)


def mute_toggle():
    _press(VK_VOLUME_MUTE)


def play_pause():
    """Play/pause da mídia atual (Spotify, YouTube, player padrão...) --
    a mesma tecla de mídia que um teclado com botões de multimídia manda."""
    _press(VK_MEDIA_PLAY_PAUSE)


def next_track():
    _press(VK_MEDIA_NEXT)


def prev_track():
    _press(VK_MEDIA_PREV)


def stop_media():
    _press(VK_MEDIA_STOP)
