"""
plugins/controle_pc.py
=========================
Lado de chat do Módulo 2 (controle_pc/): os comandos com valor real de
serem digitados diretamente (rodar um comando de sistema, organizar
janelas, clicar num elemento por nome). A maior parte da API do
controle_pc/ é pensada pra ser chamada por OUTRO código (plugins,
skill_forge, uma futura lógica de decisão) -- não faz sentido expor
"mover mouse pra x,y" como comando de chat, por exemplo.

Comandos:
    "executa o comando <cmd> no terminal, confirmo"
    "organiza minhas janelas" / "organiza as janelas em cascata"
    "clica no botão <nome>" / "clica em <nome>"
"""

import re

from core.confidence import Answer, Confidence
from seguranca.permissions import PermissionDenied, confirmado_pela_frase_ou_config
from core.plugin_manager import BasePlugin

_COMANDO_RE = re.compile(
    r"\b(execut[ae]|rod[ae])\w*\s+o\s+comando\s+(.+?)\s+no\s+terminal\b(.*)$",
    re.IGNORECASE,
)
_ORGANIZAR_RE = re.compile(
    r"\borganiz[ae]\w*\s+(?:minhas\s+|as\s+)?janelas\b(?:\s+em\s+(grade|cascata))?",
    re.IGNORECASE,
)
_CLICAR_RE = re.compile(r"\bclic[ae]\w*\s+(?:no|na|em)\s+(?:bot[aã]o\s+)?(.+)", re.IGNORECASE)
_CONFIRM_WORD_RE = re.compile(r"\bconfirmo\b", re.IGNORECASE)


class ControlePCPlugin(BasePlugin):
    name = "controle_pc"
    description = "Roda comandos de sistema (com confirmação), organiza janelas, clica em elementos por nome"
    triggers = ["no terminal", "organiza as janelas", "organiza minhas janelas", "clica no botão", "clica em"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_COMANDO_RE.search(t) or _ORGANIZAR_RE.search(t) or _CLICAR_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()

        m = _COMANDO_RE.search(t)
        if m:
            comando = m.group(2).strip(" ,.!?")
            confirmado = confirmado_pela_frase_ou_config(bool(_CONFIRM_WORD_RE.search(t)))
            return self._executar_comando(comando, confirmado)

        m = _ORGANIZAR_RE.search(t)
        if m:
            modo = (m.group(1) or "grade").lower()
            return self._organizar(modo)

        m = _CLICAR_RE.search(t)
        if m:
            alvo = _CONFIRM_WORD_RE.sub("", m.group(1)).strip(" ,.!?")
            return self._clicar(alvo)

        return None

    def _executar_comando(self, comando: str, confirmado: bool):
        if not comando:
            return Answer("Executar qual comando?", Confidence.GUESS)
        if not confirmado:
            return Answer(
                f'Rodar um comando de sistema pode fazer qualquer coisa que você faria no '
                f'terminal -- tem certeza? Diga "executa o comando {comando} no terminal, confirmo".',
                Confidence.GUESS,
            )
        import controle_pc
        try:
            resultado = controle_pc.executar_comando(comando, confirmed=True)
        except PermissionDenied as e:
            return Answer(str(e), Confidence.GUESS)
        except Exception as e:
            return Answer(f"Não consegui executar: {e}", Confidence.GUESS)
        if resultado.get("timeout"):
            return Answer(f'O comando "{comando}" excedeu o tempo limite e foi encerrado.', Confidence.GUESS)
        saida = (resultado["stdout"] or resultado["stderr"] or "(sem saída)").strip()
        return Answer(
            f'Comando executado (código {resultado["returncode"]}):\n{saida[:1000]}',
            Confidence.CONFIRMED,
        )

    def _organizar(self, modo: str):
        import controle_pc
        try:
            n = controle_pc.organizar_janelas(modo=modo)
        except Exception as e:
            return Answer(f"Não consegui organizar as janelas: {e}", Confidence.GUESS)
        if n == 0:
            return Answer("Não encontrei nenhuma janela visível pra organizar.", Confidence.CONFIRMED)
        return Answer(f"Organizei {n} janela(s) em {modo}.", Confidence.CONFIRMED)

    def _clicar(self, alvo: str):
        if not alvo:
            return Answer("Clicar em quê?", Confidence.GUESS)
        import controle_pc
        try:
            achou = controle_pc.clicar_elemento(texto=alvo)
        except Exception as e:
            return Answer(f"Não consegui clicar: {e}", Confidence.GUESS)
        if not achou:
            return Answer(f'Não encontrei nenhum elemento chamado "{alvo}" na janela em foco.', Confidence.GUESS)
        return Answer(f'Cliquei em "{alvo}".', Confidence.CONFIRMED)
