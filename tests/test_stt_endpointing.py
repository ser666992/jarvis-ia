"""
tests/test_stt_endpointing.py
================================
_gravar_ate_silencio() (voz/stt.py) precisa parar de gravar assim que
QUALQUER UM dos dois sinais disparar primeiro:
  1. RMS calibrado no ambiente (silêncio de verdade depois de falar).
  2. Endpointing do vosk (`recognizer_ao_vivo.AcceptWaveform()` == True) --
     o decodificador decidindo, pelo MODELO acústico, que a frase acabou.

Testado aqui com um microfone e um reconhecedor FALSOS (nenhum destes
testes usa hardware de áudio nem carrega um modelo do vosk de verdade
-- ambos são simulados, então rodam em qualquer máquina/CI).
"""

import numpy as np
import pytest

from voz.stt import SpeechToText


class _BlocoFalso:
    """Substitui o retorno de `sd.InputStream.read()` -- só o método
    `.astype()`/`.copy()` usados por _gravar_ate_silencio importam."""


class _StreamFalso:
    """Substitui `sd.InputStream` -- entrega os blocos pré-definidos em
    ordem, depois cai pra silêncio (zeros) indefinidamente, pra nunca
    travar um teste com bug (o teto por tempo do próprio
    _gravar_ate_silencio sempre segura o loop mesmo se o critério que
    o teste espera não disparar)."""

    def __init__(self, blocos, tamanho_bloco):
        self._blocos = list(blocos)
        self._i = 0
        self._tamanho_bloco = tamanho_bloco

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self, tamanho):
        if self._i < len(self._blocos):
            bloco = self._blocos[self._i]
            self._i += 1
        else:
            bloco = np.zeros((tamanho, 1), dtype="int16")
        return bloco, False


def _bloco(amplitude: int, tamanho: int) -> np.ndarray:
    """Bloco "constante" na amplitude dada -- alto o bastante pra ser
    reconhecido como fala quando amplitude > 0, silêncio quando 0."""
    return np.full((tamanho, 1), amplitude, dtype="int16")


class _RecognizerAoVivoFalso:
    """Substitui um vosk.KaldiRecognizer -- sinaliza "frase terminou"
    (AcceptWaveform retorna True) a partir da N-ésima chamada."""

    def __init__(self, termina_na_chamada: int = None):
        self._chamadas = 0
        self._termina_na_chamada = termina_na_chamada

    def AcceptWaveform(self, _data):
        self._chamadas += 1
        if self._termina_na_chamada is None:
            return False
        return self._chamadas >= self._termina_na_chamada


@pytest.fixture
def stt():
    return SpeechToText(language="pt-BR")


def _preparar_stream_falso(monkeypatch, blocos):
    import voz.stt as stt_module

    def _fake_input_stream(**kwargs):
        return _StreamFalso(blocos, kwargs.get("blocksize", 480))

    monkeypatch.setattr(stt_module.sd, "InputStream", _fake_input_stream)


# blocos de 30ms a 16kHz -> 480 amostras cada
_TAMANHO_BLOCO = 480


def test_endpoint_por_reconhecimento_para_antes_do_rms(monkeypatch, stt):
    """Fala CONTÍNUA (amplitude alta, sem nenhuma pausa) -- o critério
    de RMS NUNCA dispararia sozinho (não há silêncio nenhum na
    gravação). Só o endpointing via reconhecimento deve conseguir
    parar a gravação, e precisa fazer isso ANTES do teto máximo."""
    # ~8 blocos de calibração (silêncio) + fala alta contínua depois,
    # blocos o bastante pra passar da duração mínima (0.6s / 0.03s ~= 20).
    blocos = [_bloco(0, _TAMANHO_BLOCO) for _ in range(8)] + [_bloco(20000, _TAMANHO_BLOCO) for _ in range(40)]
    _preparar_stream_falso(monkeypatch, blocos)

    recognizer = _RecognizerAoVivoFalso(termina_na_chamada=25)
    audio, samplerate, metadados = stt._gravar_ate_silencio(
        duracao_maxima=12.0, recognizer_ao_vivo=recognizer,
    )

    assert metadados["endpoint_por_reconhecimento"] is True
    assert metadados["falou"] is True
    # parou bem antes do teto de 12s (nem chegaria perto, já que fala é
    # contínua e só o endpointing via reconhecimento pode ter parado isso)
    assert metadados["duracao_segundos"] < 3.0


def test_sem_recognizer_continua_so_no_rms(monkeypatch, stt):
    """Sem `recognizer_ao_vivo` (o caso do faster-whisper, ou vosk
    antes desta melhoria), o comportamento tem que continuar
    IDÊNTICO: só o RMS decide -- fala, depois silêncio de verdade."""
    silencio = [_bloco(0, _TAMANHO_BLOCO) for _ in range(8)]
    fala = [_bloco(20000, _TAMANHO_BLOCO) for _ in range(15)]
    silencio_final = [_bloco(0, _TAMANHO_BLOCO) for _ in range(40)]  # bloco de sobra, mais que o suficiente pro timeout de silêncio
    _preparar_stream_falso(monkeypatch, silencio + fala + silencio_final)

    audio, samplerate, metadados = stt._gravar_ate_silencio(duracao_maxima=12.0, recognizer_ao_vivo=None)

    assert metadados["endpoint_por_reconhecimento"] is False
    assert metadados["falou"] is True
    # parou por silêncio bem antes do teto de 12s
    assert metadados["duracao_segundos"] < 3.0


def test_recognizer_nunca_termina_cai_pro_rms(monkeypatch, stt):
    """recognizer_ao_vivo presente mas nunca "decide" que terminou
    (ex.: engasgou, ou o vosk raramente endpointa aquela frase) -- o
    RMS continua funcionando como rede de segurança, sem travar pra
    sempre."""
    silencio = [_bloco(0, _TAMANHO_BLOCO) for _ in range(8)]
    fala = [_bloco(20000, _TAMANHO_BLOCO) for _ in range(15)]
    silencio_final = [_bloco(0, _TAMANHO_BLOCO) for _ in range(40)]
    _preparar_stream_falso(monkeypatch, silencio + fala + silencio_final)

    recognizer = _RecognizerAoVivoFalso(termina_na_chamada=None)  # nunca retorna True
    audio, samplerate, metadados = stt._gravar_ate_silencio(duracao_maxima=12.0, recognizer_ao_vivo=recognizer)

    assert metadados["endpoint_por_reconhecimento"] is False
    assert metadados["falou"] is True
    assert metadados["duracao_segundos"] < 3.0


def test_endpoint_por_reconhecimento_respeita_duracao_minima(monkeypatch, stt):
    """Mesmo que o reconhecedor "decida" que terminou quase
    imediatamente, a gravação não pode parar antes da duração mínima
    (proteção contra cortar na respiração inicial, já existente pro
    critério de RMS -- precisa valer pro endpointing também)."""
    blocos = [_bloco(0, _TAMANHO_BLOCO) for _ in range(8)] + [_bloco(20000, _TAMANHO_BLOCO) for _ in range(40)]
    _preparar_stream_falso(monkeypatch, blocos)

    # termina na primeira chamada depois da calibração -- bem antes da
    # duração mínima de 0.6s (~20 blocos de 30ms)
    recognizer = _RecognizerAoVivoFalso(termina_na_chamada=1)
    audio, samplerate, metadados = stt._gravar_ate_silencio(duracao_maxima=12.0, recognizer_ao_vivo=recognizer)

    assert metadados["duracao_segundos"] >= 0.6
