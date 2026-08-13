"""
plugins/timeline.py
======================
"Linha do tempo de tudo que aconteceu no pc" -- junta os eventos que os
outros módulos registram (abrir/fechar programa, lembretes, habilidades
criadas/aprovadas, janelas controladas, logins usados, correções
automáticas, comentários sobre a tela, etc., ver core/timeline.py) numa
lista cronológica.

Comandos:
    "linha do tempo" / "o que aconteceu hoje" -> hoje
    "linha do tempo de ontem" / "o que aconteceu ontem" -> ontem
    "linha do tempo da semana" / "o que aconteceu essa semana" -> últimos 7 dias
"""

import re
from datetime import datetime, timedelta

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from core.timeline import formatar_linha_do_tempo

_TIMELINE_RE = re.compile(
    r"\blinha do tempo\b|\bo que (?:aconteceu|eu fiz|rolou)\b", re.IGNORECASE
)
_ONTEM_RE = re.compile(r"\bontem\b", re.IGNORECASE)
_SEMANA_RE = re.compile(r"\bsemana\b", re.IGNORECASE)


class TimelinePlugin(BasePlugin):
    name = "timeline"
    description = "Linha do tempo de tudo que aconteceu no PC (apps, lembretes, habilidades, etc.)"
    triggers = ["linha do tempo", "o que aconteceu", "o que eu fiz hoje", "o que eu fiz ontem", "o que rolou"]

    def matches(self, text: str) -> bool:
        return bool(_TIMELINE_RE.search(text.lower()))

    def handle(self, text: str, context: dict):
        t = text.lower()
        memory = context["memory"]
        agora = datetime.now()

        if _SEMANA_RE.search(t):
            desde = agora - timedelta(days=7)
            rotulo_periodo = "nos últimos 7 dias"
        elif _ONTEM_RE.search(t):
            ontem = agora - timedelta(days=1)
            desde = ontem.replace(hour=0, minute=0, second=0, microsecond=0)
            rotulo_periodo = "ontem"
        else:
            desde = agora.replace(hour=0, minute=0, second=0, microsecond=0)
            rotulo_periodo = "hoje"

        texto = formatar_linha_do_tempo(memory, desde)
        return Answer(f"Linha do tempo ({rotulo_periodo}):\n{texto}", Confidence.CONFIRMED)
