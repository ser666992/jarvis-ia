"""
plugins/escolher_voz.py
==========================
"Lista as vozes" / "usa a voz ...": deixa a pessoa escolher qual voz de
TTS o Jarvis usa entre as JÁ instaladas no Windows (nenhuma delas é
clonada nem imita ninguém específico -- ver voz/tts.py). Antes disso a
única forma de influenciar a voz era a preferência automática por
gênero (`personalidade.voz_robotica`); não havia como escolher UMA
específica entre várias instaladas no mesmo idioma.

Comandos:
    "lista as vozes" / "que vozes você tem" / "vozes disponíveis"
    "usa a voz <nome ou número>" / "muda a voz pra <nome ou número>"
    "usa a voz padrão" / "volta pra voz normal" (limpa a escolha manual)
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_RE_LISTAR = re.compile(r"\b(lista|listar|quais)\b.*\bvozes?\b|\bvozes?\s+dispon[ií]veis\b", re.IGNORECASE)
_RE_ESCOLHER = re.compile(
    r"\b(?:muda|mude|troca|troque|usa|use|escolhe|escolha|volta|volte)\b.*\bvoz\b\s*(?:pra|para|de\s+n[úu]mero|n[úu]mero)?\s*(.+)",
    re.IGNORECASE,
)
_PALAVRAS_RESET = {"padrão", "padrao", "original", "normal", "de sempre", "do sistema"}


class EscolherVozPlugin(BasePlugin):
    name = "escolher_voz"
    description = "Lista as vozes de TTS instaladas e troca qual delas o Jarvis usa pra falar"
    triggers = ["lista as vozes", "que vozes você tem", "usa a voz", "muda a voz"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_RE_LISTAR.search(t) or _RE_ESCOLHER.search(t))

    def handle(self, text: str, context: dict):
        from voz.tts import TextToSpeech
        tts = TextToSpeech()
        vozes = tts.listar_vozes()
        if not vozes:
            return Answer(
                "Não encontrei nenhuma voz de TTS instalada no sistema (ver requirements-voz.txt).",
                Confidence.GUESS,
            )

        m = _RE_ESCOLHER.search(text.strip())
        if m:
            return self._escolher(m.group(1).strip(" .!?"), vozes)
        return self._listar(vozes)

    def _listar(self, vozes: list):
        linhas = ["Vozes disponíveis:"]
        for i, v in enumerate(vozes, 1):
            linhas.append(f'{i}. {v["nome"]}')
        linhas.append('Diga "usa a voz <nome ou número>" pra trocar (ou "usa a voz padrão" pra voltar).')
        return Answer("\n".join(linhas), Confidence.CONFIRMED)

    def _escolher(self, alvo: str, vozes: list):
        from config.settings import get_settings
        settings = get_settings()

        if alvo.lower() in _PALAVRAS_RESET:
            settings.set("voz.voz_tts_id", "")
            settings.save()
            return Answer("Prontinho, voltei pra voz padrão do sistema.", Confidence.CONFIRMED)

        escolhida = self._resolver(alvo, vozes)
        if escolhida is None:
            return Answer(
                f'Não encontrei nenhuma voz parecida com "{alvo}". Diga "lista as vozes" pra ver as opções.',
                Confidence.GUESS,
            )
        settings.set("voz.voz_tts_id", escolhida["id"])
        settings.save()
        return Answer(f'Pronto, agora uso a voz "{escolhida["nome"]}".', Confidence.CONFIRMED)

    @staticmethod
    def _resolver(alvo: str, vozes: list):
        if alvo.isdigit():
            idx = int(alvo) - 1
            return vozes[idx] if 0 <= idx < len(vozes) else None
        alvo_low = alvo.lower()
        for v in vozes:
            if alvo_low in v["nome"].lower():
                return v
        return None
