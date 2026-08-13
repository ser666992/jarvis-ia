"""
tests/test_jogos_jogador.py
==============================
Loop de auto-jogo (jogos/jogador.py) -- captura de tela, controle de
mouse/teclado (controle_pc.entrada) e janela em foco (pygetwindow) são
todos fakes. Cobre as duas medidas de segurança que mais importam
aqui: só manda entrada com a janela do jogo em foco, e solta toda
tecla segurada ao pausar/parar.
"""

import os
import time

import numpy as np
import pytest

import jogos.jogador as jogador
from jogos import armazenamento
from jogos.captura import N_FRAMES_EMPILHADOS, NOMES_TECLAS, TAMANHO_FRAME
from jogos.modelo import PoliticaJogo, salvar


class _FakeEntrada:
    def __init__(self, disponivel=True):
        self._disponivel = disponivel
        self.chamadas = []

    def available(self):
        return self._disponivel

    def segurar_tecla(self, tecla):
        self.chamadas.append(("segurar", tecla))

    def soltar_tecla(self, tecla):
        self.chamadas.append(("soltar", tecla))

    def mover_mouse_relativo(self, dx, dy):
        self.chamadas.append(("mover", dx, dy))

    def clicar(self, botao="left"):
        self.chamadas.append(("clicar", botao))


class _FakeJanela:
    def __init__(self, titulo):
        self.title = titulo


class _FakeGW:
    def __init__(self, titulo_ativo="Meu Jogo - Janela"):
        self.titulo_ativo = titulo_ativo

    def getActiveWindow(self):
        return _FakeJanela(self.titulo_ativo) if self.titulo_ativo else None


def _frame_falso(cor=128):
    return np.full((240, 320, 3), cor, dtype=np.uint8)


@pytest.fixture
def fake_entrada(monkeypatch):
    fake = _FakeEntrada()
    import controle_pc.entrada as entrada_module
    monkeypatch.setattr(jogador, "HAS_PYGETWINDOW", True)
    for nome in ("segurar_tecla", "soltar_tecla", "mover_mouse_relativo", "clicar", "available"):
        monkeypatch.setattr(entrada_module, nome, getattr(fake, nome))
    return fake


@pytest.fixture
def fake_gw(monkeypatch):
    fake = _FakeGW()
    monkeypatch.setattr(jogador, "gw", fake)
    return fake


@pytest.fixture(autouse=True)
def _dados_isolados(tmp_path, monkeypatch):
    monkeypatch.setattr(armazenamento, "DADOS_DIR", str(tmp_path))
    yield
    if jogador.ativa():
        jogador.parar_jogo()


def _treinar_politica_falsa(nome_jogo: str):
    salvar(PoliticaJogo(), armazenamento.caminho_politica(nome_jogo))


# ---------- disponibilidade / validações antes de iniciar ----------

def test_available_combina_todas_as_dependencias(fake_entrada, monkeypatch):
    import visao.screen as screen_module
    monkeypatch.setattr(screen_module, "available", lambda: True)
    assert jogador.available() is True

    monkeypatch.setattr(jogador, "HAS_PYGETWINDOW", False)
    assert jogador.available() is False


def test_iniciar_sem_politica_treinada_levanta_erro(fake_entrada, fake_gw, monkeypatch):
    import visao.screen as screen_module
    monkeypatch.setattr(screen_module, "available", lambda: True)
    with pytest.raises(RuntimeError):
        jogador.iniciar_jogo_sozinho("jogo sem treino")


def test_iniciar_duas_vezes_levanta_erro(fake_entrada, fake_gw, monkeypatch):
    import visao.screen as screen_module
    monkeypatch.setattr(screen_module, "available", lambda: True)
    monkeypatch.setattr(screen_module, "screenshot", lambda **k: _frame_falso())
    _treinar_politica_falsa("jogo teste")

    jogador.iniciar_jogo_sozinho("jogo teste", duracao_minutos=0.5)
    with pytest.raises(RuntimeError):
        jogador.iniciar_jogo_sozinho("jogo teste", duracao_minutos=0.5)


# ---------- previsão de ação ----------

def test_prever_acao_devolve_vetor_no_formato_certo():
    modelo = PoliticaJogo()
    pilha = np.random.randint(0, 255, (N_FRAMES_EMPILHADOS, TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
    vetor = jogador._prever_acao(modelo, pilha)
    assert vetor.shape == (len(NOMES_TECLAS) + 4,)


# ---------- aplicar ação: diff de teclas seguradas ----------

def test_aplicar_acao_segura_teclas_novas_e_solta_as_que_sairam(fake_entrada):
    jogador._estado["_teclas_pressionadas"] = {"w"}
    jogador._aplicar_acao({"teclas": ["a", "w"], "dx": 0, "dy": 0, "clique_esquerdo": False, "clique_direito": False})
    assert ("segurar", "a") in fake_entrada.chamadas
    assert ("soltar", "w") not in fake_entrada.chamadas  # w continua sendo pedida, não solta à toa
    assert jogador._estado["_teclas_pressionadas"] == {"a", "w"}


def test_aplicar_acao_solta_tecla_que_nao_esta_mais_no_alvo(fake_entrada):
    jogador._estado["_teclas_pressionadas"] = {"w", "shift"}
    jogador._aplicar_acao({"teclas": ["w"], "dx": 0, "dy": 0, "clique_esquerdo": False, "clique_direito": False})
    assert ("soltar", "shift") in fake_entrada.chamadas
    assert jogador._estado["_teclas_pressionadas"] == {"w"}


def test_aplicar_acao_move_mouse_e_clica(fake_entrada):
    jogador._estado["_teclas_pressionadas"] = set()
    jogador._aplicar_acao({"teclas": [], "dx": 15, "dy": -5, "clique_esquerdo": True, "clique_direito": False})
    assert ("mover", 15, -5) in fake_entrada.chamadas
    assert ("clicar", "left") in fake_entrada.chamadas


def test_soltar_todas_teclas_solta_tudo_que_estava_segurado(fake_entrada):
    jogador._estado["_teclas_pressionadas"] = {"w", "a", "space"}
    jogador._soltar_todas_teclas()
    soltas = {c[1] for c in fake_entrada.chamadas if c[0] == "soltar"}
    assert soltas == {"w", "a", "space"}
    assert jogador._estado["_teclas_pressionadas"] == set()


# ---------- foco da janela ----------

def test_janela_em_foco_bate_por_substring(fake_gw):
    fake_gw.titulo_ativo = "F1 24 - DirectX 12"
    assert jogador._janela_em_foco("f1 24") is True
    assert jogador._janela_em_foco("roblox") is False


def test_janela_em_foco_sem_janela_ativa_retorna_falso(fake_gw):
    fake_gw.titulo_ativo = None
    assert jogador._janela_em_foco("qualquer coisa") is False


# ---------- feedback ----------

def test_registrar_feedback_sem_sessao_retorna_falso():
    jogador._estado["episodio_ids"] = []
    assert jogador.registrar_feedback(True) is False


def test_registrar_feedback_marca_so_o_episodio_mais_recente():
    jogador._estado["episodio_ids"] = [0, 0, 1, 1, 1]
    jogador._estado["feedback"] = [0.0] * 5
    assert jogador.registrar_feedback(False) is True
    assert jogador._estado["feedback"] == [0.0, 0.0, -1.0, -1.0, -1.0]


# ---------- sessão completa: grava e salva ao parar ----------

def test_sessao_completa_grava_e_solta_teclas_ao_parar(fake_entrada, fake_gw, monkeypatch):
    import visao.screen as screen_module
    monkeypatch.setattr(screen_module, "available", lambda: True)
    monkeypatch.setattr(screen_module, "screenshot", lambda **k: _frame_falso())
    from config.settings import get_settings
    get_settings().set("jogos.taxa_quadros_por_segundo", 50)

    _treinar_politica_falsa("jogo teste")
    jogador.iniciar_jogo_sozinho("jogo teste", duracao_minutos=0.5, titulo_janela="meu jogo")
    fake_gw.titulo_ativo = "Meu Jogo - Janela"
    time.sleep(0.15)
    resultado = jogador.parar_jogo()

    assert resultado["parou"] is True
    assert resultado["n_quadros"] > 0
    assert os.path.isfile(resultado["caminho"])
    # nenhuma tecla deve continuar "presa" depois de parar
    assert jogador._estado["_teclas_pressionadas"] == set()

    dados = np.load(resultado["caminho"])
    assert dados["frames"].shape[0] == resultado["n_quadros"]
    assert dados["episodio_ids"].shape[0] == resultado["n_quadros"]
    assert dados["feedback"].shape[0] == resultado["n_quadros"]
    assert dados["sinais_movimento"].shape[0] == resultado["n_quadros"]


def test_salto_grande_de_cena_fecha_episodio_e_conta_como_sinal_alto(fake_entrada, fake_gw, monkeypatch):
    """Um salto BRUSCO na cena deve: (1) fechar o episódio atual e
    abrir um novo (jogos.limiar_deteccao_reset), e (2) o próprio salto
    ainda é gravado como um sinal_movimento alto naquele quadro --
    confirma que jogador.py e captura.py concordam sobre a MESMA
    métrica (diferenca_de_frames) depois do refactor que uniu as duas
    (detecção de reset e sinal de movimento eram cálculos separados
    antes)."""
    import visao.screen as screen_module
    monkeypatch.setattr(screen_module, "available", lambda: True)

    cores = iter([50, 50, 50, 250, 250])  # salto grande na 4a chamada

    def _proximo_frame(**k):
        cor = next(cores, 250)
        return _frame_falso(cor=cor)

    monkeypatch.setattr(screen_module, "screenshot", _proximo_frame)
    from config.settings import get_settings
    get_settings().set("jogos.taxa_quadros_por_segundo", 50)
    get_settings().set("jogos.limiar_deteccao_reset", 40.0)

    _treinar_politica_falsa("jogo teste")
    jogador.iniciar_jogo_sozinho("jogo teste", duracao_minutos=0.5, titulo_janela="meu jogo")
    fake_gw.titulo_ativo = "Meu Jogo - Janela"
    time.sleep(0.15)
    resultado = jogador.parar_jogo()

    dados = np.load(resultado["caminho"])
    assert dados["episodio_ids"].max() >= 1  # pelo menos um reset detectado
    # o quadro exatamente onde o episódio mudou tem que ter um sinal de movimento alto
    idx_mudanca = np.argmax(dados["episodio_ids"] > 0)
    assert dados["sinais_movimento"][idx_mudanca] > 40.0


def test_pausa_e_solta_teclas_quando_janela_perde_foco(fake_entrada, fake_gw, monkeypatch):
    import visao.screen as screen_module
    monkeypatch.setattr(screen_module, "available", lambda: True)
    monkeypatch.setattr(screen_module, "screenshot", lambda **k: _frame_falso())
    from config.settings import get_settings
    get_settings().set("jogos.taxa_quadros_por_segundo", 50)

    fake_gw.titulo_ativo = "Outro Programa Qualquer"  # já fora de foco ANTES de iniciar -- sem essa corrida, o
    # primeiro tick (que pode rodar antes do teste conseguir reatribuir titulo_ativo depois de iniciar) já
    # nasce sem foco, então nunca captura nada de verdade.
    _treinar_politica_falsa("jogo teste")
    jogador.iniciar_jogo_sozinho("jogo teste", duracao_minutos=0.5, titulo_janela="meu jogo")
    time.sleep(0.15)

    assert jogador.pausado_por_foco() is True
    resultado = jogador.parar_jogo()
    assert resultado["n_quadros"] == 0  # nunca capturou nada -- sempre esteve fora de foco
