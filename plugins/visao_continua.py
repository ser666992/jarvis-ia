"""
plugins/visao_continua.py
============================
Lado de chat do Módulo 1 (visao_continua/): ligar/desligar o
acompanhamento contínuo da tela, e perguntar o que ele está vendo
agora. Diferente de plugins/observation.py (comentário falado, sob
pedido pontual) -- aqui é consultar o ESTADO estruturado que já está
sendo mantido em segundo plano.

Comandos:
    "liga a visão contínua" / "ativa a visão contínua"
    "desliga a visão contínua" / "para a visão contínua"
    "o que está acontecendo na minha tela" / "o que você está vendo agora"
"""

import re

from config.settings import get_settings
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_LIGAR_RE = re.compile(
    r"\b(lig[ae]|ativ[ae])\w*\s+.*\bvis[aã]o\s+cont[ií]nua\b|"
    # "assiste (a) minha tela"/"observa a tela" -- fraseado natural que o
    # usuário realmente usa pra pedir isso (reclamação real: "a função de
    # assistir tela não funciona" quando só o fraseado não batia).
    r"\b(?:assist[ae]|observ[ae])\w*\s+(?:a\s+|minha\s+)*tela\b",
    re.IGNORECASE,
)
_DESLIGAR_RE = re.compile(
    r"\b(deslig[ae]|desativ[ae]|par[ae])\w*\s+.*\bvis[aã]o\s+cont[ií]nua\b|"
    r"\bpar[ae]\w*\s+de\s+(?:assistir|observar)\s+(?:a\s+|minha\s+)*tela\b",
    re.IGNORECASE,
)
_CONSULTAR_RE = re.compile(
    r"\bo\s+que\s+(?:est[aá]\s+acontecendo|voc[eê]\s+(?:est[aá]\s+)?v[eê]|t[aá]\s+rolando|t[aá]\s+acontecendo)\b.*\btela\b",
    re.IGNORECASE,
)


class VisaoContinuaPlugin(BasePlugin):
    name = "visao_continua"
    description = "Liga/desliga o acompanhamento contínuo da tela e mostra o que está sendo observado agora"
    triggers = ["visão contínua", "visao continua", "acontecendo na minha tela", "vendo agora"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_LIGAR_RE.search(t) or _DESLIGAR_RE.search(t) or _CONSULTAR_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()
        if _LIGAR_RE.search(t):
            return self._ligar(context.get("jarvis"))
        if _DESLIGAR_RE.search(t):
            return self._desligar()
        if _CONSULTAR_RE.search(t):
            return self._consultar()
        return None

    def _ligar(self, jarvis=None):
        import visao_continua
        try:
            visao_continua.ligar(jarvis)
        except Exception as e:
            return Answer(f"Não consegui ligar a visão contínua: {e}", Confidence.GUESS)
        settings = get_settings()
        settings.set("visao_continua.ativa", True)
        settings.save()
        return Answer(
            "Visão contínua ligada -- vou acompanhar sua tela em segundo plano (só reprocesso "
            "quando algo muda de verdade, pra não gastar CPU à toa) e você pode me perguntar "
            '"o que está acontecendo na minha tela" a qualquer momento. Diga "desliga a visão '
            'contínua" quando quiser parar.',
            Confidence.CONFIRMED,
        )

    def _desligar(self):
        import visao_continua
        parou = visao_continua.parar()
        settings = get_settings()
        settings.set("visao_continua.ativa", False)
        settings.save()
        if parou:
            return Answer("Visão contínua desligada.", Confidence.CONFIRMED)
        return Answer("A visão contínua já estava desligada.", Confidence.CONFIRMED)

    def _consultar(self):
        import visao_continua
        if not visao_continua.ativo():
            return Answer(
                'A visão contínua está desligada agora -- diga "liga a visão contínua" pra eu '
                "começar a acompanhar.",
                Confidence.GUESS,
            )
        obs = visao_continua.estado_atual()
        if not obs:
            return Answer(
                "Ainda não tive tempo de observar nada -- tenta de novo em alguns segundos.",
                Confidence.GUESS,
            )
        linhas = [f"Janela em foco: {obs.get('janela') or 'desconhecida'}"]
        if obs.get("processo"):
            linhas.append(f"Processo: {obs['processo']}")
        if obs.get("texto_tela"):
            linhas.append(f"Texto visível: {obs['texto_tela'][:300]}")
        if obs.get("eventos"):
            linhas.append("Eventos recentes: " + ", ".join(obs["eventos"]))
        return Answer("\n".join(linhas), Confidence.CONFIRMED)
