"""
plugins/escuta_ativa.py
==========================
Lado de chat da sessão de escuta acompanhada, com tempo limitado
(automacao/escuta_ativa.py) -- a alternativa responsável ao "modo de
escuta contínua" sempre ligado que foi pedido e recusado nesta
conversa: aqui a escuta só começa com um comando explícito, dizendo
por quanto tempo, e tem hora certa pra acabar (ou pode ser encerrada
antes a qualquer momento).

Comandos:
    "escuta essa conversa por 10 minutos" / "me escuta por 5 minutos" /
    "ouve essa conversa por 15 minutos"
    "para de escutar" / "encerra a escuta" / "para a escuta"
    "o que você ouviu" / "o que foi dito na escuta" / "transcrição da escuta"
    "esquece o que você ouviu" / "descarta a escuta"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_INICIAR_RE = re.compile(
    r"\b(?:me\s+)?(?:escut[ae]\w*|ouv\w*|ou[cç]a\w*|acompanh[ae]\w*)\b.{0,40}?\bpor\s+(\d+)\s*min",
    re.IGNORECASE,
)
_PARAR_RE = re.compile(
    r"\b(?:par[ae]|encerr[ae])\w*\s+(?:de\s+)?(?:escutar|ouvir|a\s+escuta)\b",
    re.IGNORECASE,
)
_ESQUECER_RE = re.compile(
    r"\b(?:esquece|descart[ae]\w*|apag[ae]\w*)\b.{0,30}?\b(?:escuta|ouviu|escutou)\b",
    re.IGNORECASE,
)
_CONSULTAR_RE = re.compile(
    r"\bo\s+que\s+(?:voc[eê]\s+)?(?:ouviu|escutou|captou)\b|"
    r"\bo\s+que\s+foi\s+dito\s+na\s+escuta\b|"
    r"\btranscri[cç][aã]o\s+da\s+escuta\b",
    re.IGNORECASE,
)


class EscutaAtivaPlugin(BasePlugin):
    name = "escuta_ativa"
    description = "Sessão de escuta acompanhada com tempo limitado, iniciada e encerrada explicitamente pelo usuário"
    triggers = ["escuta essa conversa", "para de escutar", "o que você ouviu", "o que voce ouviu", "encerra a escuta"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _INICIAR_RE.search(t) or _PARAR_RE.search(t) or _ESQUECER_RE.search(t) or _CONSULTAR_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()
        m = _INICIAR_RE.search(t)
        if m:
            return self._iniciar(int(m.group(1)))
        if _PARAR_RE.search(t):
            return self._parar()
        if _ESQUECER_RE.search(t):
            return self._esquecer()
        if _CONSULTAR_RE.search(t):
            return self._consultar()
        return None

    def _iniciar(self, minutos: int):
        import automacao.escuta_ativa as escuta
        try:
            resultado = escuta.iniciar(minutos)
        except RuntimeError as e:
            return Answer(str(e), Confidence.GUESS)
        duracao = escuta._formatar_duracao(resultado["duracao_minutos"])
        return Answer(
            f'Começando a escutar por até {duracao} -- vou avisar quando terminar. Diga "para de '
            'escutar" a qualquer momento pra encerrar antes, ou "o que você ouviu" pra ver o que '
            "já foi transcrito.",
            Confidence.CONFIRMED,
        )

    def _parar(self):
        import automacao.escuta_ativa as escuta
        resultado = escuta.parar()
        if not resultado["parou"]:
            return Answer("Não havia nenhuma escuta ativa agora.", Confidence.GUESS)
        n = len(resultado["transcricao"])
        return Answer(
            f'Escuta encerrada. Capturei {n} trecho(s) -- pergunte "o que você ouviu" se quiser ver.',
            Confidence.CONFIRMED,
        )

    def _esquecer(self):
        import automacao.escuta_ativa as escuta
        escuta.descartar()
        return Answer("Pronto, esqueci o que tinha sido transcrito na escuta.", Confidence.CONFIRMED)

    def _consultar(self):
        import automacao.escuta_ativa as escuta
        trechos = escuta.transcricao_atual()
        if not trechos:
            if escuta.ativa():
                return Answer("Estou escutando, mas ainda não captei nada com confiança suficiente.", Confidence.GUESS)
            return Answer(
                'Nenhuma escuta ativa nem recente -- diga "escuta essa conversa por N minutos" pra começar.',
                Confidence.GUESS,
            )
        linhas = [t["texto"] for t in trechos]
        status = ""
        if escuta.ativa():
            restante = escuta.tempo_restante_segundos()
            status = f" (ainda escutando, faltam ~{restante / 60:.0f} min)"
        return Answer("O que ouvi até agora" + status + ":\n- " + "\n- ".join(linhas), Confidence.CONFIRMED)
