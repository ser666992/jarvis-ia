"""
plugins/redcore.py
=====================
Comandos de chat pro RedCore (gui/redcore.py) -- o navegador do
próprio Ultron, com acesso à internet inteira, que registra o que você
navega (pedido explícito do usuário) e pode ser esquecido a qualquer
momento.

Comandos:
    "abre o redcore" -> abre a janela do navegador (processo próprio)
    "o que eu vi hoje" / "meu histórico do redcore" -> lista navegação recente
    "o que eu vi sobre X" -> busca no histórico
    "apaga o histórico do redcore" / "esquece minha navegação" -> limpa tudo
"""

import re
import subprocess
import sys

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_ABRIR_RE = re.compile(r"\babr[ae]\w*\s+(?:o\s+)?redcore\b", re.IGNORECASE)
_HISTORICO_HOJE_RE = re.compile(
    r"\bo\s+que\s+(?:eu\s+)?vi\s+hoje\b|\bmeu\s+hist[óo]rico\s+d[eo]\s+redcore\b|"
    r"\bhist[óo]rico\s+d[eo]\s+redcore\b",
    re.IGNORECASE,
)
_HISTORICO_BUSCA_RE = re.compile(r"\bo\s+que\s+(?:eu\s+)?vi\s+sobre\s+(.+)", re.IGNORECASE)
_LIMPAR_RE = re.compile(
    r"\bapag[ae]\w*\s+(?:o\s+)?hist[óo]rico\s+d[eo]\s+redcore\b|"
    r"\besque[çc]\w*\s+(?:a\s+)?minha\s+navega[çc][ãa]o\b",
    re.IGNORECASE,
)


class RedCorePlugin(BasePlugin):
    name = "redcore"
    description = "Abre o RedCore (navegador do Ultron) e consulta/limpa o histórico de navegação registrado"
    triggers = ["abre o redcore", "histórico do redcore", "vi sobre", "minha navegação"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _ABRIR_RE.search(t) or _HISTORICO_HOJE_RE.search(t)
            or _HISTORICO_BUSCA_RE.search(t) or _LIMPAR_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()
        user_id = context["user_id"]

        if _ABRIR_RE.search(t):
            return self._abrir(user_id)
        if _LIMPAR_RE.search(t):
            return self._limpar(user_id)
        if _HISTORICO_HOJE_RE.search(t):
            return self._historico_hoje(user_id)
        m = _HISTORICO_BUSCA_RE.search(t)
        if m:
            return self._buscar(user_id, m.group(1).strip(" ?.!"))
        return None

    def _abrir(self, user_id: str):
        try:
            subprocess.Popen([sys.executable, "-m", "gui.redcore", user_id])
        except Exception as e:
            return Answer(f"Não consegui abrir o RedCore: {e}", Confidence.GUESS)
        return Answer(
            "Abrindo o RedCore -- é uma janela própria, pode levar alguns segundos pra aparecer.",
            Confidence.CONFIRMED,
        )

    def _historico_hoje(self, user_id: str):
        from automacao import redcore_historico
        visitas = redcore_historico.historico_de_hoje(user_id)
        if not visitas:
            return Answer("Ainda não registrei nenhuma navegação sua hoje no RedCore.", Confidence.CONFIRMED)
        linhas = [f"- {v['titulo'] or v['url']} ({v['visitado_em'][11:16]})" for v in visitas[:20]]
        return Answer("O que você viu hoje no RedCore:\n" + "\n".join(linhas), Confidence.CONFIRMED)

    def _buscar(self, user_id: str, termo: str):
        if not termo:
            return Answer("Sobre o que você quer buscar no seu histórico?", Confidence.GUESS)
        from automacao import redcore_historico
        resultados = redcore_historico.buscar_historico(user_id, termo)
        if not resultados:
            return Answer(f"Não achei nada sobre '{termo}' no seu histórico do RedCore.", Confidence.GUESS)
        linhas = [f"- {v['titulo'] or v['url']} ({v['visitado_em'][:10]})" for v in resultados]
        return Answer(f"Sobre '{termo}', você viu:\n" + "\n".join(linhas), Confidence.SINGLE_SOURCE)

    def _limpar(self, user_id: str):
        from automacao import redcore_historico
        total = redcore_historico.limpar_historico(user_id)
        if total == 0:
            return Answer("Já não havia nada no histórico do RedCore.", Confidence.CONFIRMED)
        return Answer(f"Apaguei {total} visita(s) do histórico do RedCore.", Confidence.CONFIRMED)
