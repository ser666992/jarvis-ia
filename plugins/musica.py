"""
plugins/musica.py
====================
Tocar música por comando, no Spotify ou no YouTube, e controlar a
reprodução (pausar/próxima/anterior) via teclas de mídia.

Ver automacao/musica.py pros detalhes/limitações honestas (YouTube toca
de verdade via automação; Spotify abre na busca pra você dar play).

Comandos:
    "toca <música> no spotify" / "toca <música> no youtube" / "toca <música>"
    "pausa a música" / "continua a música" / "play"
    "próxima música" / "música anterior"
    "para a música"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_TOCAR_RE = re.compile(
    r"\b(?:toc[ae]\w*|coloc[ae]\w*|põe|poe|bota)\b\s+(?:a\s+m[úu]sica\s+|a\s+|o\s+|umas?\s+)?(.+)",
    re.IGNORECASE,
)
_PAUSE_RE = re.compile(r"\b(pausa\w*|paus[ae]|congela)\b.*\bm[úu]sica\b|\bpausa\s+a\s+m[úu]sica\b", re.IGNORECASE)
_PLAY_RE = re.compile(r"\b(continu[ae]\w*|retom[ae]\w*|volta\w*)\b.*\bm[úu]sica\b|\bd[áa]\s+play\b|\bplay\b", re.IGNORECASE)
_NEXT_RE = re.compile(r"\b(pr[óo]xim[ao]|pula|avan[çc]a\w*)\b.*\bm[úu]sica\b|\bpr[óo]xima\s+m[úu]sica\b", re.IGNORECASE)
_PREV_RE = re.compile(r"\b(anterior|volta\w*)\b.*\bm[úu]sica\b|\bm[úu]sica\s+anterior\b", re.IGNORECASE)
_STOP_RE = re.compile(r"\b(par[ae]\w*|desliga\w*)\b\s+(?:a\s+)?m[úu]sica\b", re.IGNORECASE)


class MusicaPlugin(BasePlugin):
    name = "musica"
    description = "Toca música no Spotify/YouTube e controla a reprodução (pausar, próxima, anterior)"
    triggers = ["toca ", "coloca a musica", "põe a musica", "pausa a musica", "próxima musica", "para a musica", "dá play"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        # controles de reprodução (checados de forma independente)
        if (_STOP_RE.search(t) or _PAUSE_RE.search(t) or _NEXT_RE.search(t)
                or _PREV_RE.search(t) or _PLAY_RE.search(t)):
            return True
        # "toca X" -- mas não "toca no computador"/frases sem alvo real
        m = _TOCAR_RE.search(t)
        return bool(m and m.group(1).strip())

    def handle(self, text: str, context: dict):
        t = text.strip()

        # Controles primeiro (mais específicos).
        if _STOP_RE.search(t):
            return self._parar()
        if _NEXT_RE.search(t):
            return self._media("next_track", "Próxima música.")
        if _PREV_RE.search(t):
            return self._media("prev_track", "Música anterior.")
        if _PAUSE_RE.search(t):
            return self._media("play_pause", "Pausei/retomei a música.")
        # "play"/"continua" só como controle quando não é "toca <algo>"
        if _PLAY_RE.search(t) and not _TOCAR_RE.search(t):
            return self._media("play_pause", "Play/pause.")

        m = _TOCAR_RE.search(t)
        if not m:
            return None
        pedido = m.group(1).strip(" .!?")
        servico = None
        # extrai "no spotify"/"no youtube" do fim e tira do nome da música
        ms = re.search(r"\b(?:no|na|pelo|pela)\s+(spotify|youtube|yt)\b", pedido, re.IGNORECASE)
        if ms:
            servico = ms.group(1).lower()
            pedido = pedido[:ms.start()].strip(" ,.!?")
        if not pedido:
            return Answer("Tocar qual música?", Confidence.GUESS)
        return self._tocar(pedido, servico)

    def _tocar(self, pedido: str, servico):
        from automacao import musica
        try:
            msg = musica.tocar(pedido, servico)
        except Exception as e:
            return Answer(f"Não consegui tocar: {e}", Confidence.GUESS)
        return Answer(msg, Confidence.CONFIRMED)

    def _parar(self):
        from automacao import musica, media_keys
        parou = musica.parar_youtube()
        if not parou and media_keys.available():
            try:
                media_keys.stop_media()
            except Exception:
                pass
        return Answer("Parei a música.", Confidence.CONFIRMED)

    def _media(self, acao: str, ok_msg: str):
        from automacao import media_keys
        if not media_keys.available():
            return Answer("Controle de mídia por tecla só funciona no Windows.", Confidence.GUESS)
        try:
            getattr(media_keys, acao)()
        except Exception as e:
            return Answer(f"Não consegui controlar a mídia: {e}", Confidence.GUESS)
        return Answer(ok_msg, Confidence.CONFIRMED)
