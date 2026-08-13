"""
tests/test_jogos_gravador.py
===============================
Sessão de gravação de demonstração (jogos/gravador.py) -- mesmo padrão
de tests/test_barge_in.py: thread de fundo de verdade, mas toda
dependência de hardware (pynput, captura de tela) é substituída por
fake, e a temporização usa sleeps curtos reais + fps alto (não
segundos de verdade esperando o teto de duração, que é de minutos).
"""

import time

import numpy as np
import pytest

import jogos.gravador as gravador


class _ListenerFalso:
    """Substitui pynput.keyboard.Listener/pynput.mouse.Listener --
    start()/stop() não fazem nada de verdade (os testes chamam os
    callbacks _on_press/_on_release/_on_move/_on_click diretamente,
    simulando o que o pynput real dispararia)."""

    def __init__(self, **kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class _FakeKeyCode:
    def __init__(self, char):
        self.char = char
        self.name = None


def _frame_falso(monitor_index=1):
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture(autouse=True)
def _sem_hardware_de_verdade(monkeypatch):
    monkeypatch.setattr(gravador, "_pynput_keyboard", type("M", (), {"Listener": _ListenerFalso}))
    monkeypatch.setattr(gravador, "_pynput_mouse", type("M", (), {"Listener": _ListenerFalso}))
    monkeypatch.setattr(gravador, "HAS_PYNPUT", True)

    import visao.screen as screen_module
    monkeypatch.setattr(screen_module, "screenshot", _frame_falso)
    monkeypatch.setattr(screen_module, "available", lambda: True)

    from config.settings import get_settings
    get_settings().set("jogos.taxa_quadros_por_segundo", 50)  # 20ms/tick -- rápido pro teste não demorar

    yield
    # limpeza: garante que nenhuma gravação fique "presa" ativa entre testes
    if gravador.ativa():
        gravador.parar_gravacao()


def test_available_reflete_dependencias(monkeypatch):
    import visao.screen as screen_module
    monkeypatch.setattr(gravador, "HAS_PYNPUT", True)
    monkeypatch.setattr(screen_module, "available", lambda: True)
    assert gravador.available() is True

    monkeypatch.setattr(gravador, "HAS_PYNPUT", False)
    assert gravador.available() is False


def test_iniciar_gravacao_levanta_erro_sem_dependencia(monkeypatch):
    monkeypatch.setattr(gravador, "HAS_PYNPUT", False)
    with pytest.raises(RuntimeError):
        gravador.iniciar_gravacao("jogo teste")


def test_iniciar_gravacao_duas_vezes_levanta_erro():
    gravador.iniciar_gravacao("jogo teste", duracao_minutos=0.5)
    with pytest.raises(RuntimeError):
        gravador.iniciar_gravacao("outro jogo", duracao_minutos=0.5)
    gravador.parar_gravacao()


def test_duracao_respeita_piso_e_teto(monkeypatch):
    from config.settings import get_settings
    get_settings().set("jogos.duracao_maxima_demonstracao_minutos", 5.0)

    resultado = gravador.iniciar_gravacao("jogo teste", duracao_minutos=100.0)  # bem acima do teto
    assert resultado["duracao_minutos"] == 5.0
    gravador.parar_gravacao()

    resultado = gravador.iniciar_gravacao("jogo teste", duracao_minutos=0.001)  # bem abaixo do piso
    assert resultado["duracao_minutos"] == 0.5
    gravador.parar_gravacao()


def test_para_sozinha_quando_o_tempo_previsto_passa():
    """Em vez de esperar minutos de verdade, força fim_previsto pro
    passado logo após iniciar -- a própria thread deve perceber e
    encerrar sozinha, sem precisar de parar_gravacao()."""
    gravador.iniciar_gravacao("jogo teste", duracao_minutos=0.5)
    gravador._estado["fim_previsto"] = time.time() - 1
    thread = gravador._estado["_thread"]
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert gravador.ativa() is False


def test_grava_frames_e_acoes_com_teclas_seguradas(tmp_path, monkeypatch):
    from jogos import armazenamento
    monkeypatch.setattr(armazenamento, "DADOS_DIR", str(tmp_path))

    gravador.iniciar_gravacao("jogo teste", duracao_minutos=0.5)
    gravador._on_press(_FakeKeyCode("w"))
    time.sleep(0.15)  # alguns ticks a 50fps
    gravador._on_release(_FakeKeyCode("w"))
    time.sleep(0.05)
    resultado = gravador.parar_gravacao()

    assert resultado["parou"] is True
    assert resultado["n_quadros"] > 0
    assert resultado["nome_jogo"] == "jogo teste"
    assert resultado["caminho"].endswith(".npz")

    dados = np.load(resultado["caminho"])
    assert dados["frames"].shape[0] == resultado["n_quadros"]
    assert dados["acoes"].shape == (resultado["n_quadros"], 21)
    assert dados["sinais_movimento"].shape == (resultado["n_quadros"],)
    # pelo menos um quadro deve ter capturado a tecla "w" segurada
    from jogos.captura import NOMES_TECLAS
    idx_w = NOMES_TECLAS.index("w")
    assert dados["acoes"][:, idx_w].max() == 1.0


def test_parar_sem_gravacao_ativa_nao_quebra():
    resultado = gravador.parar_gravacao()
    assert resultado == {"parou": False, "n_quadros": 0, "caminho": "", "nome_jogo": ""}


def test_mouse_e_clique_sao_capturados(tmp_path, monkeypatch):
    from jogos import armazenamento
    monkeypatch.setattr(armazenamento, "DADOS_DIR", str(tmp_path))

    class _FakeButton:
        def __init__(self, nome):
            self._nome = nome

        def __str__(self):
            return f"Button.{self._nome}"

    gravador.iniciar_gravacao("jogo teste", duracao_minutos=0.5)
    gravador._on_move(0, 0)
    gravador._on_move(50, 30)  # dx=50, dy=30
    gravador._on_click(50, 30, _FakeButton("left"), True)
    time.sleep(0.1)
    gravador._on_click(50, 30, _FakeButton("left"), False)
    resultado = gravador.parar_gravacao()

    dados = np.load(resultado["caminho"])
    from jogos.captura import NOMES_TECLAS
    n_teclas = len(NOMES_TECLAS)
    idx_clique_esq = n_teclas + 2
    assert dados["acoes"][:, idx_clique_esq].max() == 1.0  # clique esquerdo foi capturado em algum quadro
