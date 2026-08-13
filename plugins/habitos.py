"""
plugins/habitos.py
=====================
"Analisa hábitos no computador" -- ver automacao/habitos.py (amostragem
periódica de app/janela em primeiro plano, acumulada em data/jarvis.db).
Diferente da timeline (eventos pontuais): isto é uma CONTAGEM agregada
de uso ao longo de dias.

Comandos:
    "quais são meus hábitos" / "analisa meus hábitos no computador"
"""

import re

from automacao import habitos
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_HABITOS_RE = re.compile(r"\bh[aá]bitos?\b", re.IGNORECASE)


class HabitosPlugin(BasePlugin):
    name = "habitos"
    description = "Analisa hábitos de uso (apps mais usados) no PC"
    triggers = ["hábitos", "habitos"]

    def matches(self, text: str) -> bool:
        return bool(_HABITOS_RE.search(text))

    def handle(self, text: str, context: dict):
        return Answer(habitos.resumo("pc"), Confidence.CONFIRMED)
