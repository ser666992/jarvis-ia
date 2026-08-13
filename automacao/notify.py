"""
automacao/notify.py
======================
Notificação genérica, usada por qualquer módulo que precise avisar o
usuário de algo de forma proativa (lembretes com horário, comentários
automáticos sobre o que o usuário está fazendo, etc.) -- ver
automacao/reminders.py e plugins/observation.py.

Melhor-esforço e sempre degrada graciosamente: toca um som do sistema
(via `winsound` no Windows; sem isso, um beep ASCII) e sempre imprime
a mensagem no console/log. Quem quiser um aviso visual extra (ex.: a
GUI, com um toast na bandeja do sistema) registra uma função com
`add_notifier()`.
"""

import sys

from logs.logger import get_logger

log = get_logger("automacao")

_notifiers = []


def add_notifier(func):
    """Registra `func(titulo, mensagem)`, chamada sempre que `notify()`
    for chamado -- além do som e do print que já acontecem sempre. Pode
    registrar mais de um notifier (ex.: GUI + log)."""
    _notifiers.append(func)


def _play_sound():
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound("SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC)
            return
        except Exception as e:
            log.warning("falha ao tocar som do sistema: %s", e)
    try:
        print("\a", end="", flush=True)
    except Exception:
        pass


def notify(titulo: str, mensagem: str, sound: bool = True):
    if sound:
        _play_sound()
    print(f"\n[{titulo}] {mensagem}\n")
    for notifier in list(_notifiers):
        try:
            notifier(titulo, mensagem)
        except Exception as e:
            log.warning("notifier falhou: %s", e)
