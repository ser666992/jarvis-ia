"""
tests/test_modo_silencioso.py
================================
"Modo silencioso": liga/desliga `voz.barge_in_ativo` por comando, sem
precisar reiniciar o modo de voz -- voz/loop.py e gui/app.py já
respeitavam essa config antes deste plugin (ver
tests/test_barge_in.py e a lógica em _falar_interrompivel), só faltava
o comando em si.
"""

from plugins.modo_silencioso import ModoSilenciosoPlugin


def test_ativa_modo_silencioso_desliga_barge_in(contexto):
    from config.settings import get_settings
    plugin = ModoSilenciosoPlugin()
    assert plugin.matches("modo silencioso")

    resposta = plugin.handle("modo silencioso", contexto)

    assert get_settings().get("voz.barge_in_ativo") is False
    assert "silencioso" in resposta.text.lower()


def test_sair_do_modo_silencioso_reativa_barge_in(contexto):
    from config.settings import get_settings
    get_settings().set("voz.barge_in_ativo", False)
    plugin = ModoSilenciosoPlugin()
    assert plugin.matches("sai do modo silencioso")

    resposta = plugin.handle("sai do modo silencioso", contexto)

    assert get_settings().get("voz.barge_in_ativo") is True
    assert "interromper" in resposta.text.lower()


def test_desativa_o_barge_in_por_frase_alternativa(contexto):
    from config.settings import get_settings
    plugin = ModoSilenciosoPlugin()
    assert plugin.matches("desativa o barge-in")

    plugin.handle("desativa o barge-in", contexto)

    assert get_settings().get("voz.barge_in_ativo") is False


def test_ativa_o_barge_in_por_frase_alternativa(contexto):
    from config.settings import get_settings
    get_settings().set("voz.barge_in_ativo", False)
    plugin = ModoSilenciosoPlugin()
    assert plugin.matches("ativa o barge-in")

    plugin.handle("ativa o barge-in", contexto)

    assert get_settings().get("voz.barge_in_ativo") is True


def test_nao_confunde_com_frase_nao_relacionada(contexto):
    plugin = ModoSilenciosoPlugin()
    assert not plugin.matches("que horas são")
    assert not plugin.matches("abre o spotify")


# ---------- integração real: voz/loop.py e gui/app.py já respeitam a config ----------

def test_loop_nao_cria_barge_in_monitor_com_modo_silencioso(monkeypatch):
    """Ponta a ponta: plugin liga voz.barge_in_ativo=False -> VoiceLoop
    fala sem monitorar o microfone em paralelo (sem BargeInMonitor)."""
    import voz.loop as loop_module
    from config.settings import get_settings
    from voz.loop import VoiceLoop

    chamado = {"criou_monitor": False}

    class _MonitorNuncaDeveriaSerCriado:
        def __init__(self, *a, **k):
            chamado["criou_monitor"] = True

        def iniciar(self):
            pass

        def parar(self):
            pass

        def interrompido(self):
            return False

    monkeypatch.setattr(loop_module, "BargeInMonitor", _MonitorNuncaDeveriaSerCriado)

    plugin = ModoSilenciosoPlugin()
    plugin.handle("modo silencioso", {"user_id": "t", "jarvis": None, "ia_manager": None, "memory": None})
    assert get_settings().get("voz.barge_in_ativo") is False

    class _FakeJarvis:
        user_id = "teste"

        def process(self, texto):
            return "ok"

    class _FakeTTS:
        def __init__(self):
            self.falas = []

        def available(self):
            return True

        def speak(self, texto, verificar_interromper=None):
            # sem callback == sem barge-in, é a prova de que o modo
            # silencioso está sendo respeitado.
            assert verificar_interromper is None
            self.falas.append(texto)

        def interromper(self):
            pass

    loop = VoiceLoop(_FakeJarvis(), use_wakeword=False)
    loop.tts = _FakeTTS()

    loop._falar_interrompivel("resposta de teste")

    assert chamado["criou_monitor"] is False
    assert loop.tts.falas == ["resposta de teste"]
