"""
plugins/video_creation.py
============================
"Cria vídeos": grava um trecho da tela (visao/screen.py:record_screen)
e permite editar depois -- cortar um trecho, acelerar
(visao/video_edit.py). Vídeos ficam em data/videos/.

A gravação é BLOQUEANTE (o Ultron fica ocupado gravando durante o
tempo pedido, sem responder a outras coisas nesse meio-tempo) -- por
isso há um teto de duração (_DURACAO_MAXIMA) pra não travar demais.

Comandos:
    "grava minha tela por 20 segundos" / "grava um vídeo de 2 minutos"
    "lista os vídeos" / "quais vídeos você gravou"
    "corta o vídeo <nome> de 5 a 15 segundos"
    "acelera o vídeo <nome> em 2x"
"""

import datetime
import os
import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from core.timeline import registrar
from visao import screen, video_edit

VIDEOS_DIR = os.path.join("data", "videos")
_DURACAO_MAXIMA = 120  # segundos

_RECORD_RE = re.compile(
    r"\bgrav[ae]\w*\b.*\b(?:tela|v[ií]deo)\b.*?(\d+)\s*(segundos?|s\b|minutos?|min)\b", re.IGNORECASE
)
_LIST_RE = re.compile(
    r"\bv[ií]deos?\b.*\b(grav(?:ou|ados|ei)|criou|criados)\b|\blista\w*\s+.*v[ií]deos?\b", re.IGNORECASE
)
_CUT_RE = re.compile(
    r"\bcort[ae]\w*\s+o\s+v[ií]deo\s+(\S+)\s+de\s+(\d+)\s+a\s+(\d+)\s*segundos?", re.IGNORECASE
)
_SPEEDUP_RE = re.compile(r"\bacelera\w*\s+o\s+v[ií]deo\s+(\S+)\s+em\s+(\d+(?:\.\d+)?)\s*x", re.IGNORECASE)


class VideoCreationPlugin(BasePlugin):
    name = "video_creation"
    description = "Grava e edita vídeos da tela (gravação + corte + aceleração)"
    triggers = [
        "grava minha tela", "grava um vídeo", "grava a tela",
        "vídeos gravados", "corta o vídeo", "acelera o vídeo",
    ]

    def matches(self, text: str) -> bool:
        return bool(
            _RECORD_RE.search(text) or _LIST_RE.search(text)
            or _CUT_RE.search(text) or _SPEEDUP_RE.search(text)
        )

    def handle(self, text: str, context: dict):
        m = _CUT_RE.search(text)
        if m:
            return self._cortar(m.group(1), int(m.group(2)), int(m.group(3)))

        m = _SPEEDUP_RE.search(text)
        if m:
            return self._acelerar(m.group(1), float(m.group(2)))

        if _LIST_RE.search(text):
            return self._listar()

        m = _RECORD_RE.search(text)
        if m:
            valor = int(m.group(1))
            unidade = m.group(2).lower()
            segundos = valor * 60 if unidade.startswith("min") else valor
            return self._gravar(segundos)

        return None

    def _gravar(self, segundos: int):
        if not screen.available():
            return Answer(
                "Instale 'mss' e 'opencv-python' (requirements-visao.txt) pra gravar a tela.",
                Confidence.GUESS,
            )
        segundos_reais = min(segundos, _DURACAO_MAXIMA)
        os.makedirs(VIDEOS_DIR, exist_ok=True)
        nome = f"tela_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        caminho = os.path.join(VIDEOS_DIR, nome)
        try:
            screen.record_screen(caminho, seconds=segundos_reais)
        except Exception as e:
            return Answer(f"Não consegui gravar a tela: {e}", Confidence.GUESS)
        registrar("video_gravado", nome)
        aviso_teto = f" (pedi {segundos}s, mas o teto é {_DURACAO_MAXIMA}s)" if segundos > _DURACAO_MAXIMA else ""
        return Answer(
            f'Gravei {segundos_reais}s da sua tela em "{caminho}"{aviso_teto}. Posso cortar '
            f'("corta o vídeo {nome} de X a Y segundos") ou acelerar '
            f'("acelera o vídeo {nome} em 2x") se quiser.',
            Confidence.CONFIRMED,
        )

    def _listar(self):
        if not os.path.isdir(VIDEOS_DIR):
            return Answer("Ainda não gravei nenhum vídeo.", Confidence.CONFIRMED)
        arquivos = sorted(f for f in os.listdir(VIDEOS_DIR) if f.endswith(".mp4"))
        if not arquivos:
            return Answer("Ainda não gravei nenhum vídeo.", Confidence.CONFIRMED)
        return Answer("Vídeos gravados:\n" + "\n".join(f"- {a}" for a in arquivos), Confidence.CONFIRMED)

    def _resolver_caminho(self, nome: str) -> str:
        # os.path.basename descarta qualquer componente de caminho (barra,
        # contrabarra, "..", letra de unidade) -- sem isso, um nome tipo
        # "C:\Users\alguem\arquivo" faz os.path.join IGNORAR VIDEOS_DIR
        # (join com um caminho absoluto descarta o primeiro argumento) e
        # cortar/acelerar acabam lendo/escrevendo fora de data/videos/.
        nome = os.path.basename(nome)
        if not nome.endswith(".mp4"):
            nome += ".mp4"
        return os.path.join(VIDEOS_DIR, nome)

    def _cortar(self, nome: str, inicio: int, fim: int):
        if not video_edit.available():
            return Answer("Instale 'opencv-python' (requirements-visao.txt) pra editar vídeo.", Confidence.GUESS)
        caminho = self._resolver_caminho(nome)
        if not os.path.isfile(caminho):
            return Answer(f'Não achei o vídeo "{nome}".', Confidence.GUESS)
        saida = caminho[:-4] + f"_corte_{inicio}_{fim}.mp4"
        try:
            video_edit.cortar(caminho, inicio, fim, saida)
        except Exception as e:
            return Answer(f"Não consegui cortar o vídeo: {e}", Confidence.GUESS)
        registrar("video_editado", os.path.basename(saida))
        return Answer(f'Cortei de {inicio}s a {fim}s e salvei em "{saida}".', Confidence.CONFIRMED)

    def _acelerar(self, nome: str, fator: float):
        if not video_edit.available():
            return Answer("Instale 'opencv-python' (requirements-visao.txt) pra editar vídeo.", Confidence.GUESS)
        caminho = self._resolver_caminho(nome)
        if not os.path.isfile(caminho):
            return Answer(f'Não achei o vídeo "{nome}".', Confidence.GUESS)
        saida = caminho[:-4] + f"_{fator}x.mp4"
        try:
            video_edit.acelerar(caminho, fator, saida)
        except Exception as e:
            return Answer(f"Não consegui acelerar o vídeo: {e}", Confidence.GUESS)
        registrar("video_editado", os.path.basename(saida))
        return Answer(f'Acelerei em {fator}x e salvei em "{saida}".', Confidence.CONFIRMED)
