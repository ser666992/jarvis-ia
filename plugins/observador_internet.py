"""
plugins/observador_internet.py
==================================
Comandos de chat pro Observador da Internet (sistema/observador_internet.py).

Comandos:
    "verifica atualizações" / "tem alguma atualização de biblioteca"
    "o que tem de novo nas minhas bibliotecas"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_VERIFICAR_RE = re.compile(
    r"\bverific[ae]\w*\s+.*\b(?:atualiza[çc][õo]es|bibliotecas)\b|"
    r"\b(?:tem|há|ha)\s+.*\batualiza[çc][ãa]o\b.*\bbiblioteca\b|"
    r"\bo\s+que\s+tem\s+de\s+novo\s+na[sm]?\s+(?:minhas?\s+)?bibliotecas\b|"
    r"\bobservador\s+da\s+internet\b",
    re.IGNORECASE,
)


class ObservadorInternetPlugin(BasePlugin):
    name = "observador_internet"
    description = "Verifica atualizações de bibliotecas/frameworks relevantes aos seus projetos (PyPI)"
    triggers = ["atualizações de biblioteca", "novo nas bibliotecas", "observador da internet"]

    def matches(self, text: str) -> bool:
        return bool(_VERIFICAR_RE.search(text.strip()))

    def handle(self, text: str, context: dict):
        jarvis = context.get("jarvis")
        if jarvis is None:
            return Answer("Não consigo checar isso neste contexto.", Confidence.GUESS)

        from sistema import observador_internet
        try:
            novidades = observador_internet.verificar_agora(jarvis)
        except Exception as e:
            return Answer(f"Não consegui checar as atualizações agora: {e}", Confidence.GUESS)

        resumo = observador_internet.resumir(jarvis, novidades)
        return Answer(resumo, Confidence.CONFIRMED)
