"""
tests/test_gui_voice_confidence.py
=====================================
Mesma regressão/correção de tests/test_voice_confidence.py, só que pro
lado da GUI (gui/app.py:MainWindow._on_ouviu) -- transcrição pouco
confiável não pode virar um envio automático pro Jarvis processar.

Roda com QT_QPA_PLATFORM=offscreen (sem precisar de display de
verdade) -- pulado graciosamente se PySide6 não estiver instalado.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pyside6 = pytest.importorskip("PySide6", reason="PySide6 não instalado -- GUI é opcional")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def janela(qapp):
    """MainWindow "nua" -- monta só o suficiente pra testar _on_ouviu()
    sem passar pelo carregamento de verdade do Jarvis (pesado, e fora
    do escopo deste teste)."""
    from PySide6.QtWidgets import QMainWindow
    from gui.app import MainWindow

    win = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(win)
    win.user_id = "teste"
    win.jarvis = object()
    win._worker = None
    win._speak_worker = None
    win._listen_worker = None
    win._loader = None
    win._closing_requested = False
    win._permitir_fechar = False
    win._voice_enabled = True
    import time
    win._resposta_inicio = time.monotonic()
    from PySide6.QtCore import QTimer
    win._pensando_timer = QTimer(win)
    win._pensando_dots = 0
    win._build_ui()
    yield win
    win.deleteLater()


def test_transcricao_confiavel_preenche_e_envia(monkeypatch, janela):
    enviado = {}

    def _fake_on_send():
        enviado["texto"] = janela.input_line.text()

    monkeypatch.setattr(janela, "_on_send", _fake_on_send)
    monkeypatch.setattr(janela, "_falar", lambda *_a: None)

    janela._on_ouviu("abre o spotify", True, "")

    assert enviado.get("texto") == "abre o spotify"


def test_transcricao_pouco_confiavel_nao_envia_pede_repeticao(monkeypatch, janela):
    """O caso real: NÃO pode chamar _on_send() (que mandaria pro
    Jarvis processar) -- só avisa e pede pra repetir."""
    chamou_send = {"sim": False}
    falas = []

    monkeypatch.setattr(janela, "_on_send", lambda: chamou_send.__setitem__("sim", True))
    monkeypatch.setattr(janela, "_falar", lambda texto: falas.append(texto))

    janela._on_ouviu("ora o amargo", False, "volume baixo demais")

    assert chamou_send["sim"] is False
    assert janela.input_line.text() == ""  # nunca preencheu o campo com o texto ruim
    assert any("Não peguei bem" in f for f in falas)


def test_transcricao_vazia_nao_pede_repeticao(monkeypatch, janela):
    """Silêncio de verdade (texto vazio) tem sua própria mensagem
    ("tente de novo") -- não deve confundir com "pode repetir?" de
    transcrição ruim."""
    chamou_send = {"sim": False}
    falas = []

    monkeypatch.setattr(janela, "_on_send", lambda: chamou_send.__setitem__("sim", True))
    monkeypatch.setattr(janela, "_falar", lambda texto: falas.append(texto))

    janela._on_ouviu("", True, "")

    assert chamou_send["sim"] is False
    assert not any("Não peguei bem" in f for f in falas)


def test_neutron_pausa_quando_oculto_e_reinicia_quando_visivel(qapp):
    from PySide6.QtGui import QHideEvent, QShowEvent
    from gui.neutron_core import NeutronCore

    core = NeutronCore()
    assert core._timer.isActive()
    core.hideEvent(QHideEvent())
    assert not core._timer.isActive()
    core.showEvent(QShowEvent())
    assert core._timer.isActive()
    core.deleteLater()
