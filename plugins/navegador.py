"""
plugins/navegador.py
=======================
"Navega sozinho na internet": pesquisa um termo, lê os primeiros
resultados de verdade (não só um snippet de busca) e resume/responde
com base no que encontrou -- ver automacao/navegador.py. Diferente de
knowledge_search.py (só Wikipedia): isso pesquisa a internet aberta e
lê o conteúdo de fato das páginas.

Comandos:
    "pesquisa na internet sobre X" / "navega na internet e descobre X" /
    "procura na internet X"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from core.timeline import registrar

_BROWSE_RE = re.compile(
    r"\bpesquis[ae]\w*\s+na\s+internet\s+(?:sobre\s+)?(.+)|"
    r"\bnaveg[ae]\w*\s+na\s+internet\b.*?(?:e\s+)?(?:descobre|acha|pesquisa)\s+(.+)|"
    r"\bprocur[ae]\w*\s+na\s+internet\s+(.+)",
    re.IGNORECASE,
)


class NavegadorPlugin(BasePlugin):
    name = "navegador"
    description = "Pesquisa e lê páginas de verdade na internet (não só o snippet de busca) e resume"
    triggers = ["pesquisa na internet", "navega na internet", "procura na internet"]

    def matches(self, text: str) -> bool:
        return bool(_BROWSE_RE.search(text))

    def handle(self, text: str, context: dict):
        m = _BROWSE_RE.search(text)
        if not m:
            return None
        consulta = next((g for g in m.groups() if g), None)
        consulta = (consulta or "").strip(" ?.!")
        if not consulta:
            return Answer("Pesquisar o quê na internet?", Confidence.GUESS)

        from automacao import navegador
        if not navegador.available():
            return Answer(
                "Instale 'playwright' (requirements-automacao.txt) e rode "
                "'python -m playwright install chromium' pra eu navegar na internet.",
                Confidence.GUESS,
            )

        ia_manager = context.get("ia_manager")
        try:
            resposta = navegador.pesquisar_e_resumir(ia_manager, consulta)
        except RuntimeError as e:
            return Answer(str(e), Confidence.GUESS)

        registrar("navegacao_web", consulta)
        confianca = Confidence.RELIABLE_SOURCE if ia_manager is not None else Confidence.SINGLE_SOURCE
        return Answer(resposta, confianca)
