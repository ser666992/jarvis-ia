"""
sistema/display.py
=====================
Brilho da tela via WMI (`root\\wmi`, classe `WmiMonitorBrightness`) --
só funciona em telas que expõem controle de brilho por software (a
maioria de notebooks; monitores externos por HDMI/DisplayPort
geralmente não, porque o brilho é controlado só pelos botões físicos
do monitor). Usa `win32com` (pywin32, já presente no Windows junto com
`pyttsx3`/SAPI5 -- ver voz/tts.py), sem dependência nova.
"""

import sys

from logs.logger import get_logger

log = get_logger("sistema")

try:
    import win32com.client
    HAS_WMI = sys.platform == "win32"
except ImportError:
    HAS_WMI = False


def available() -> bool:
    return HAS_WMI


def _wmi_root():
    locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
    return locator.ConnectServer(".", "root\\wmi")


def get_brightness() -> int:
    if not HAS_WMI:
        raise RuntimeError("Controle de brilho requer Windows com WMI (pywin32).")
    service = _wmi_root()
    for item in service.ExecQuery("SELECT * FROM WmiMonitorBrightness"):
        return item.CurrentBrightness
    raise RuntimeError("Nenhuma tela com controle de brilho por software encontrada.")


def set_brightness(percent: int) -> int:
    if not HAS_WMI:
        raise RuntimeError("Controle de brilho requer Windows com WMI (pywin32).")
    percent = max(0, min(100, percent))
    service = _wmi_root()
    metodos = list(service.ExecQuery("SELECT * FROM WmiMonitorBrightnessMethods"))
    if not metodos:
        raise RuntimeError("Nenhuma tela com controle de brilho por software encontrada.")
    for item in metodos:
        item.WmiSetBrightness(1, percent)  # (tempo de transição em segundos, brilho %)
    return percent


def adjust_brightness(delta: int) -> int:
    novo = get_brightness() + delta
    return set_brightness(novo)
