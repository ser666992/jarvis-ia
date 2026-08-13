"""
plugins/linguagem_propria.py
================================
UltronScript: a linguagem de programação PRÓPRIA do Ultron (léxico,
sintaxe e interpretador em linguagem/, ver linguagem/README.md pra
sintaxe completa). Sandboxed por construção -- sem acesso a arquivo,
rede, ou qualquer coisa do sistema operacional, só o que os builtins
(imprime, len, str, num, tempo) expõem.

Comandos:
    "roda em ultronscript: <código>" -> executa e mostra a saída
    "o que é ultronscript" / "como programar em ultronscript" -> explica a sintaxe
    ("jarvisscript" continua aceito também, por compatibilidade com o nome antigo)
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from linguagem import executar

_RUN_RE = re.compile(r"\brod[ae]\w*\s+em\s+(?:ultron|jarvis)\s*script\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)
_SOBRE_RE = re.compile(
    r"\b(o que [eé]|como programar em|sintaxe d[eo])\s+(?:ultron|jarvis)\s*script\b", re.IGNORECASE
)

_RESUMO_SINTAXE = (
    "UltronScript é a linguagem de programação própria do Ultron -- pequena, mas real "
    "(léxico, sintaxe e interpretador escritos do zero em Python, ver linguagem/README.md).\n\n"
    "Exemplo:\n"
    'var nome = "mundo";\n'
    'imprime "olá, " + nome;\n\n'
    "func soma(a, b) {\n"
    "    retorna a + b;\n"
    "}\n"
    "imprime soma(2, 3);\n\n"
    "Palavras-chave: var, func, se/senao, enquanto, para, quebra, continua, "
    "retorna, imprime, verdadeiro/falso, nulo, e/ou/nao. Operadores compostos: "
    "+= -= *= /=. Listas aceitam atribuição por índice (lista[0] = valor). "
    "Builtins: len, str, num, tempo.\n"
    'Rode com "roda em ultronscript: <código>".'
)


class LinguagemPropriaPlugin(BasePlugin):
    name = "linguagem_propria"
    description = "Interpretador da UltronScript, a linguagem de programação própria do Ultron"
    triggers = ["ultronscript", "ultron script", "jarvisscript", "jarvis script"]

    def matches(self, text: str) -> bool:
        return bool(_RUN_RE.search(text) or _SOBRE_RE.search(text))

    def handle(self, text: str, context: dict):
        if _SOBRE_RE.search(text):
            return Answer(_RESUMO_SINTAXE, Confidence.CONFIRMED)

        m = _RUN_RE.search(text)
        if m:
            codigo = m.group(1).strip()
            saida, erro = executar(codigo)
            if erro:
                extra = f"\n\nSaída até o erro:\n{saida}" if saida else ""
                return Answer(f"Erro ao rodar:\n{erro}{extra}", Confidence.GUESS)
            return Answer(saida or "(programa rodou sem imprimir nada)", Confidence.CONFIRMED)

        return None
