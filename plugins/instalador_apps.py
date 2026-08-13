"""
plugins/instalador_apps.py
==============================
"Baixa esse app pra mim, só dizendo o nome" -- via winget (Windows
Package Manager). Instalar programa novo é ação destrutiva-adjacente
(grava no sistema de verdade) -- exige confirmação explícita, igual a
fechar um programa (ver automacao/instalador_apps.py).

O verbo "baixa" também é usado por plugins/system_control.py pra
"abaixa o volume/brilho" -- os lookaheads em _BAIXA_APP_RE excluem
"volume"/"brilho" de propósito, pra não roubar esses comandos.

Comandos:
    "instala o vlc" / "baixa o spotify" / "instala o discord, confirmo"
    "procura o pacote do vlc" -> lista candidatos sem instalar nada
"""

import re

from automacao import instalador_apps
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from seguranca.permissions import PermissionDenied, confirmado_pela_frase_ou_config

_INSTALA_RE = re.compile(r"\binstal[ae]\w*\s+(?:o|a)?\s*(.+)", re.IGNORECASE)
# O lookahead negativo precisa "ver" o mesmo artigo opcional que o
# resto do padrão consome depois -- senão o motor de regex pode
# simplesmente NÃO casar o artigo opcional pra escapar do lookahead
# (backtracking), e "baixa o volume" acaba sendo capturado como se
# "o volume" fosse o nome de um app.
_BAIXA_APP_RE = re.compile(
    r"\bbaix[ae]\w*\s+(?!(?:o|a)?\s*(?:volume|brilho)\b)(?:o|a)?\s*(.+)", re.IGNORECASE
)
_SEARCH_RE = re.compile(
    # "pacote" é OBRIGATÓRIO aqui (antes vinha opcional -- "(?:...)?" --
    # e por isso "procura o pacote de vlc" era só um caso PARTICULAR de
    # um padrão que também casava qualquer "busca X"/"procura X" solto,
    # roubando "busca na base" (knowledge_base.py) e "procura na
    # internet" (automacao/navegador.py). Bug real, achado numa
    # auditoria sistemática de colisão de triggers.
    r"\b(procur[ae]|busc[ae])\w*\s+(?:o\s+)?pacote\s+d[eo]\s+(.+)", re.IGNORECASE
)
_CONFIRM_WORD_RE = re.compile(r"\bconfirmo\b|\btenho certeza\b|\bpode instalar\b", re.IGNORECASE)


def _extrair_nome(resto: str) -> str:
    return _CONFIRM_WORD_RE.sub("", resto).strip(" ,.!?")


class InstaladorAppsPlugin(BasePlugin):
    name = "instalador_apps"
    description = "Instala programas por nome via winget (Windows Package Manager)"
    triggers = ["instala o", "instala a", "baixa o", "baixa a", "procura o pacote", "busca o pacote"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_INSTALA_RE.search(t) or _BAIXA_APP_RE.search(t) or _SEARCH_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()

        m = _SEARCH_RE.search(t)
        if m:
            return self._buscar(_extrair_nome(m.group(2)))

        m = _INSTALA_RE.search(t) or _BAIXA_APP_RE.search(t)
        if m:
            resto = m.group(1)
            confirmado = confirmado_pela_frase_ou_config(bool(_CONFIRM_WORD_RE.search(resto)))
            return self._instalar(_extrair_nome(resto), confirmado)

        return None

    def _buscar(self, nome: str):
        if not nome:
            return Answer("Procurar o pacote de qual programa?", Confidence.GUESS)
        if not instalador_apps.available():
            return Answer(
                "Preciso do 'winget' (Windows Package Manager) -- já vem com Windows 10/11 "
                "atualizados, ou instale o 'App Installer' pela Microsoft Store.",
                Confidence.GUESS,
            )
        try:
            candidatos = instalador_apps.buscar(nome)
        except Exception as e:
            return Answer(f"Não consegui buscar: {e}", Confidence.GUESS)
        if not candidatos:
            return Answer(f'Não achei nenhum pacote parecido com "{nome}".', Confidence.CONFIRMED)
        return Answer("Encontrei:\n" + "\n".join(candidatos), Confidence.CONFIRMED)

    def _instalar(self, nome: str, confirmado: bool):
        if not nome:
            return Answer("Instalar o quê?", Confidence.GUESS)
        if not instalador_apps.available():
            return Answer(
                "Preciso do 'winget' (Windows Package Manager) -- já vem com Windows 10/11 "
                "atualizados, ou instale o 'App Installer' pela Microsoft Store.",
                Confidence.GUESS,
            )
        if not confirmado:
            return Answer(
                f'Instalar "{nome}" grava um programa novo de verdade no seu sistema -- tem '
                f'certeza? Diga "instala o {nome}, confirmo".',
                Confidence.GUESS,
            )
        try:
            saida = instalador_apps.instalar(nome, confirmed=True)
        except PermissionDenied as e:
            return Answer(str(e), Confidence.GUESS)
        except Exception as e:
            return Answer(f'Não consegui instalar "{nome}": {e}', Confidence.GUESS)
        return Answer(f'Instalação de "{nome}" concluída (ou já estava instalado):\n{saida[-500:]}', Confidence.CONFIRMED)
