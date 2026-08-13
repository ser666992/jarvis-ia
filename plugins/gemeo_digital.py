"""
plugins/gemeo_digital.py
============================
"Cria um gêmeo digital e testa antes de aplicar de verdade" -- ver
automacao/gemeo_digital.py. Por enquanto cobre a operação mais
arriscada já existente no projeto: organizar uma pasta por tipo
(automacao/files.py:organize_by_type).

Comandos:
    "testa organizar a pasta <caminho> num gêmeo digital" -> aplica
    numa cópia, mostra o que mudaria, sem tocar no original
    "aplica de verdade a organização da pasta <caminho>, confirmo" ->
    roda a operação real (mesma confirmação de sempre)
"""

import re

from automacao import files, gemeo_digital
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from core.timeline import registrar
from seguranca.permissions import PermissionDenied, confirmado_pela_frase_ou_config

_TESTAR_RE = re.compile(
    r"\btest[ae]\w*\s+organizar\s+a\s+pasta\s+(.+?)\s+num\s+g[êe]meo\s+digital|"
    r"\bg[êe]meo\s+digital\s+d[ea]\s+pasta\s+(.+)",
    re.IGNORECASE,
)
_APLICAR_RE = re.compile(
    r"\bapli[ck]a\w*\s+de\s+verdade\s+a\s+organiza[çc][ãa]o\s+da\s+pasta\s+(.+)", re.IGNORECASE
)
_CONFIRM_WORD_RE = re.compile(r"\bconfirmo\b", re.IGNORECASE)


class GemeoDigitalPlugin(BasePlugin):
    name = "gemeo_digital"
    description = "Testa organização de pastas num 'gêmeo digital' (cópia) antes de aplicar de verdade"
    triggers = ["gêmeo digital", "gemeo digital", "aplica de verdade a organização"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_TESTAR_RE.search(t) or _APLICAR_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()

        m = _TESTAR_RE.search(t)
        if m:
            pasta = (m.group(1) or m.group(2) or "").strip(" ,.!?")
            return self._testar(pasta)

        m = _APLICAR_RE.search(t)
        if m:
            pasta = _CONFIRM_WORD_RE.sub("", m.group(1)).strip(" ,.!?")
            confirmado = confirmado_pela_frase_ou_config(bool(_CONFIRM_WORD_RE.search(t)))
            return self._aplicar(pasta, confirmado)

        return None

    def _testar(self, pasta: str):
        if not pasta:
            return Answer("Testar a organização de qual pasta?", Confidence.GUESS)
        try:
            resultado = gemeo_digital.testar_organizacao(pasta)
        except Exception as e:
            return Answer(f"Não consegui testar isso: {e}", Confidence.GUESS)

        if resultado["total"] == 0:
            return Answer(
                f'Testei num gêmeo digital -- nada mudaria organizando "{pasta}" '
                "(nenhum arquivo bateu com as categorias conhecidas).",
                Confidence.CONFIRMED,
            )
        linhas = [f"- {cat}: {len(arqs)} arquivo(s)" for cat, arqs in resultado["movidos"].items()]
        registrar("gemeo_digital_testado", pasta)
        return Answer(
            f'Testei num gêmeo digital (cópia em "{resultado["caminho_gemeo"]}") -- organizando '
            f'"{pasta}" por tipo moveria:\n' + "\n".join(linhas) +
            f'\n\nSe quiser aplicar de verdade na pasta original, diga "aplica de verdade a '
            f'organização da pasta {pasta}, confirmo".',
            Confidence.CONFIRMED,
        )

    def _aplicar(self, pasta: str, confirmado: bool):
        if not pasta:
            return Answer("Aplicar a organização de qual pasta?", Confidence.GUESS)
        if not confirmado:
            return Answer(
                f'Isso move arquivos de verdade em "{pasta}" -- tem certeza? Diga "aplica de '
                f'verdade a organização da pasta {pasta}, confirmo".',
                Confidence.GUESS,
            )
        try:
            movidos = files.organize_by_type(pasta, confirmed=True)
        except PermissionDenied as e:
            return Answer(str(e), Confidence.GUESS)
        except Exception as e:
            return Answer(f"Não consegui organizar: {e}", Confidence.GUESS)
        total = sum(len(v) for v in movidos.values())
        return Answer(f'Organizei "{pasta}" de verdade -- {total} arquivo(s) movido(s).', Confidence.CONFIRMED)
