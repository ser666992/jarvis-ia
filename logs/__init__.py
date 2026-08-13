import os

from logs.logger import get_logger, tail, LOG_FILE

__all__ = ["get_logger", "tail", "status"]


def status() -> dict:
    return {
        "disponivel": True,
        "motivo": "logging da stdlib (RotatingFileHandler), sempre disponível",
        "detalhes": {"arquivo": LOG_FILE, "existe": os.path.isfile(LOG_FILE)},
    }
