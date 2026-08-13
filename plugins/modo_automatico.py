"""
plugins/modo_automatico.py
==============================
Expõe automacao/modo_automatico.py via linguagem natural no chat.

Exemplos:
    "ativa auto: abre o spotify e toca lofi, depois diminui o volume"
    "modo automático: tira um screenshot e abre o navegador"
    "modo auto: organiza -- abre o discord e o vscode"

Ver automacao/modo_automatico.py pro porquê disso NÃO ser "controle
irrestrito": cada passo passa pelo dispatch normal de plugins (mesma
política de confirmação pra ações destrutivas), e a IA é instruída a
recusar o plano inteiro em vez de arriscar algo fora das capacidades
reais do Ultron.
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_TRIGGER_RE = re.compile(
    # \b no fim de cada alternativa -- sem isso, "modo auto" batia como
    # PREFIXO de "modo autonomo" (sem acento -- letras ASCII batem
    # literalmente), sequestrando os comandos de
    # plugins/modo_autonomo.py (o Modo Autônomo com detecção de
    # ociosidade). Mesma classe de bug de limite de palavra já vista
    # antes ("na verdade e" casando como prefixo de "na verdade eu").
    r"(?:ativa\s+(?:o\s+)?modo\s+autom[áa]tico\b|ativa\s+auto\b|modo\s+auto(?:m[áa]tico)?\b)"
    r"\s*:?\s*(.+)",
    re.IGNORECASE,
)
_TRIGGER_VAZIO_RE = re.compile(
    r"\bativa\s+auto\b|\bmodo\s+autom[áa]tico\b|\bmodo\s+auto\b", re.IGNORECASE,
)


class ModoAutomaticoPlugin(BasePlugin):
    name = "modo_automatico"
    description = "Modo automático: decompõe um objetivo em uma sequência de comandos e executa sozinho, dentro das capacidades já existentes"
    triggers = ["ativa auto", "modo auto"]

    def matches(self, text: str) -> bool:
        # NÃO usar o matches() padrão (substring simples em `triggers`)
        # aqui -- "modo auto" bateria como PREFIXO de "modo autonomo"
        # (sem acento), sequestrando os comandos de
        # plugins/modo_autonomo.py mesmo com _TRIGGER_RE/_TRIGGER_VAZIO_RE
        # já tendo o \b certo pra evitar exatamente isso (bug real:
        # a regex corrigida só era usada dentro de handle(), nunca
        # aqui, então a colisão continuava acontecendo na prática).
        t = text.strip()
        return bool(_TRIGGER_RE.search(t) or _TRIGGER_VAZIO_RE.search(t))

    def _formatar(self, relatorio: dict) -> str:
        if relatorio["recusa"]:
            return (
                f'Não vou executar "{relatorio["objetivo"]}" automaticamente: '
                f'{relatorio["recusa"]}'
            )
        linhas = [f'Modo automático pra "{relatorio["objetivo"]}":']
        for i, p in enumerate(relatorio["passos"], 1):
            marca = "OK" if p["executado"] else "PAROU"
            linhas.append(f"{i}. [{marca}] {p['comando']} -> {p['resposta']}")
        feitos = sum(1 for p in relatorio["passos"] if p["executado"])
        total = len(relatorio["passos"])
        if feitos < total:
            linhas.append(f"\nParei em {feitos}/{total} passos (motivo no último item acima).")
        else:
            linhas.append(f"\nConcluí os {total} passos sozinho.")
        return "\n".join(linhas)

    def handle(self, text: str, context: dict):
        t = text.strip()
        m = _TRIGGER_RE.search(t)
        objetivo = m.group(1).strip(" :.!") if m else ""
        if not objetivo:
            if _TRIGGER_VAZIO_RE.search(t):
                return Answer(
                    'Modo automático pra fazer o quê? Diga algo como "ativa auto: <objetivo>".',
                    Confidence.GUESS,
                )
            return None

        jarvis = context.get("jarvis")
        if jarvis is None or jarvis.ia_manager is None:
            return Answer(
                "Modo automático precisa de um provedor de IA configurado pra planejar os "
                "passos -- sem isso não tenho como decompor o objetivo com segurança.",
                Confidence.GUESS,
            )

        from automacao import modo_automatico
        relatorio = modo_automatico.executar(jarvis, objetivo, context)
        return Answer(self._formatar(relatorio), Confidence.CONFIRMED)
