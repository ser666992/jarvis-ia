"""
plugins/investigador.py
==========================
Lado de chat do "Investigador Universal" (investigador/analise.py):
descobre tecnologias/arquitetura/indícios a partir de um arquivo (EXE,
APK, PDF, imagem, vídeo) ou uma URL -- análise estática e passiva,
nunca executa o arquivo nem varre um site ativamente (ver limitações
honestas no README do módulo).

Comandos:
    "investiga o arquivo C:\\caminho\\app.exe"
    "analisa esse apk: C:\\caminho\\app.apk"
    "descubra tudo sobre https://exemplo.com"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_GATILHO_RE = re.compile(r"\b(?:investig[ae]\w*|analis[ae]\w*|descubr[ae]\w*|descobr[ie]\w*)\b", re.IGNORECASE)
_ALVO_RE = re.compile(r"(https?://\S+|[A-Za-z]:\\\S+|\.?/\S+\.\w+)")


class InvestigadorPlugin(BasePlugin):
    name = "investigador"
    description = "Investiga um arquivo (EXE/APK/PDF/imagem/vídeo) ou site e reporta indícios de tecnologia/arquitetura"
    triggers = ["investiga", "investigue", "descubra tudo sobre", "analisa esse arquivo", "analisa esse site"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_GATILHO_RE.search(t) and _ALVO_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()
        if not _GATILHO_RE.search(t):
            return None
        m = _ALVO_RE.search(t)
        if not m:
            return None
        alvo = m.group(1).rstrip(").,;:!?\"'")
        return self._investigar(alvo)

    def _investigar(self, alvo: str):
        import investigador
        try:
            resultado = investigador.analisar(alvo)
        except FileNotFoundError as e:
            return Answer(str(e), Confidence.GUESS)
        except Exception as e:
            return Answer(f"Não consegui investigar '{alvo}': {e}", Confidence.GUESS)
        relatorio = investigador.formatar_relatorio(alvo, resultado)
        return Answer(relatorio, Confidence.SINGLE_SOURCE)
