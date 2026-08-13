"""Comandos de chat para o Motor de Missões."""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_CREATE = re.compile(r"\b(?:nova|cria|inicia)\s+miss[aã]o\s*:?\s*(.+)", re.IGNORECASE)
_LIST = re.compile(r"\b(?:minhas|lista(?:r)?)\s+miss[õo]es\b", re.IGNORECASE)
_RUN = re.compile(r"\b(?:executa|continua|retoma)\s+(?:a\s+)?miss[aã]o\s+(\d+)", re.IGNORECASE)
_APPROVE = re.compile(
    r"\baprova\s+(?:o\s+)?passo\s+(\d+)\s+da\s+miss[aã]o\s+(\d+)", re.IGNORECASE)
_PAUSE = re.compile(r"\b(pausa|cancela)\s+(?:a\s+)?miss[aã]o\s+(\d+)", re.IGNORECASE)


class MissoesPlugin(BasePlugin):
    name = "missoes"
    description = "Missões persistentes: planeja, executa, verifica, pausa e retoma objetivos"
    triggers = ["nova missão", "minhas missões", "executa missão", "aprova passo"]

    def matches(self, text):
        return any(regex.search(text) for regex in (_CREATE, _LIST, _RUN, _APPROVE, _PAUSE))

    def handle(self, text, context):
        from automacao import missoes
        user_id = context["user_id"]
        match = _APPROVE.search(text)
        if match:
            item = missoes.aprovar_passo(user_id, int(match.group(2)), int(match.group(1)))
            return Answer(
                "Passo aprovado e missão pronta para continuar." if item
                else "Não encontrei essa missão ou passo.",
                Confidence.CONFIRMED if item else Confidence.GUESS)
        match = _PAUSE.search(text)
        if match:
            item = (missoes.cancelar if match.group(1).lower().startswith("cancel")
                    else missoes.pausar)(user_id, int(match.group(2)))
            return Answer("Missão atualizada." if item else "Missão não encontrada.",
                          Confidence.CONFIRMED if item else Confidence.GUESS)
        match = _RUN.search(text)
        if match:
            mission_id = int(match.group(1))
            if text.strip().lower().startswith("retoma"):
                missoes.pausar(user_id, mission_id, pausada=False)
            result = missoes.executar_ate_parar(context["jarvis"], mission_id)
            mission = result["missao"]
            if not mission:
                return Answer("Missão não encontrada.", Confidence.GUESS)
            last = result["resultados"][-1]
            return Answer(
                f"Missão #{mission['id']}: {mission['status']}. "
                f"Último resultado: {last.get('evidencia') or last.get('motivo')}.",
                Confidence.CONFIRMED)
        if _LIST.search(text):
            items = missoes.listar(user_id)
            if not items:
                return Answer("Não há missões ativas.", Confidence.CONFIRMED)
            return Answer("Missões:\n" + "\n".join(
                f"#{m['id']} [{m['status']}] {m['objetivo']} "
                f"({sum(p['status'] == 'concluido' for p in m['passos'])}/{len(m['passos'])})"
                for m in items), Confidence.CONFIRMED)
        match = _CREATE.search(text)
        if match:
            try:
                mission = missoes.criar(context["jarvis"], match.group(1).strip())
            except ValueError as error:
                return Answer(str(error), Confidence.GUESS)
            high = sum(p["risco"] == "alto" for p in mission["passos"])
            return Answer(
                f"Missão #{mission['id']} criada com {len(mission['passos'])} passos "
                f"({high} exige(m) aprovação). Diga “executa missão {mission['id']}”.",
                Confidence.CONFIRMED)
