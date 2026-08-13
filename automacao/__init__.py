from automacao import apps, files, media_keys, notify, reminders, tasks, watcher

__all__ = [
    "apps", "files", "media_keys", "notify", "reminders", "tasks", "watcher", "status",
]


def status() -> dict:
    backend = "watchdog" if watcher.HAS_WATCHDOG else "polling (fallback sem dependência)"
    return {
        "disponivel": True,
        "motivo": f"abrir apps / arquivos / agendamento via stdlib; observação de pastas via {backend}",
        "detalhes": {"watchdog": watcher.HAS_WATCHDOG, "psutil_para_fechar_apps": apps.HAS_PSUTIL},
    }
