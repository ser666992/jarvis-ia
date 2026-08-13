"""
tests/test_calibracao_inicial.py
===================================
Pedido explícito do usuário: "antes de iniciar o jarvis ele pede pra
configurar e você fala algumas frases pra salvar no microfone" --
`VoiceLoop._calibrar_se_necessario()` guia essa calibração ANTES do
primeiro turno de verdade, mas só na primeira vez que o modo de voz é
usado (`voz.microfone_calibrado`, ver config.example.json).

Nenhum teste aqui grava áudio de verdade -- STT/TTS são fakes.
"""

from voz.loop import VoiceLoop


class _FakeSTT:
    def __init__(self, resultado_calibracao=None, falha_calibracao=None, disponivel=True):
        self._resultado_calibracao = resultado_calibracao or {
            "ruido_ambiente_rms": 120.0,
            "rms_max": 9000.0,
            "maior_pausa_interna_segundos": 0.5,
            "silencio_recomendado_segundos": 0.65,
            "sensibilidade_barge_in_recomendada": 3.1,
            "qualidade": "boa",
            "aviso": None,
        }
        self._falha_calibracao = falha_calibracao
        self._disponivel = disponivel
        self.chamadas_calibracao = 0

    def available(self):
        return self._disponivel

    def calibrar_microfone(self):
        self.chamadas_calibracao += 1
        if self._falha_calibracao:
            raise self._falha_calibracao
        return self._resultado_calibracao

    def listen_and_transcribe_detalhado(self, duration_seconds):
        # texto não-vazio -- só pra deixar run(max_turns=1) completar um
        # turno e sair, em vez de girar pra sempre num "não disse nada".
        return {"texto": "oi", "confiavel": True, "motivo": None}


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


def _montar_loop(stt):
    loop = VoiceLoop(_FakeJarvis(), use_wakeword=False)
    loop.stt = stt
    loop.tts = _FakeTTS()
    return loop


def test_primeira_vez_dispara_calibracao_e_salva_config():
    from config.settings import get_settings
    assert get_settings().get("voz.microfone_calibrado", False) is False

    stt = _FakeSTT()
    loop = _montar_loop(stt)

    loop._calibrar_se_necessario()

    assert stt.chamadas_calibracao == 1
    assert get_settings().get("voz.microfone_calibrado") is True
    assert get_settings().get("voz.silencio_para_parar_segundos") == 0.65
    assert get_settings().get("voz.sensibilidade_barge_in") == 3.1
    # avisa a pessoa por voz que vai calibrar e quando terminou
    assert any("calibrar" in f.lower() for f in loop.tts.falas)
    assert any("prontinho" in f.lower() or "calibrei" in f.lower() for f in loop.tts.falas)


def test_nao_recalibra_se_ja_calibrado():
    from config.settings import get_settings
    get_settings().set("voz.microfone_calibrado", True)
    get_settings().save()

    stt = _FakeSTT()
    loop = _montar_loop(stt)

    loop._calibrar_se_necessario()

    assert stt.chamadas_calibracao == 0
    assert loop.tts.falas == []


def test_sem_motor_de_voz_disponivel_nao_quebra():
    stt = _FakeSTT(disponivel=False)
    loop = _montar_loop(stt)

    loop._calibrar_se_necessario()  # não deve levantar

    assert stt.chamadas_calibracao == 0


def test_falha_na_calibracao_nao_quebra_e_nao_marca_como_calibrado():
    from config.settings import get_settings

    stt = _FakeSTT(falha_calibracao=RuntimeError("microfone ocupado"))
    loop = _montar_loop(stt)

    loop._calibrar_se_necessario()  # não deve levantar

    assert stt.chamadas_calibracao == 1
    assert get_settings().get("voz.microfone_calibrado", False) is False


def test_run_chama_calibracao_antes_do_primeiro_turno(monkeypatch):
    import voz.loop as loop_module

    class _FakeBargeInMonitor:
        def __init__(self, *a, **k):
            pass

        def iniciar(self):
            pass

        def parar(self):
            pass

        def interrompido(self):
            return False

    monkeypatch.setattr(loop_module, "BargeInMonitor", _FakeBargeInMonitor)

    stt = _FakeSTT()
    loop = _montar_loop(stt)

    loop.run(max_turns=1)

    assert stt.chamadas_calibracao == 1
