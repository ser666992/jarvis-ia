"""
plugins/consciencia_codigo.py
================================
Lado de chat da "consciência de código" (core/consciencia_codigo.py):
mapa de dependências do próprio código do Ultron, pra você entender o
impacto de uma mudança antes de fazer.

Honesto: é análise estática no nível de import (quem importa quem), não
call graph de método por método -- mas já responde bem "se eu mexer
nisso, o que quebra?".

Comandos:
    "mapa do código" / "analisa o código" / "estrutura do código"
    "o que depende do automacao.tasks" / "o que quebra se eu mexer em memory"
    "de que o skill_forge depende"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_RESUMO_RE = re.compile(
    r"\bmapa\s+d[oe]\s+c[óo]digo\b|\banalis[ae]\w*\s+o\s+c[óo]digo\b|"
    r"\bestrutura\s+d[oe]\s+c[óo]digo\b|\bconsci[êe]ncia\s+d[eo]\s+c[óo]digo\b",
    re.IGNORECASE,
)
_DEPENDENTES_RE = re.compile(
    r"\bo\s+que\s+(?:depende|usa)\s+d[eo]\s+(\S+)|"
    r"\bo\s+que\s+quebra\s+se\s+eu\s+(?:mexer|mudar|apagar)\s+(?:em\s+|n[oa]\s+|o\s+|a\s+)?(\S+)|"
    r"\bquem\s+(?:importa|usa)\s+(?:o\s+|a\s+)?(\S+)",
    re.IGNORECASE,
)
_DEPENDENCIAS_RE = re.compile(
    r"\bde\s+que\s+(?:o\s+|a\s+)?(\S+)\s+depende\b|"
    r"\bdo\s+que\s+(?:o\s+|a\s+)?(\S+)\s+depende\b|"
    r"\bdepend[êe]ncias\s+d[eo]\s+(\S+)",
    re.IGNORECASE,
)


def _limpar_alvo(nome: str) -> str:
    # str.rstrip(".py") removeria QUALQUER '.', 'p' ou 'y' final (é um
    # conjunto de caracteres, não um sufixo) -- "memory" virava "memor".
    # Remove o sufixo ".py" só se ele existir de verdade.
    alvo = (nome or "").strip().strip(" ?.!\"'")
    if alvo.endswith(".py"):
        alvo = alvo[:-3]
    # Usuário digita caminho de arquivo ("core/memory", "core\\memory.py"),
    # mas o grafo indexa por nome de MÓDULO ("core.memory") -- sem essa
    # conversão, qualquer pergunta com barra respondia "nada importa isso".
    alvo = alvo.replace("/", ".").replace("\\", ".")
    return alvo


class ConscienciaCodigoPlugin(BasePlugin):
    name = "consciencia_codigo"
    description = "Mapa de dependências do próprio código do Ultron: o que depende de um módulo, do que ele depende, e o impacto de mexer nele"
    triggers = ["mapa do código", "mapa do codigo", "o que depende de", "o que quebra se eu mexer", "de que o", "estrutura do código"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_DEPENDENCIAS_RE.search(t) or _DEPENDENTES_RE.search(t) or _RESUMO_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()
        from core import consciencia_codigo

        m = _DEPENDENCIAS_RE.search(t)
        if m:
            alvo = _limpar_alvo(next((g for g in m.groups() if g), ""))
            deps = consciencia_codigo.dependencias_de(alvo)
            if not deps:
                return Answer(f'Não achei o módulo "{alvo}", ou ele não importa nenhum módulo interno.', Confidence.GUESS)
            return Answer(f'"{alvo}" depende de (importa): ' + ", ".join(deps), Confidence.CONFIRMED)

        m = _DEPENDENTES_RE.search(t)
        if m:
            alvo = _limpar_alvo(next((g for g in m.groups() if g), ""))
            deps = consciencia_codigo.dependentes_de(alvo)
            if not deps:
                return Answer(
                    f'Nada no projeto importa "{alvo}" (ou o nome não bate com nenhum módulo). '
                    "Mexer nele não deveria quebrar outro módulo por import direto.",
                    Confidence.CONFIRMED,
                )
            return Answer(
                f'Se você mexer em "{alvo}", isto pode ser afetado ({len(deps)} módulo(s) que o importam):\n'
                + ", ".join(deps),
                Confidence.CONFIRMED,
            )

        if _RESUMO_RE.search(t):
            r = consciencia_codigo.resumo()
            top = "\n".join(f"   - {mod}: importado por {n} módulo(s)" for mod, n in r["mais_importados"])
            return Answer(
                f"Mapa do meu código: {r['total_modulos']} módulos internos, "
                f"{r['total_dependencias']} dependências (imports internos) entre eles.\n"
                f"Os mais centrais (mais arriscados de mexer, porque muita coisa depende deles):\n{top}\n\n"
                'Pergunte "o que quebra se eu mexer em <módulo>" pra ver o impacto de um específico.',
                Confidence.CONFIRMED,
            )

        return None
