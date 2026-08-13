"""
tests/test_wakeword_confianca.py
===================================
Gap fechado: `WakeWordDetector.listen_for_command()` (fallback via STT)
tratava o comando dito na MESMA respiração que a palavra-chave
("jarvis, que horas são") como sempre confiável, sem checar volume/
duração como qualquer outra transcrição -- agora usa
`listen_and_transcribe_detalhado()` e devolve
{"texto", "confiavel", "motivo"} igual aos outros caminhos de escuta.

Nenhum teste aqui usa microfone/porcupine de verdade -- o STT é um fake.
"""

from voz.wakeword import WakeWordDetector


class _FakeSTT:
    def __init__(self, resultado):
        self._resultado = resultado

    def available(self):
        return True

    def listen_and_transcribe_detalhado(self, duration_seconds):
        return self._resultado


def test_comando_na_mesma_respiracao_confiavel():
    stt = _FakeSTT({"texto": "jarvis que horas são", "confiavel": True, "motivo": None})
    detector = WakeWordDetector(keyword="jarvis", stt=stt)

    resultado = detector.listen_for_command()

    assert resultado == {"texto": "que horas são", "confiavel": True, "motivo": None}


def test_comando_na_mesma_respiracao_pouco_confiavel_nao_e_mascarado():
    """O caso que motivou o fix: transcrição ruim nesse caminho
    específico não pode sair marcada como confiável incondicionalmente
    -- quem chama (voz/loop.py) precisa saber que é pra pedir repetição."""
    stt = _FakeSTT({"texto": "jarvis ora o amargo", "confiavel": False, "motivo": "volume baixo demais"})
    detector = WakeWordDetector(keyword="jarvis", stt=stt)

    resultado = detector.listen_for_command()

    assert resultado["texto"] == "ora o amargo"
    assert resultado["confiavel"] is False
    assert resultado["motivo"] == "volume baixo demais"


def test_apenas_palavra_chave_sem_comando_ainda():
    stt = _FakeSTT({"texto": "jarvis", "confiavel": True, "motivo": None})
    detector = WakeWordDetector(keyword="jarvis", stt=stt)

    resultado = detector.listen_for_command()

    assert resultado == {"texto": "", "confiavel": True, "motivo": None}


def test_palavra_chave_nao_detectada_retorna_none():
    stt = _FakeSTT({"texto": "que horas são", "confiavel": True, "motivo": None})
    detector = WakeWordDetector(keyword="jarvis", stt=stt)

    assert detector.listen_for_command() is None


def test_qualquer_palavra_chave_da_lista_ativa():
    stt = _FakeSTT({"texto": "ark liga a luz", "confiavel": True, "motivo": None})
    detector = WakeWordDetector(keywords=["jarvis", "ark"], stt=stt)

    resultado = detector.listen_for_command()

    assert resultado["texto"] == "liga a luz"
    assert resultado["confiavel"] is True
