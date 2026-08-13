"""
ia/__init__.py
=================
Ponto de entrada do módulo de IA. `manager()` devolve uma instância
única (singleton leve) do AIManager, usada pelo núcleo do Ultron
(`core/jarvis.py`) e por qualquer plugin que queira consultar um
provedor de IA diretamente.
"""

from ia.manager import AIManager

__all__ = ["AIManager", "manager", "status"]

_instance = None


def manager() -> AIManager:
    global _instance
    if _instance is None:
        _instance = AIManager()
    return _instance


def status() -> dict:
    return manager().status()
