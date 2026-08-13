"""
plugins/clicar_texto.py
==========================
"Clica no texto ...": localiza um trecho de texto NA TELA via OCR
(visao.ocr.localizar_texto_na_tela) e clica no centro dele
(controle_pc.entrada.clicar) -- combina visão computacional com
controle de mouse/teclado pra automatizar UI que não tem atalho de
teclado nem elemento nomeado localizável por
controle_pc/elementos.py (ex.: um botão dentro de uma imagem, um jogo,
um app que não expõe nomes de controle pra automação de UI nativa).

IMPORTANTE (evita colisão real): plugins/controle_pc.py já responde a
"clica no botão <nome>"/"clica em <nome>" genérico, via elemento de UI
nomeado (pywinauto -- mais rápido/confiável quando o app expõe nome
acessível de verdade). Pra não roubar esses gatilhos (plugins são
"primeiro que casar, ganha", por ordem alfabética de arquivo -- e
"clicar_texto.py" vem ANTES de "controle_pc.py"), este plugin só ativa
com um marcador EXPLÍCITO de que é busca por texto NA TELA: a palavra
"texto" logo após no/na/em, ou o sufixo obrigatório "na tela". "clica
no botão Salvar" sem nenhum desses dois continua indo pro plugin de
elemento de UI, sem mudança de comportamento pra quem já usa isso.

Sem confirmação exigida, mesma categoria de controle_pc/entrada.py
(entrada simulada reversível -- ver docstring de lá pro raciocínio
completo). Se o texto aparecer mais de uma vez na tela, clica na
correspondência de MAIOR confiança do OCR.

Comandos:
    "clica no texto Salvar"
    "clica no texto que diz OK"
    "clica duas vezes no texto abrir arquivo"
    "clica em Cancelar na tela"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_RE_TEXTO = re.compile(
    r'\bclic[ae]\w*\b(?:\s+duas\s+vezes)?\s+(?:no|na|em)\s+texto\s+(?:que\s+diz\s+)?'
    r'["\']?(.+?)["\']?(?:\s+na\s+tela)?$',
    re.IGNORECASE,
)
_RE_NA_TELA = re.compile(
    r'\bclic[ae]\w*\b(?:\s+duas\s+vezes)?\s+(?:no|na|em)\s+["\']?(.+?)["\']?\s+na\s+tela$',
    re.IGNORECASE,
)
_RE_DUPLO = re.compile(r"\bduas\s+vezes\b", re.IGNORECASE)


class ClicarTextoPlugin(BasePlugin):
    name = "clicar_texto"
    description = "Localiza um texto na tela via OCR e clica nele (combina visão + controle do mouse)"
    triggers = ["clica no texto", "clica no texto que diz", "clica na tela"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_RE_TEXTO.search(t) or _RE_NA_TELA.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()
        m = _RE_TEXTO.search(t) or _RE_NA_TELA.search(t)
        if not m:
            return None
        alvo = m.group(1).strip(" \"'.")
        if not alvo:
            return None

        from visao import ocr, screen
        if not ocr.available():
            return Answer(
                "OCR indisponível pra eu ler a tela (instale 'pytesseract' + Pillow + o binário "
                "Tesseract, ver requirements-visao.txt).",
                Confidence.GUESS,
            )
        if not screen.available():
            return Answer("Captura de tela indisponível (instale 'mss').", Confidence.GUESS)

        from controle_pc import entrada
        if not entrada.available():
            return Answer("Controle de mouse indisponível (instale 'pyautogui').", Confidence.GUESS)

        try:
            encontrados = ocr.localizar_texto_na_tela(alvo)
        except Exception as e:
            return Answer(f"Não consegui ler a tela: {e}", Confidence.GUESS)

        if not encontrados:
            return Answer(f'Não encontrei "{alvo}" na tela.', Confidence.GUESS)

        melhor = encontrados[0]
        duplo = bool(_RE_DUPLO.search(t))
        entrada.clicar(melhor["x"], melhor["y"], duplo=duplo)

        acao = "Cliquei duas vezes" if duplo else "Cliquei"
        return Answer(
            f'{acao} em "{melhor["texto"]}" (encontrado por OCR, confiança {melhor["confianca"]:.0f}%).',
            Confidence.CONFIRMED,
        )
