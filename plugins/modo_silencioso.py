"""
plugins/modo_silencioso.py
=============================
"Modo silencioso": desliga o barge-in (voz/stt.py:BargeInMonitor)
temporariamente, sem precisar reiniciar o modo de voz -- útil quando o
falso positivo do eco (sem cancelamento de eco de verdade, ver
voz/README.md) está incomodando, ou quando a pessoa só quer ouvir a
resposta inteira sem risco de cortar sozinha por engano (tossir, som
do ambiente). `voz.barge_in_ativo` já era respeitado por voz/loop.py e
gui/app.py antes deste plugin -- só faltava um jeito de ligar/desligar
por comando.

Comandos:
    "modo silencioso" / "desativa o barge-in" / "desliga a interrupção"
    "sai do modo silencioso" / "ativa o barge-in" / "liga a interrupção"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_RE_DESLIGAR = re.compile(
    r"\b(modo\s+silencioso|entra\s+.*\bsil[êe]ncio)\b|"
    r"\b(desativ[ae]|deslig[ae])\b.*\b(barge.?in|interrup[çc][ãa]o)\b",
    re.IGNORECASE,
)
_RE_LIGAR = re.compile(
    r"\b(sai|saia)\b.*\bsilencioso\b|"
    r"\b(ativ[ae]|lig[ae])\b.*\b(barge.?in|interrup[çc][ãa]o)\b",
    re.IGNORECASE,
)


class ModoSilenciosoPlugin(BasePlugin):
    name = "modo_silencioso"
    description = "Liga/desliga o barge-in (poder interromper o Jarvis falando) temporariamente"
    triggers = ["modo silencioso", "desativa o barge-in", "ativa o barge-in", "sai do modo silencioso"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_RE_DESLIGAR.search(t) or _RE_LIGAR.search(t))

    def handle(self, text: str, context: dict):
        from config.settings import get_settings
        settings = get_settings()
        t = text.strip()

        if _RE_LIGAR.search(t):
            settings.set("voz.barge_in_ativo", True)
            settings.save()
            return Answer(
                "Prontinho, saí do modo silencioso -- pode me interromper falando por cima de novo.",
                Confidence.CONFIRMED,
            )

        settings.set("voz.barge_in_ativo", False)
        settings.save()
        return Answer(
            "Modo silencioso ativado -- vou falar a resposta inteira sem parar, mesmo se você falar "
            'junto. Diga "sai do modo silencioso" pra voltar ao normal.',
            Confidence.CONFIRMED,
        )
