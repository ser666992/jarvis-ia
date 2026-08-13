"""
tests/test_mudanca_ambiente.py
=================================
`VoiceLoop._checar_mudanca_de_ambiente()`: cada gravação já mede o chão
de ruído real do ambiente (voz/stt.py:_gravar_ate_silencio) -- comparar
isso com o que foi medido na última calibração
(`voz.ruido_ambiente_calibrado`) permite sugerir recalibrar quando o
ambiente muda de verdade (mudou de cômodo, ligou um ventilador, etc.),
em vez de deixar a pessoa arcar com cortes de frase sem saber por quê.

Nenhum teste aqui grava/fala de verdade -- STT/TTS são fakes.
"""

import pytest

from voz.loop import VoiceLoop


class _FakeBargeInMonitor:
    """Substitui voz.stt.BargeInMonitor -- sem isso, _falar_interrompivel
    (chamado pelo aviso de mudança de ambiente) tentaria abrir o
    microfone de verdade em background."""

    def __init__(self, *a, **k):
        pass

    def iniciar(self):
        pass

    def parar(self):
        pass

    def interrompido(self):
        return False


@pytest.fixture(autouse=True)
def _sem_barge_in_de_verdade(monkeypatch):
    import voz.loop as loop_module
    monkeypatch.setattr(loop_module, "BargeInMonitor", _FakeBargeInMonitor)


class _FakeTTS:
    def __init__(self):
        self.falas = []

    def available(self):
        return True

    def speak(self, texto, verificar_interromper=None):
        self.falas.append(texto)

    def interromper(self):
        pass


class _FakeJarvis:
    user_id = "teste"

    def process(self, texto):
        return "ok"


def _montar_loop():
    from config.settings import get_settings
    get_settings().set("voz.microfone_calibrado", True)  # não é o wizard que este arquivo testa
    loop = VoiceLoop(_FakeJarvis(), use_wakeword=False)
    loop.tts = _FakeTTS()
    return loop


def test_sem_baseline_calibrado_nao_avisa():
    loop = _montar_loop()  # voz.ruido_ambiente_calibrado nunca foi setado
    loop._checar_mudanca_de_ambiente(2000.0)
    assert loop.tts.falas == []


def test_ruido_atual_none_nao_avisa():
    from config.settings import get_settings
    get_settings().set("voz.ruido_ambiente_calibrado", 100.0)
    loop = _montar_loop()
    loop._checar_mudanca_de_ambiente(None)
    assert loop.tts.falas == []


def test_ruido_parecido_nao_avisa():
    from config.settings import get_settings
    get_settings().set("voz.ruido_ambiente_calibrado", 100.0)
    loop = _montar_loop()
    loop._checar_mudanca_de_ambiente(150.0)  # 1.5x -- dentro da margem
    assert loop.tts.falas == []


def test_ambiente_muito_mais_ruidoso_avisa():
    from config.settings import get_settings
    get_settings().set("voz.ruido_ambiente_calibrado", 100.0)
    loop = _montar_loop()
    loop._checar_mudanca_de_ambiente(400.0)  # 4x -- ventilador ligado, etc.
    assert len(loop.tts.falas) == 1
    assert "calibra o microfone" in loop.tts.falas[0]


def test_ambiente_muito_mais_silencioso_tambem_avisa():
    from config.settings import get_settings
    get_settings().set("voz.ruido_ambiente_calibrado", 500.0)
    loop = _montar_loop()
    loop._checar_mudanca_de_ambiente(50.0)  # 0.1x -- mudou pra um cômodo bem mais silencioso
    assert len(loop.tts.falas) == 1


def test_so_avisa_uma_vez_por_sessao():
    from config.settings import get_settings
    get_settings().set("voz.ruido_ambiente_calibrado", 100.0)
    loop = _montar_loop()
    loop._checar_mudanca_de_ambiente(400.0)
    loop._checar_mudanca_de_ambiente(450.0)
    loop._checar_mudanca_de_ambiente(500.0)
    assert len(loop.tts.falas) == 1
