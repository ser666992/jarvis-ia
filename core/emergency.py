"""Parada imediata e centralizada das automações do Neutron."""

from datetime import datetime

_last_stop = None


def stop_all() -> dict:
    global _last_stop
    from automacao import tasks
    from core.resilience import reset
    stopped = tasks.cancel_all()
    try:
        from automacao.instagram_auto import fechar_sessao
        fechar_sessao()
    except Exception:
        pass
    reset()
    _last_stop = datetime.now().isoformat(timespec="seconds")
    return {"rotinas_interrompidas": stopped, "em": _last_stop}


def status() -> dict:
    return {"ultima_parada": _last_stop}
