"""
tests/test_barge_in.py
=========================
Barge-in: interromper a fala do Jarvis ao detectar que o usuário
começou a falar por cima (voz/stt.py:BargeInMonitor +
voz/tts.py:TextToSpeech.speak(verificar_interromper=...)).

Nenhum teste aqui usa hardware de áudio de verdade nem faz o
computador falar de verdade -- microfone (sounddevice) e motores de
fala (pyttsx3/SAPI) são todos substituídos por fakes.
"""

import numpy as np
import pytest

from voz.stt import BargeInMonitor
from voz.tts import TextToSpeech


# ---------- BargeInMonitor (detecção por volume) ----------

class _StreamFalso:
    def __init__(self, blocos):
        self._blocos = list(blocos)
        self._i = 0

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


def _bloco(amplitude: int, tamanho: int = 480) -> np.ndarray:
    return np.full((tamanho, 1), amplitude, dtype="int16")


def _preparar_stream_falso(monkeypatch, blocos):
    import voz.stt as stt_module
    monkeypatch.setattr(stt_module.sd, "InputStream", lambda **kw: _StreamFalso(blocos))


def test_barge_in_detecta_fala_alta_sustentada(monkeypatch):
    silencio = [_bloco(0) for _ in range(6)]
    fala_alta = [_bloco(20000) for _ in range(20)]
    _preparar_stream_falso(monkeypatch, silencio + fala_alta)

    monitor = BargeInMonitor()
    monitor.iniciar()
    monitor._thread.join(timeout=2.0)  # a própria thread termina sozinha ao detectar
    resultado = monitor.interrompido()
    monitor.parar()

    assert resultado is True


def test_barge_in_ignora_ambiente_calmo(monkeypatch):
    """Sem nenhum som acima do ruído ambiente calibrado, nunca deve
    disparar -- os blocos "de sobra" (silêncio) simulam o Jarvis
    falando sem ninguém interrompendo. `parar()` (não só join) é
    essencial aqui -- sem nunca disparar, a thread ficaria girando pra
    sempre lendo os zeros "de sobra" do stream falso."""
    blocos = [_bloco(0) for _ in range(6)] + [_bloco(50) for _ in range(30)]
    _preparar_stream_falso(monkeypatch, blocos)

    monitor = BargeInMonitor()
    monitor.iniciar()
    import time
    time.sleep(0.3)
    monitor.parar()

    assert monitor.interrompido() is False


def test_barge_in_ignora_pico_isolado(monkeypatch):
    """Um "pop" de um bloco só (tossida, clique) não deve disparar --
    só volume ALTO SUSTENTADO por vários blocos seguidos conta."""
    blocos = (
        [_bloco(0) for _ in range(6)]
        + [_bloco(20000) for _ in range(1)]  # só 1 bloco alto -- abaixo do mínimo sustentado
        + [_bloco(0) for _ in range(30)]
    )
    _preparar_stream_falso(monkeypatch, blocos)

    monitor = BargeInMonitor()
    monitor.iniciar()
    import time
    time.sleep(0.3)
    monitor.parar()

    assert monitor.interrompido() is False


def test_barge_in_parar_encerra_a_thread(monkeypatch):
    blocos = [_bloco(0) for _ in range(6)] + [_bloco(50) for _ in range(200)]
    _preparar_stream_falso(monkeypatch, blocos)

    monitor = BargeInMonitor()
    monitor.iniciar()
    monitor.parar()
    assert monitor._thread is None


# ---------- TextToSpeech: interrupção do motor pyttsx3 ----------

class _EngineFalso:
    """Substitui pyttsx3.init() -- runAndWait() simula uma fala
    "longa" (dorme em pequenos passos), checando a cada passo se
    stop() já foi chamado, pra terminar mais cedo quando for."""

    def __init__(self):
        self.parado = False
        self.textos = []

    def setProperty(self, *_a, **_k):
        pass

    def getProperty(self, nome):
        return [] if nome == "voices" else None

    def say(self, texto):
        self.textos.append(texto)

    def runAndWait(self):
        import time
        for _ in range(100):  # até 1s (100 * 10ms) -- interrompido bem antes nos testes
            if self.parado:
                return
            time.sleep(0.01)

    def stop(self):
        self.parado = True


@pytest.fixture
def tts_pyttsx3(monkeypatch):
    import voz.tts as tts_module
    monkeypatch.setattr(tts_module, "HAS_PYTTSX3", True)
    monkeypatch.setattr(tts_module, "HAS_SAPI_COM", False)
    t = TextToSpeech()
    t._engine = _EngineFalso()
    # _ensure_engine() só cria se self._engine for None -- já preenchido
    # acima com o fake, então _ensure_engine() vira no-op na prática.
    return t


def test_speak_pyttsx3_interrompe_quando_callback_diz_sim(tts_pyttsx3):
    chamadas = {"n": 0}

    def _verificar():
        chamadas["n"] += 1
        return chamadas["n"] >= 3  # "detecta" a interrupção na 3a checagem

    tts_pyttsx3.speak("um texto qualquer bem longo", verificar_interromper=_verificar)

    assert tts_pyttsx3._engine.parado is True


def test_speak_pyttsx3_sem_callback_nao_interrompe(tts_pyttsx3):
    """Sem verificar_interromper, comportamento idêntico a antes --
    runAndWait() roda até o fim (aqui, até o "silêncio" do fake, que
    não chama stop() sozinho)."""
    tts_pyttsx3._engine.parado = True  # runAndWait() "termina" na hora, só pra teste ser rápido
    tts_pyttsx3.speak("um texto qualquer")
    # não deveria ter tentado interromper por conta própria
    assert tts_pyttsx3._engine.textos == ["um texto qualquer"]


def test_interromper_nao_quebra_sem_nada_tocando():
    """interromper() precisa ser seguro de chamar mesmo se nada
    estiver tocando (ex.: barge-in disparou bem no instante em que a
    fala já tinha terminado sozinha)."""
    t = TextToSpeech()
    t.interromper()  # não deve levantar
