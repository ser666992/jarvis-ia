"""
plugins/consciencia.py
=========================
Lado de chat da "consciência interna" (core/autoconsciencia.py): o
Jarvis responde tecnicamente sobre o próprio estado -- memória do
processo, tempo no ar, plugins carregados, módulos disponíveis,
provedores de IA prontos, rotinas de fundo ativas ("agentes") e
avisos/erros registrados no log hoje.

Diferente do "como você está?" casual (core/conversation.py, que dá uma
resposta de conversa): aqui é um diagnóstico técnico com números reais.

"diagnóstico completo" (ou só "diagnóstico") ACRESCENTA uma segunda
parte: um checklist item por item de cada SUB-RECURSO (OCR, ADB, STT/
TTS, provedor de IA, Instagram, etc. -- ver core/diagnostico.py), não
só "o processo está de pé". Existiam DUAS ideias parecidas com o mesmo
nome ("diagnóstico") tentando nascer como plugins separados -- como o
carregador de plugins despacha em ordem alfabética e para no primeiro
que casar, o segundo nunca seria alcançado. Unificado aqui num relatório
só, em vez de dois comandos concorrendo pela mesma palavra.

Comandos:
    "diagnóstico" / "diagnóstico completo" / "status técnico" / "relatório interno"
    "como você está por dentro" / "como você está tecnicamente"
    "quais são suas capacidades" / "quais são seus limites"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_RE = re.compile(
    r"\bdiagn[óo]stico\b|\bstatus\s+t[ée]cnico\b|\brelat[óo]rio\s+interno\b|"
    r"\bcomo\s+voc[êe]\s+est[áa]\s+(?:por\s+dentro|tecnicamente)\b|"
    r"\bseu\s+estado\s+(?:interno|t[ée]cnico)\b|"
    r"\b(?:suas\s+capacidades|seus\s+limites|seus\s+m[óo]dulos)\b|"
    r"\bcomo\s+voc[êe]\s+se\s+sente\s+tecnicamente\b",
    re.IGNORECASE,
)
_COMPLETO_RE = re.compile(r"\bdiagn[óo]stico\s+completo\b|\best[áa]\s+tudo\s+funcionando\b", re.IGNORECASE)


class ConscienciaPlugin(BasePlugin):
    name = "consciencia"
    description = "Diagnóstico técnico do próprio Jarvis: memória, uptime, plugins, módulos, IA, rotinas ativas, erros do dia -- e, no modo completo, um checklist de cada sub-recurso (OCR, ADB, voz, IA, Instagram...)"
    triggers = [
        "diagnóstico", "diagnostico", "diagnóstico completo", "status técnico", "status tecnico",
        "relatório interno", "relatorio interno", "como você está por dentro",
        "como voce esta por dentro", "suas capacidades", "seus limites",
    ]

    def matches(self, text: str) -> bool:
        return bool(_RE.search(text.strip()))

    def handle(self, text: str, context: dict):
        jarvis = context.get("jarvis")
        if jarvis is None:
            return Answer("Não consegui acessar meu próprio núcleo pra fazer o diagnóstico agora.", Confidence.GUESS)
        from core import autoconsciencia
        try:
            corpo = autoconsciencia.descrever(jarvis)
        except Exception as e:
            return Answer(f"Falhei ao montar o diagnóstico: {e}", Confidence.GUESS)
        resposta = "Meu estado técnico agora:\n" + corpo

        if _COMPLETO_RE.search(text.strip()):
            resposta += "\n\n" + self._recursos()
        else:
            resposta += (
                '\n\nDiga "diagnóstico completo" pra eu testar cada sub-recurso também '
                "(OCR, ADB, voz, provedor de IA, Instagram etc.)."
            )
        return Answer(resposta, Confidence.CONFIRMED)

    def _recursos(self) -> str:
        from core.diagnostico import rodar_diagnostico
        itens = rodar_diagnostico()
        oks = sum(1 for i in itens if i["ok"])

        linhas = [f"Sub-recursos -- {oks}/{len(itens)} prontos:"]
        area_atual = None
        for item in itens:
            if item["area"] != area_atual:
                area_atual = item["area"]
                linhas.append(f"\n{area_atual}:")
            marca = "OK" if item["ok"] else "--"
            detalhe = f" ({item['detalhe']})" if item["detalhe"] else ""
            linhas.append(f"  [{marca}] {item['nome']}{detalhe}")
        return "\n".join(linhas)
