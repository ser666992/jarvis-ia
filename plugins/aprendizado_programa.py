"""
plugins/aprendizado_programa.py
===================================
"Observa como eu uso um programa e aprende a utilizá-lo" -- ver
automacao/aprendizado_programa.py.

Comandos:
    "observa como eu uso o excel" / "me observa usando o word" ->
    começa a observar (janela + texto na tela, a cada 15s)
    "para de aprender o excel" / "já aprendeu o excel" -> encerra e
    gera o resumo/tutorial, salvo na base de conhecimento
"""

import re

from automacao import aprendizado_programa
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_START_RE = re.compile(
    # Artigo "o"/"a" agora opcional (nomes de programa estrangeiros
    # raramente vêm com artigo -- "observa como eu uso photoshop").
    # IMPORTANTE: o artigo e o espaço seguinte são um grupo só,
    # opcional em conjunto -- (?:o|a)\s+ -- nunca (?:o|a)?\s*
    # separado, senão "a" sozinho (sem exigir o espaço depois) casaria
    # com a PRIMEIRA LETRA de nomes que começam com "a" (ex.: "uso
    # adobe" virava capturar só "dobe").
    r"\bobserv[ae]\w*\s+como\s+eu\s+uso\s+(?:(?:o|a)\s+)?(.+)|"
    r"\bme\s+observ[ae]\w*\s+usando\s+(?:(?:o|a)\s+)?(.+)",
    re.IGNORECASE,
)
_STOP_RE = re.compile(
    r"\bencerra\w*\s+o\s+aprendizado\s+d[eo]\s+(.+)|"
    r"\bpar[ae]\w*\s+de\s+aprender\s+(?:(?:o|a)\s+)?(.+)|"
    r"\bj[aá]\s+aprendeu\s+(?:o\s+suficiente\s+)?(?:sobre\s+)?(?:(?:o|a)\s+)?(.+)",
    re.IGNORECASE,
)


class AprendizadoProgramaPlugin(BasePlugin):
    name = "aprendizado_programa"
    description = "Observa como você usa um programa e aprende a descrever como usá-lo"
    triggers = ["observa como eu uso", "me observa usando", "para de aprender", "já aprendeu"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_START_RE.search(t) or _STOP_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()

        m = _STOP_RE.search(t)
        if m:
            nome = next((g for g in m.groups() if g), None)
            return self._parar(nome, context)

        m = _START_RE.search(t)
        if m:
            nome = next((g for g in m.groups() if g), None)
            return self._iniciar(nome)

        return None

    def _iniciar(self, nome_programa: str):
        nome_programa = (nome_programa or "").strip(" ?.!")
        if not nome_programa:
            return Answer("Observar o uso de qual programa?", Confidence.GUESS)
        aprendizado_programa.iniciar_observacao(nome_programa)
        return Answer(
            f'Combinado, vou observar como você usa "{nome_programa}" (a cada 15s, até 20 '
            f'minutos). Diga "para de aprender {nome_programa}" quando terminar, que eu resumo '
            "o que vi num tutorial.",
            Confidence.CONFIRMED,
        )

    def _parar(self, nome_programa: str, context: dict):
        nome_programa = (nome_programa or "").strip(" ?.!")
        if not nome_programa:
            return Answer("Parar de aprender qual programa?", Confidence.GUESS)
        if not aprendizado_programa.em_observacao(nome_programa):
            return None  # não tinha observação ativa -- deixa outro plugin tentar (ex.: observation.py)
        mensagem = aprendizado_programa.parar_e_aprender(
            nome_programa, context.get("ia_manager"), context["knowledge"], context["user_id"],
        )
        return Answer(mensagem, Confidence.RELIABLE_SOURCE)
