"""
plugins/modo_autonomo.py
============================
Comandos de chat pro "Modo Autônomo" (automacao/modo_autonomo.py):
cadastrar objetivos, ligar/desligar, ver o que está pendente/já rodou.

Exemplos:
    "ativa o modo autônomo" / "desativa o modo autônomo"
    "novo objetivo autônomo: organiza meus arquivos de downloads"
    "meus objetivos autônomos" / "objetivos pendentes"
    "remove o objetivo autônomo 3"
    "executa o próximo objetivo autônomo" -- roda AGORA, sem esperar o ócio
    "histórico do modo autônomo"
"""

import re

from config.settings import get_settings
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_ATIVAR_RE = re.compile(r"\b(ativ[ae]|lig[ae])\w*\s+.*\bmodo\s+aut[ôo]nomo\b", re.IGNORECASE)
_DESATIVAR_RE = re.compile(r"\b(desativ[ae]|deslig[ae])\w*\s+.*\bmodo\s+aut[ôo]nomo\b", re.IGNORECASE)
_NOVO_OBJETIVO_RE = re.compile(
    r"\b(?:novo\s+objetivo\s+aut[ôo]nomo|objetivo\s+aut[ôo]nomo\s+novo|cadastra\w*\s+(?:o\s+)?objetivo)"
    r"\s*:?\s*(.+)",
    re.IGNORECASE,
)
# Bare trigger (sem exigir conteúdo capturado depois) -- cobre "novo
# objetivo autônomo:" seguido só de espaço/nada, onde _NOVO_OBJETIVO_RE
# não tem o que capturar em (.+) e simplesmente não bate (mesmo padrão
# de _TRIGGER_VAZIO_RE em plugins/modo_automatico.py).
_NOVO_OBJETIVO_VAZIO_RE = re.compile(
    r"\bnovo\s+objetivo\s+aut[ôo]nomo\b|\bobjetivo\s+aut[ôo]nomo\s+novo\b|\bcadastra\w*\s+(?:o\s+)?objetivo\b",
    re.IGNORECASE,
)
_LISTAR_RE = re.compile(
    r"\b(?:meus\s+)?objetivos\s+(?:aut[ôo]nomos|pendentes)\b", re.IGNORECASE
)
_REMOVER_RE = re.compile(r"\bremov\w*\s+(?:o\s+)?objetivo\s+aut[ôo]nomo\s+(\d+)", re.IGNORECASE)
_EXECUTAR_AGORA_RE = re.compile(
    r"\bexecut\w*\s+(?:o\s+)?pr[óo]ximo\s+objetivo\s+aut[ôo]nomo\b", re.IGNORECASE
)
_HISTORICO_RE = re.compile(r"\bhist[óo]rico\s+d[oe]\s+modo\s+aut[ôo]nomo\b", re.IGNORECASE)


class ModoAutonomoPlugin(BasePlugin):
    name = "modo_autonomo"
    description = "Liga/desliga o Modo Autônomo, cadastra objetivos e mostra o que já foi feito sozinho"
    triggers = [
        "modo autônomo", "modo autonomo", "objetivo autônomo", "objetivo autonomo",
        "objetivos autônomos", "objetivos pendentes",
    ]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _ATIVAR_RE.search(t) or _DESATIVAR_RE.search(t) or _NOVO_OBJETIVO_RE.search(t)
            or _NOVO_OBJETIVO_VAZIO_RE.search(t)
            or _LISTAR_RE.search(t) or _REMOVER_RE.search(t) or _EXECUTAR_AGORA_RE.search(t)
            or _HISTORICO_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()
        user_id = context["user_id"]

        if _ATIVAR_RE.search(t):
            return self._alternar(True)
        if _DESATIVAR_RE.search(t):
            return self._alternar(False)

        if _HISTORICO_RE.search(t):
            return self._historico(user_id)

        if _EXECUTAR_AGORA_RE.search(t):
            return self._executar_agora(context)

        m = _REMOVER_RE.search(t)
        if m:
            return self._remover(user_id, int(m.group(1)))

        if _LISTAR_RE.search(t):
            return self._listar(user_id)

        m = _NOVO_OBJETIVO_RE.search(t)
        if m:
            return self._cadastrar(user_id, m.group(1))
        if _NOVO_OBJETIVO_VAZIO_RE.search(t):
            return self._cadastrar(user_id, "")

        return None

    def _alternar(self, ligar: bool):
        settings = get_settings()
        settings.set("personalidade.modo_autonomo", ligar)
        settings.save()
        if ligar:
            minutos = settings.get("personalidade.modo_autonomo_ociosidade_minutos", 5)
            return Answer(
                f"Modo Autônomo ativado. Quando o PC ficar {minutos} minuto(s) sem uso, eu pego o "
                'próximo objetivo pendente e executo sozinho -- diga "novo objetivo autônomo: <o quê>" '
                "pra cadastrar o que devo fazer. Continuo respeitando as mesmas confirmações de sempre "
                "pra qualquer ação destrutiva.",
                Confidence.CONFIRMED,
            )
        return Answer("Modo Autônomo desativado -- não vou mais trabalhar sozinho no ócio.", Confidence.CONFIRMED)

    def _cadastrar(self, user_id: str, objetivo: str):
        objetivo = objetivo.strip(" :.!?")
        if not objetivo:
            return Answer("Qual é o objetivo?", Confidence.GUESS)
        from automacao import modo_autonomo
        try:
            item = modo_autonomo.adicionar_objetivo(user_id, objetivo)
        except ValueError as e:
            return Answer(str(e), Confidence.GUESS)
        ligado = get_settings().get("personalidade.modo_autonomo", False)
        aviso = "" if ligado else ' (o Modo Autônomo está DESLIGADO agora -- diga "ativa o modo autônomo" pra eu trabalhar sozinho nisso)'
        return Answer(
            f'Cadastrado (#{item["id"]}): "{item["objetivo"]}".{aviso}',
            Confidence.CONFIRMED,
        )

    def _listar(self, user_id: str):
        from automacao import modo_autonomo
        pendentes = modo_autonomo.listar_objetivos(user_id)
        if not pendentes:
            return Answer(
                'Nenhum objetivo pendente. Diga "novo objetivo autônomo: <o quê>" pra cadastrar um.',
                Confidence.CONFIRMED,
            )
        linhas = [f'#{p["id"]}: {p["objetivo"]}' for p in pendentes]
        return Answer("Objetivos pendentes:\n" + "\n".join(linhas), Confidence.CONFIRMED)

    def _remover(self, user_id: str, objetivo_id: int):
        from automacao import modo_autonomo
        if modo_autonomo.remover_objetivo(user_id, objetivo_id):
            return Answer(f"Removi o objetivo #{objetivo_id}.", Confidence.CONFIRMED)
        return Answer(f"Não achei o objetivo #{objetivo_id}.", Confidence.GUESS)

    def _executar_agora(self, context: dict):
        jarvis = context.get("jarvis")
        if jarvis is None or jarvis.ia_manager is None:
            return Answer(
                "Preciso de um provedor de IA configurado pra planejar e executar objetivos.",
                Confidence.GUESS,
            )
        from automacao import modo_autonomo
        resultado = modo_autonomo.executar_proximo_objetivo(jarvis)
        if not resultado.get("objetivo"):
            return Answer("Não há nenhum objetivo pendente pra executar.", Confidence.CONFIRMED)
        return Answer(
            f'Executei "{resultado["objetivo"]}" -- {resultado["resumo"]}',
            Confidence.CONFIRMED,
        )

    def _historico(self, user_id: str):
        from core.memory import Memory
        memory = Memory()
        eventos = memory.events_by_type("modo_autonomo_ciclo", limit=10)
        if not eventos:
            return Answer("O Modo Autônomo ainda não executou nada.", Confidence.CONFIRMED)
        linhas = [f"{e['timestamp'][:16]} -- {e['description']}" for e in reversed(eventos)]
        return Answer("Últimas execuções do Modo Autônomo:\n" + "\n".join(linhas), Confidence.CONFIRMED)
