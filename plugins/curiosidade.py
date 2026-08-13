"""
plugins/curiosidade.py
=========================
Lado de chat do Sistema de Curiosidade/Previsão (sistema/curiosidade.py):
pergunta ao Ultron se ele notou algo estranho ou que valha a pena se
preocupar, a partir dos dados reais que ele coleta (uso de hardware ao
longo do tempo + linha do tempo de eventos).

Honestidade: são observações estatísticas sobre dados reais
(tendência de disco/RAM, repetições na timeline), não previsão mágica
de bugs/travamentos. Precisa de dados acumulados ao longo do tempo pra
ter o que dizer.

Comandos:
    "notou algo?" / "tem algo estranho?" / "alguma curiosidade?"
    "tem algo pra eu me preocupar?" / "previsão do sistema"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_RE = re.compile(
    r"\bnotou\s+algo\b|\bpercebeu\s+algo\b|\balgo\s+estranho\b|\balguma\s+curiosidade\b|"
    r"\bcuriosidades?\b|\bprevis[ãa]o\s+d[oe]\s+sistema\b|"
    r"\balgo\s+(?:pra|para)\s+(?:eu\s+)?me\s+preocupar\b|\btem\s+algo\s+errado\b",
    re.IGNORECASE,
)


class CuriosidadePlugin(BasePlugin):
    name = "curiosidade"
    description = "Reporta padrões/anomalias reais que o Ultron notou (tendência de disco/RAM, erros recorrentes na timeline)"
    triggers = ["notou algo", "algo estranho", "alguma curiosidade", "previsão do sistema", "me preocupar"]

    def matches(self, text: str) -> bool:
        return bool(_RE.search(text.strip()))

    def handle(self, text: str, context: dict):
        from sistema import curiosidade
        try:
            findings = curiosidade.analisar()
        except Exception as e:
            return Answer(f"Tentei analisar, mas falhou: {e}", Confidence.GUESS)
        if not findings:
            return Answer(
                "Por enquanto não notei nada digno de nota -- ou está tudo tranquilo, ou ainda não "
                "acumulei dados suficientes ao longo do tempo pra ver uma tendência (eu coleto isso "
                "aos poucos em segundo plano).",
                Confidence.CONFIRMED,
            )
        emoji = {"alta": "⚠️", "media": "•", "baixa": "·"}
        linhas = [f"{emoji.get(f['gravidade'], '•')} {f['texto']}" for f in findings]
        return Answer(
            "Coisas que notei nos seus dados (observações sobre tendências reais, não previsão "
            "mágica):\n" + "\n".join(linhas),
            Confidence.SINGLE_SOURCE,
        )
