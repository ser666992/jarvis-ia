"""
plugins/professor.py
=======================
Modo "professor particular": explica um assunto do zero, passo a
passo, e pode te testar com uma pergunta -- usa a IA configurada com um
system prompt PRÓPRIO de professor paciente (não a persona "ultron"
padrão do Ultron, ver ia/manager.py:chat(system_prompt=...), mesmo
padrão usado por plugins/instagram.py e plugins/skill_forge.py).

Diferente de uma pergunta factual comum ("o que é fotossíntese", já
respondida por core/jarvis.py:_query_knowledge_base_first ANTES de
qualquer plugin rodar): este plugin só entra quando a intenção de
"aula"/"aprender de verdade" é explícita ("me ensina", "quero
aprender", "me dá uma aula sobre").

Comandos:
    "me ensina sobre recursão" / "quero aprender sobre APIs" /
    "me dá uma aula sobre economia" / "explica machine learning pra mim"
    "me testa sobre X" / "faz uma pergunta sobre X" -> gera UMA pergunta;
    responda começando com "resposta: ..." pra eu corrigir
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_ENSINAR_RE = re.compile(
    r"\b(?:me\s+)?ensin[ae]\w*\s+(?:sobre\s+|o\s+que\s+[eé]\s+)?(.+)|"
    r"\bexplica\w*\s+(.+?)\s+pra\s+mim\b|"
    r"\b(?:eu\s+)?quero\s+aprender\s+(?:sobre\s+)?(.+)|"
    r"\b(?:me\s+)?d[aá]\s+uma\s+aula\s+sobre\s+(.+)",
    re.IGNORECASE,
)
_TESTAR_RE = re.compile(
    r"\bme\s+test[ae]\w*\s+sobre\s+(.+)|\bfa[çcz]\w*\s+uma\s+pergunta\s+sobre\s+(.+)|"
    r"\bquiz\s+sobre\s+(.+)",
    re.IGNORECASE,
)
_RESPOSTA_RE = re.compile(r"^resposta:\s*(.+)", re.IGNORECASE)

_SYSTEM_PROMPT_PROFESSOR = (
    "Você é um professor particular paciente e didático. Explique o assunto pedido do "
    "zero, com exemplos simples, dividido em passos curtos e fáceis de acompanhar -- "
    "não presuma conhecimento prévio, e não use jargão sem explicar antes. No final, "
    "pergunte se ficou alguma dúvida. Você NÃO é o Ultron aqui -- não use nenhuma "
    "persona configurada, seja só um professor de verdade."
)
_SYSTEM_PROMPT_QUIZ = (
    "Você é um professor particular. Crie APENAS UMA pergunta de verificação de "
    "aprendizado sobre o assunto pedido -- direta, de resposta curta, sem múltipla "
    "escolha. Não dê a resposta ainda, e não escreva mais nada além da pergunta."
)
_SYSTEM_PROMPT_CORRECAO = (
    "Você é um professor particular corrigindo a resposta de um aluno pra uma pergunta "
    "que você mesmo fez. Diga se a resposta está certa, incompleta ou errada, explique "
    "por quê, e dê a resposta certa de forma breve e encorajadora."
)


class ProfessorPlugin(BasePlugin):
    name = "professor"
    description = "Professor particular: explica assuntos do zero e pode te testar com perguntas"
    triggers = [
        "me ensina", "ensina sobre", "quero aprender", "aula sobre",
        "me testa sobre", "faz uma pergunta sobre", "quiz sobre", "resposta:",
    ]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_ENSINAR_RE.search(t) or _TESTAR_RE.search(t) or _RESPOSTA_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()
        user_id = context["user_id"]
        ia_manager = context.get("ia_manager")
        memory = context["memory"]

        m_resposta = _RESPOSTA_RE.search(t)
        if m_resposta:
            return self._corrigir(user_id, m_resposta.group(1), ia_manager, memory)

        m_testar = _TESTAR_RE.search(t)
        if m_testar:
            assunto = next((g for g in m_testar.groups() if g), None)
            return self._testar(user_id, assunto, ia_manager, memory)

        m_ensinar = _ENSINAR_RE.search(t)
        if m_ensinar:
            assunto = next((g for g in m_ensinar.groups() if g), None)
            return self._ensinar(assunto, ia_manager)

        return None

    def _ensinar(self, assunto: str, ia_manager):
        assunto = (assunto or "").strip(" ?.!")
        if not assunto:
            return Answer("Sobre o que você quer aprender?", Confidence.GUESS)
        if ia_manager is None:
            return Answer(
                "Preciso de um provedor de IA configurado pra dar aula (veja /configurarapi).",
                Confidence.GUESS,
            )
        try:
            _, explicacao = ia_manager.chat(
                f"Me explique: {assunto}", history=[], system_prompt=_SYSTEM_PROMPT_PROFESSOR, max_tokens=900,
            )
        except Exception as e:
            return Answer(f"Não consegui preparar a aula: {e}", Confidence.GUESS)
        if not explicacao:
            return Answer("Não consegui gerar uma explicação agora.", Confidence.GUESS)
        return Answer(explicacao, Confidence.RELIABLE_SOURCE)

    def _testar(self, user_id: str, assunto: str, ia_manager, memory):
        assunto = (assunto or "").strip(" ?.!")
        if not assunto:
            return Answer("Sobre o que você quer que eu te teste?", Confidence.GUESS)
        if ia_manager is None:
            return Answer(
                "Preciso de um provedor de IA configurado pra criar a pergunta (veja /configurarapi).",
                Confidence.GUESS,
            )
        try:
            _, pergunta = ia_manager.chat(
                f"Assunto: {assunto}", history=[], system_prompt=_SYSTEM_PROMPT_QUIZ, max_tokens=200,
            )
        except Exception as e:
            return Answer(f"Não consegui gerar a pergunta: {e}", Confidence.GUESS)
        if not pergunta:
            return Answer("Não consegui gerar uma pergunta agora.", Confidence.GUESS)
        memory.remember_fact(user_id, "professor_pergunta_pendente", pergunta)
        return Answer(f'{pergunta}\n\n(Responda começando com "resposta: ...")', Confidence.CONFIRMED)

    def _corrigir(self, user_id: str, resposta_aluno: str, ia_manager, memory):
        pergunta = memory.recall_fact(user_id, "professor_pergunta_pendente")
        if not pergunta:
            return Answer(
                "Não tenho nenhuma pergunta pendente pra corrigir. Peça \"me testa sobre ...\" primeiro.",
                Confidence.GUESS,
            )
        if ia_manager is None:
            return Answer(
                "Preciso de um provedor de IA configurado pra corrigir (veja /configurarapi).",
                Confidence.GUESS,
            )
        try:
            _, correcao = ia_manager.chat(
                f"Pergunta: {pergunta}\nResposta do aluno: {resposta_aluno}",
                history=[], system_prompt=_SYSTEM_PROMPT_CORRECAO, max_tokens=400,
            )
        except Exception as e:
            return Answer(f"Não consegui corrigir: {e}", Confidence.GUESS)
        memory.forget_fact(user_id, "professor_pergunta_pendente")
        if not correcao:
            return Answer("Não consegui gerar a correção agora.", Confidence.GUESS)
        return Answer(correcao, Confidence.RELIABLE_SOURCE)
