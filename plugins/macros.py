"""
plugins/macros.py
====================
Lado de CHAT do sistema de macros (automacao/macros.py): salva uma
sequência de comandos sob um nome, roda tudo de uma vez, e
opcionalmente agenda pra rodar sozinho de tempos em tempos.

Cada passo é só um comando que o Ultron já sabe executar (mesma frase
que funcionaria digitada direto) -- criar uma macro não ensina nada
novo, só empacota comandos existentes numa sequência com um nome.
Rodar a macro (na hora ou agendada) executa cada passo no modo de
comando direto ("/", ver core/jarvis.py:process()), então toda regra
de segurança de sempre (confirmação pra ações destrutivas, etc.)
continua valendo passo a passo.

Comandos:
    "cria uma macro <nome>: <passo 1>, <passo 2>, <passo 3>"
    "roda a macro <nome>" / "executa a macro <nome>"
    "minhas macros" / "quais macros eu tenho"
    "apaga a macro <nome>" / "remove a macro <nome>"
    "agenda a macro <nome> a cada 30 minutos" / "... a cada 2 horas"
    "cancela o agendamento da macro <nome>"
"""

import re

from automacao import macros
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_CRIAR_RE = re.compile(r"\bcri[ae]\w*\s+uma\s+macro\s+(.+?):\s*(.+)", re.IGNORECASE)
_RODAR_RE = re.compile(r"\b(?:execut[ae]|rod[ae])\w*\s+a\s+macro\s+(.+)", re.IGNORECASE)
_LISTAR_RE = re.compile(r"\bminhas\s+macros\b|\bquais\s+macros\b|\blist[ae]\w*\s+.*\bmacros\b", re.IGNORECASE)
_REMOVER_RE = re.compile(r"\b(?:apag[ae]|remov[ae])\w*\s+a\s+macro\s+(.+)", re.IGNORECASE)
_AGENDAR_RE = re.compile(
    r"\bagend[ae]\w*\s+a\s+macro\s+(.+?)\s+a\s+cada\s+(\d+)\s*(minutos?|min|horas?|h)\b", re.IGNORECASE
)
_CANCELAR_AGENDA_RE = re.compile(
    r"\b(?:cancel[ae]|desativ[ae])\w*\s+(?:o\s+agendamento\s+d[ae]\s+)?macro\s+(.+)", re.IGNORECASE
)


def _limpar_nome(nome: str) -> str:
    return nome.strip(" ,.!?").lower()


class MacrosPlugin(BasePlugin):
    name = "macros"
    description = "Cria, roda e agenda macros: sequências de comandos existentes salvas sob um nome"
    triggers = ["macro"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _CRIAR_RE.search(t) or _AGENDAR_RE.search(t) or _CANCELAR_AGENDA_RE.search(t)
            or _REMOVER_RE.search(t) or _LISTAR_RE.search(t) or _RODAR_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()
        user_id = context["user_id"]
        jarvis = context.get("jarvis")

        m = _AGENDAR_RE.search(t)
        if m:
            return self._agendar(jarvis, user_id, m.group(1), int(m.group(2)), m.group(3))

        m = _CANCELAR_AGENDA_RE.search(t)
        if m:
            return self._cancelar_agendamento(user_id, _limpar_nome(m.group(1)))

        m = _REMOVER_RE.search(t)
        if m:
            return self._remover(user_id, _limpar_nome(m.group(1)))

        if _LISTAR_RE.search(t):
            return self._listar(user_id)

        m = _CRIAR_RE.search(t)
        if m:
            return self._criar(user_id, m.group(1), m.group(2))

        m = _RODAR_RE.search(t)
        if m:
            return self._rodar(jarvis, user_id, _limpar_nome(m.group(1)))

        return None

    def _criar(self, user_id: str, nome: str, passos_texto: str):
        nome = _limpar_nome(nome)
        if not nome:
            return Answer("Preciso de um nome pra macro. Ex: 'cria uma macro boa noite: ...'.", Confidence.GUESS)
        passos = [p.strip() for p in re.split(r"[,;]", passos_texto) if p.strip()]
        if not passos:
            return Answer(
                "Liste os passos separados por vírgula. Ex: 'cria uma macro boa noite: "
                "fecha o chrome, muta o som, diminui o brilho'.",
                Confidence.GUESS,
            )
        try:
            macro = macros.criar_macro(user_id, nome, passos)
        except ValueError as e:
            return Answer(str(e), Confidence.GUESS)
        lista = "\n".join(f"{i+1}. {p}" for i, p in enumerate(macro["passos"]))
        return Answer(
            f"Macro '{nome}' salva com {len(macro['passos'])} passo(s):\n{lista}\n\n"
            f'Diga "roda a macro {nome}" pra executar, ou "agenda a macro {nome} a cada 30 '
            'minutos" pra rodar sozinha.',
            Confidence.CONFIRMED,
        )

    def _rodar(self, jarvis, user_id: str, nome: str):
        if jarvis is None:
            return Answer("Não consegui acessar o Ultron pra rodar a macro agora.", Confidence.GUESS)
        try:
            respostas = macros.executar_macro(jarvis, user_id, nome)
        except ValueError as e:
            return Answer(str(e), Confidence.GUESS)
        macro = macros.obter_macro(user_id, nome)
        linhas = [f'{i+1}. "{p}" -> {r}' for i, (p, r) in enumerate(zip(macro["passos"], respostas))]
        return Answer(f"Rodei a macro '{nome}':\n" + "\n".join(linhas), Confidence.CONFIRMED)

    def _listar(self, user_id: str):
        lista = macros.listar_macros(user_id)
        if not lista:
            return Answer(
                "Você ainda não tem nenhuma macro. Crie uma com 'cria uma macro <nome>: "
                "<passo 1>, <passo 2>'.",
                Confidence.CONFIRMED,
            )
        linhas = []
        for m in lista:
            agenda = f" (agendada a cada {m['intervalo_segundos']}s)" if m.get("intervalo_segundos") else ""
            linhas.append(f"- {m['nome']}{agenda}: {', '.join(m['passos'])}")
        return Answer("Suas macros:\n" + "\n".join(linhas), Confidence.CONFIRMED)

    def _remover(self, user_id: str, nome: str):
        if macros.remover_macro(user_id, nome):
            return Answer(f"Removi a macro '{nome}'.", Confidence.CONFIRMED)
        return Answer(f"Não encontrei nenhuma macro chamada '{nome}'.", Confidence.GUESS)

    def _agendar(self, jarvis, user_id: str, nome: str, quantidade: int, unidade: str):
        nome = _limpar_nome(nome)
        if jarvis is None:
            return Answer("Não consegui acessar o Ultron pra agendar a macro agora.", Confidence.GUESS)
        segundos = quantidade * (3600 if unidade.startswith(("hora", "h")) else 60)
        if segundos < 60:
            return Answer("O menor intervalo pra agendar uma macro é 1 minuto.", Confidence.GUESS)
        try:
            macros.agendar_macro(jarvis, user_id, nome, segundos)
        except ValueError as e:
            return Answer(str(e), Confidence.GUESS)
        return Answer(
            f"Agendei a macro '{nome}' pra rodar sozinha a cada {quantidade} {unidade}. "
            f'Diga "cancela o agendamento da macro {nome}" pra parar.',
            Confidence.CONFIRMED,
        )

    def _cancelar_agendamento(self, user_id: str, nome: str):
        if macros.cancelar_agendamento(user_id, nome):
            return Answer(f"Cancelei o agendamento da macro '{nome}'.", Confidence.CONFIRMED)
        return Answer(f"A macro '{nome}' não tinha nenhum agendamento ativo.", Confidence.GUESS)
