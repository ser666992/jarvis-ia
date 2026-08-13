"""
plugins/plano_energia.py
===========================
Troca o plano de energia do Windows por comando (controle_pc/energia.py,
via `powercfg`) -- "modo economia de energia" antes de sair de casa com
o notebook, "modo desempenho máximo" antes de um jogo/render pesado,
"modo equilibrado" pra voltar ao padrão. Reversível na hora (é só
trocar de novo), sem confirmação exigida -- mesma categoria de
organizar janelas.

Comandos:
    "modo economia de energia" / "modo desempenho máximo" / "modo equilibrado"
    "troca o plano de energia pra alto desempenho"
    "qual o plano de energia atual"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_RE_CONSULTAR = re.compile(r"\bqual\b.*\bplano\s+de\s+energia\b|\bplano\s+de\s+energia\s+atual\b", re.IGNORECASE)
_FRASES_ATIVAR = {
    re.compile(r"\bmodo\s+economia\s+de\s+energia\b|\beconomiz[ae]\w*\s+energia\b|\bpoup[ae]\w*\s+bateria\b", re.IGNORECASE):
        "economia de energia",
    re.compile(r"\bmodo\s+desempenho\s+m[aá]ximo\b|\balto\s+desempenho\b|\bdesempenho\s+m[aá]ximo\b", re.IGNORECASE):
        "desempenho máximo",
    re.compile(r"\bmodo\s+equilibrado\b|\bplano\s+equilibrado\b|\bplano\s+balanceado\b", re.IGNORECASE):
        "equilibrado",
}
_RE_TROCAR_GENERICO = re.compile(
    r"\b(?:troca|troque|muda|mude)\b.*\bplano\s+de\s+energia\s+(?:pra|para)\s+(.+)",
    re.IGNORECASE,
)


class PlanoEnergiaPlugin(BasePlugin):
    name = "plano_energia"
    description = "Troca o plano de energia do Windows (economia/equilibrado/desempenho máximo)"
    triggers = ["modo economia de energia", "modo desempenho máximo", "modo equilibrado", "plano de energia"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        if _RE_CONSULTAR.search(t) or _RE_TROCAR_GENERICO.search(t):
            return True
        return any(padrao.search(t) for padrao in _FRASES_ATIVAR)

    def handle(self, text: str, context: dict):
        from controle_pc import energia
        if not energia.available():
            return Answer("Troca de plano de energia só é suportada no Windows.", Confidence.GUESS)

        t = text.strip()

        if _RE_CONSULTAR.search(t):
            try:
                ativo = energia.plano_ativo()
            except Exception as e:
                return Answer(f"Não consegui consultar o plano de energia: {e}", Confidence.GUESS)
            if not ativo:
                return Answer("Não consegui identificar o plano de energia ativo.", Confidence.GUESS)
            return Answer(f'O plano de energia atual é "{ativo["nome"]}".', Confidence.CONFIRMED)

        alvo = None
        for padrao, nome in _FRASES_ATIVAR.items():
            if padrao.search(t):
                alvo = nome
                break
        if alvo is None:
            m = _RE_TROCAR_GENERICO.search(t)
            if m:
                alvo = m.group(1).strip(" .!?")
        if alvo is None:
            return None

        try:
            resultado = energia.ativar_plano(alvo)
        except ValueError as e:
            return Answer(str(e), Confidence.GUESS)
        except Exception as e:
            return Answer(f"Não consegui trocar o plano de energia: {e}", Confidence.GUESS)
        return Answer(f'Prontinho, plano de energia trocado pra "{resultado["nome"]}".', Confidence.CONFIRMED)
