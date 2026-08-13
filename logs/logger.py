"""
logs/logger.py
================
Logging central do Ultron: um logger por módulo, todos gravando em
`logs/jarvis.log` (rotativo, via `logging.handlers.RotatingFileHandler`
da stdlib -- zero dependência externa).

Uso:
    from logs.logger import get_logger
    log = get_logger("ia")
    log.info("provedor %s respondeu em %.2fs", nome, dt)
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from config.settings import get_settings

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOGS_DIR, "jarvis.log")

_configured_loggers = {}
_root_configured = False


def _configure_root():
    global _root_configured
    if _root_configured:
        return
    settings = get_settings()
    level_name = str(settings.get("logs.nivel", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    max_bytes = int(settings.get("logs.arquivo_max_bytes", 1_048_576))
    backup_count = int(settings.get("logs.arquivos_backup", 3))

    os.makedirs(LOGS_DIR, exist_ok=True)

    root = logging.getLogger("jarvis")
    root.setLevel(level)
    if not root.handlers:
        handler = RotatingFileHandler(
            LOG_FILE, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        root.addHandler(handler)
    _root_configured = True


def get_logger(module_name: str) -> logging.Logger:
    _configure_root()
    full_name = f"jarvis.{module_name}"
    if full_name not in _configured_loggers:
        _configured_loggers[full_name] = logging.getLogger(full_name)
    return _configured_loggers[full_name]


def tail(n: int = 20) -> list:
    """Últimas n linhas do log atual -- usado pelo comando /logs no chat."""
    if not os.path.isfile(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return [line.rstrip("\n") for line in lines[-n:]]
