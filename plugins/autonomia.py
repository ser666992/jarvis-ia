"""
plugins/autonomia.py
=======================
Dispara AGORA (sob demanda) as rotinas autônomas que normalmente rodam
sozinhas em segundo plano, mas em intervalos longos (aprender
tecnologia = 24h, sonhar uma habilidade = 2h) -- assim você consegue
VER o Ultron aprender algo na web ou inventar uma função na hora, em
vez de esperar horas.

Isto NÃO muda nenhuma regra de segurança: uma habilidade "sonhada"
continua sendo só um RASCUNHO pendente que espera sua aprovação (mesmo
gate de core/skill_forge.py). Aprender um tópico só grava conhecimento
na base interna (nada executável).

Comandos:
    "aprende algo novo" / "aprenda algo sozinho" / "aprende algo na internet"
    "inventa uma habilidade" / "cria uma habilidade sozinho" / "sonha uma habilidade nova"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_APRENDER_RE = re.compile(
    r"\baprend[ae]\w*\s+(?:algo|alguma\s+coisa|um\s+t[óo]pico|uma\s+tecnologia)\b|"
    r"\baprend[ae]\w*\s+(?:sozinho|sozinha|por\s+conta)\b|"
    r"\baprend[ae]\w*\s+.*\b(?:na\s+internet|na\s+web|online)\b",
    re.IGNORECASE,
)
_SONHAR_RE = re.compile(
    r"\b(?:invent[ae]|cri[ae]|sonh[ae])\w*\s+(?:uma\s+|com\s+uma\s+)?habilidade\b|"
    r"\bsonh[ae]\w*\s+(?:com\s+)?(?:uma\s+)?(?:ideia|fun[çc][ãa]o|habilidade)\b",
    re.IGNORECASE,
)


class AutonomiaPlugin(BasePlugin):
    name = "autonomia"
    description = "Dispara na hora as rotinas autônomas (aprender algo novo da web, inventar uma habilidade) em vez de esperar o ciclo automático"
    triggers = [
        "aprende algo novo", "aprenda algo", "aprende algo na internet",
        "inventa uma habilidade", "cria uma habilidade sozinho", "sonha uma habilidade",
    ]

    def matches(self, text: str) -> bool:
        t = text.strip()
        # "cria uma habilidade que ..." (com um pedido específico) é do
        # skill_forge, não daqui -- só pegamos o pedido GENÉRICO de
        # inventar algo sozinho, sem o usuário dizer o quê.
        if re.search(r"\bhabilidade\s+que\b|\bhabilidade\s+pra\b|\bhabilidade\s+para\b", t, re.IGNORECASE):
            return False
        return bool(_APRENDER_RE.search(t) or _SONHAR_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()
        jarvis = context.get("jarvis")
        if jarvis is None:
            return Answer("Não consegui acessar o núcleo do Ultron pra fazer isso agora.", Confidence.GUESS)

        if _SONHAR_RE.search(t):
            return self._sonhar(jarvis)
        if _APRENDER_RE.search(t):
            return self._aprender(jarvis)
        return None

    def _aprender(self, jarvis):
        from automacao import aprendizado_autonomo
        try:
            resultado = aprendizado_autonomo.aprender_um_topico(jarvis)
        except Exception as e:
            return Answer(f"Tentei aprender algo agora, mas falhou: {e}", Confidence.GUESS)
        if not resultado:
            return Answer(
                "Por enquanto não achei nada novo pra aprender (já pesquisei os tópicos da minha "
                "lista), ou não consegui acessar a internet agora. Tento de novo mais tarde sozinho.",
                Confidence.GUESS,
            )
        return Answer(
            f'Aprendi sozinho sobre "{resultado["topico"]}" (fonte: {resultado["fonte"]}):\n\n'
            f'{resultado["resumo"][:600]}\n\n'
            f'Já guardei na minha base -- pergunte "o que você aprendeu sobre {resultado["topico"]}" '
            "quando quiser rever.",
            Confidence.RELIABLE_SOURCE,
        )

    def _sonhar(self, jarvis):
        if jarvis.ia_manager is None:
            return Answer(
                "Pra inventar uma habilidade sozinho eu preciso de um provedor de IA configurado "
                "(veja /configurarapi).",
                Confidence.GUESS,
            )
        from automacao import sonhos
        try:
            resultado = sonhos.sonhar_uma_habilidade(jarvis)
        except Exception as e:
            return Answer(f"Tentei inventar uma habilidade agora, mas falhou: {e}", Confidence.GUESS)
        if not resultado:
            return Answer(
                "Tentei inventar uma habilidade nova agora, mas o rascunho não passou no meu "
                "autoteste (carreguei e testei antes de te mostrar). Descartei -- tento outra ideia "
                "depois. Nada foi ativado.",
                Confidence.GUESS,
            )
        avisos = ""
        if resultado.get("avisos"):
            avisos = "\n\nAtenção ao revisar -- o código usa: " + "; ".join(resultado["avisos"]) + "."
        return Answer(
            f'Inventei e testei uma habilidade nova sozinho: "{resultado["slug"]}" '
            f'({resultado["caminho"]}). Passou no autoteste e está como RASCUNHO esperando sua '
            f'aprovação -- ela NÃO está ativa ainda. Revise o arquivo e diga "aprova a habilidade '
            f'{resultado["slug"]}" pra ativar, ou "rejeita a habilidade {resultado["slug"]}" pra '
            f"descartar.{avisos}",
            Confidence.CONFIRMED,
        )
