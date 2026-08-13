"""
tests/test_voice_confidence.py
=================================
Regressão real reportada: uma transcrição ruim ("ora o amargo" em vez
do que foi dito de verdade) ia direto pro Jarvis processar como se
fosse o pedido real, gerando uma resposta sem nexo -- mesmo o sistema
já calculando `confiavel=False` pra esse caso
(voz/stt.py:listen_and_transcribe_detalhado). `voz/loop.py` e
`gui/app.py` agora checam essa confiança ANTES de mandar pro Jarvis:
`confiavel=False` vira "não peguei bem, pode repetir?" em vez de uma
tentativa de adivinhar sentido numa transcrição capenga.

Nenhum teste aqui grava áudio de verdade nem fala de verdade -- STT,
TTS, BargeInMonitor e o Jarvis em si são todos fakes.
"""

from voz.loop import VoiceLoop


class _FakeSTT:
    def __init__(self, resultados):
        # cada chamada consome o próximo resultado da lista -- permite
        # simular vários turnos (ex.: 1 turno ruim seguido de 1 bom).
        self._resultados = list(resultados)

    def available(self):
        return True

    def listen_and_transcribe_detalhado(self, duration_seconds):
        return self._resultados.pop(0)


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
    def __init__(self):
        self.user_id = "teste"
        self.processados = []

    def process(self, texto):
        self.processados.append(texto)
        return f"resposta pra: {texto}"


class _FakeBargeInMonitor:
    """Substitui voz.stt.BargeInMonitor -- sem isso, _falar_interrompivel
    tentaria abrir o microfone de verdade em background."""

    def __init__(self, *a, **k):
        pass

    def iniciar(self):
        pass

    def parar(self):
        pass

    def interrompido(self):
        return False


def _montar_loop(monkeypatch, resultados):
    import voz.loop as loop_module
    monkeypatch.setattr(loop_module, "BargeInMonitor", _FakeBargeInMonitor)

    # já calibrado -- estes testes cobrem o gate de confiança de cada
    # turno, não o assistente de calibração inicial (ver
    # tests/test_calibracao_inicial.py), então evita que o wizard rode
    # e consuma/poe uma fala extra antes das que o teste espera.
    from config.settings import get_settings
    get_settings().set("voz.microfone_calibrado", True)

    jarvis = _FakeJarvis()
    loop = VoiceLoop(jarvis, use_wakeword=False)
    loop.stt = _FakeSTT(resultados)
    loop.tts = _FakeTTS()
    return loop, jarvis


def test_transcricao_confiavel_vai_direto_pro_jarvis(monkeypatch):
    loop, jarvis = _montar_loop(monkeypatch, [
        {"texto": "que horas são", "confiavel": True, "motivo": None},
    ])
    loop.run(max_turns=1)

    assert jarvis.processados == ["que horas são"]
    assert loop.tts.falas == ["resposta pra: que horas são"]


def test_transcricao_pouco_confiavel_pede_pra_repetir_sem_processar(monkeypatch):
    """O caso real que motivou isto: transcrição ruim NÃO pode virar
    uma chamada a jarvis.process() -- só um pedido de repetição."""
    loop, jarvis = _montar_loop(monkeypatch, [
        {"texto": "ora o amargo", "confiavel": False, "motivo": "volume baixo demais"},
        {"texto": "quais animais moram na amazônia", "confiavel": True, "motivo": None},
    ])
    loop.run(max_turns=1)

    # nenhum turno "conta" (max_turns=1) até uma transcrição CONFIÁVEL
    # ser processada -- então o loop consome os dois resultados
    # preparados (o ruim primeiro, pedindo repetição; o bom depois,
    # processado de verdade).
    assert jarvis.processados == ["quais animais moram na amazônia"]
    assert "Não peguei bem" in loop.tts.falas[0]
    assert loop.tts.falas[1] == "resposta pra: quais animais moram na amazônia"


def test_transcricao_vazia_nao_conta_como_turno_nem_pede_repeticao(monkeypatch):
    """Silêncio/nada dito (texto vazio, mas confiavel=True -- ver
    voz/stt.py:_avaliar_qualidade) não deve gerar "pode repetir?" --
    só um "não disse nada" de verdade, não uma transcrição ruim."""
    loop, jarvis = _montar_loop(monkeypatch, [
        {"texto": "", "confiavel": True, "motivo": None},
        {"texto": "abre o spotify", "confiavel": True, "motivo": None},
    ])
    loop.run(max_turns=1)

    assert jarvis.processados == ["abre o spotify"]
    assert all("Não peguei bem" not in f for f in loop.tts.falas)
