"""
tests/test_jogos_captura.py
==============================
Espaço de ação/observação compartilhado por jogos/gravador.py e
jogos/jogador.py (jogos/captura.py) -- codificação/decodificação do
vetor de ação (teclas + mouse + cliques) e downsample/empilhamento de
frame. Cobrir isso bem aqui importa mais que o normal: se gravação e
auto-jogo divergissem no formato, uma política treinada numa gravação
ficaria incompatível com o loop que tenta usá-la depois, silenciosamente.
"""

import numpy as np

from jogos.captura import (
    N_FRAMES_EMPILHADOS,
    NOMES_TECLAS,
    TAMANHO_ACAO,
    TAMANHO_FRAME,
    EmpilhadorFrames,
    diferenca_de_frames,
    estado_para_vetor,
    normalizar_tecla_pynput,
    nova_acao_vazia,
    preprocessar_frame,
    vetor_para_acao,
)


def test_nova_acao_vazia_tem_o_tamanho_certo():
    vetor = nova_acao_vazia()
    assert vetor.shape == (TAMANHO_ACAO,)
    assert vetor.sum() == 0.0


def test_estado_para_vetor_marca_teclas_seguradas():
    vetor = estado_para_vetor({"w", "shift"})
    for tecla in ("w", "shift"):
        assert vetor[NOMES_TECLAS.index(tecla)] == 1.0
    for tecla in NOMES_TECLAS:
        if tecla not in ("w", "shift"):
            assert vetor[NOMES_TECLAS.index(tecla)] == 0.0


def test_estado_para_vetor_normaliza_mouse_e_clips():
    vetor = estado_para_vetor(set(), dx=1000, dy=-1000)  # bem acima do limite -- deve saturar em -1..1
    acao = vetor_para_acao(vetor)
    assert acao["dx"] > 0  # positivo preservado
    assert acao["dy"] < 0  # negativo preservado
    # decodificado de volta pra pixels, nunca deve passar do limite configurado (jogos.captura._DX_DY_MAX_PIXELS)
    from jogos.captura import _DX_DY_MAX_PIXELS
    assert abs(acao["dx"]) <= _DX_DY_MAX_PIXELS + 1e-3
    assert abs(acao["dy"]) <= _DX_DY_MAX_PIXELS + 1e-3


def test_estado_para_vetor_ida_e_volta_preserva_cliques():
    vetor = estado_para_vetor(set(), clique_esquerdo=True, clique_direito=False)
    acao = vetor_para_acao(vetor)
    assert acao["clique_esquerdo"] is True
    assert acao["clique_direito"] is False


def test_vetor_para_acao_so_lista_teclas_acima_do_limiar():
    vetor = nova_acao_vazia()
    vetor[NOMES_TECLAS.index("w")] = 0.9
    vetor[NOMES_TECLAS.index("a")] = 0.2  # abaixo do limiar padrão (0.5)
    acao = vetor_para_acao(vetor)
    assert acao["teclas"] == ["w"]


def test_normalizar_tecla_pynput_teclas_de_caractere():
    class _FakeKeyCode:
        def __init__(self, char):
            self.char = char
            self.name = None

    assert normalizar_tecla_pynput(_FakeKeyCode("w")) == "w"
    assert normalizar_tecla_pynput(_FakeKeyCode("W")) == "w"  # case-insensitive
    assert normalizar_tecla_pynput(_FakeKeyCode("z")) is None  # fora do vocabulário -- ignorada de propósito


def test_normalizar_tecla_pynput_teclas_especiais():
    class _FakeKey:
        def __init__(self, name):
            self.name = name
            self.char = None

    assert normalizar_tecla_pynput(_FakeKey("space")) == "space"
    assert normalizar_tecla_pynput(_FakeKey("shift_l")) == "shift"
    assert normalizar_tecla_pynput(_FakeKey("shift_r")) == "shift"
    assert normalizar_tecla_pynput(_FakeKey("ctrl_l")) == "ctrl"
    assert normalizar_tecla_pynput(_FakeKey("up")) == "up"
    assert normalizar_tecla_pynput(_FakeKey("f5")) is None  # fora do vocabulário


def test_preprocessar_frame_reduz_pro_tamanho_esperado():
    frame_bgr = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    processado = preprocessar_frame(frame_bgr)
    assert processado.shape == (TAMANHO_FRAME, TAMANHO_FRAME)
    assert processado.dtype == np.uint8


def test_preprocessar_frame_aceita_cinza_e_bgra():
    cinza = np.random.randint(0, 255, (120, 160), dtype=np.uint8)
    bgra = np.random.randint(0, 255, (120, 160, 4), dtype=np.uint8)
    assert preprocessar_frame(cinza).shape == (TAMANHO_FRAME, TAMANHO_FRAME)
    assert preprocessar_frame(bgra).shape == (TAMANHO_FRAME, TAMANHO_FRAME)


def test_preprocessar_frame_rejeita_quantidade_de_canais_invalida():
    frame = np.zeros((20, 20, 2), dtype=np.uint8)
    import pytest
    with pytest.raises(ValueError, match="Frame inválido"):
        preprocessar_frame(frame)


def test_empilhador_primeiro_frame_repete_pra_preencher_pilha():
    # EmpilhadorFrames.adicionar() espera um frame JÁ pré-processado
    # (ver preprocessar_frame) -- quem chama (jogos/jogador.py)
    # pré-processa uma vez só e reaproveita pra outras coisas no mesmo
    # tick (detecção de reset, gravar a sessão). Passar um frame cru
    # de novo pra dentro quebraria (cv2 não aceita escala de cinza
    # como se fosse BGR) -- bug real encontrado testando isto.
    empilhador = EmpilhadorFrames()
    frame = np.random.randint(0, 255, (TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
    pilha = empilhador.adicionar(frame)
    assert pilha.shape == (N_FRAMES_EMPILHADOS, TAMANHO_FRAME, TAMANHO_FRAME)
    # sem histórico ainda -- todas as N_FRAMES_EMPILHADOS "camadas" são o mesmo frame
    for i in range(1, N_FRAMES_EMPILHADOS):
        assert np.array_equal(pilha[0], pilha[i])


def test_empilhador_desliza_a_janela_com_novos_frames():
    empilhador = EmpilhadorFrames()
    frame1 = np.full((TAMANHO_FRAME, TAMANHO_FRAME), 10, dtype=np.uint8)
    frame2 = np.full((TAMANHO_FRAME, TAMANHO_FRAME), 200, dtype=np.uint8)
    empilhador.adicionar(frame1)
    pilha = empilhador.adicionar(frame2)
    # o quadro mais recente (último da pilha) tem que ser o frame2
    assert pilha[-1].mean() > pilha[0].mean()


def test_empilhador_resetar_limpa_o_historico():
    empilhador = EmpilhadorFrames()
    frame = np.random.randint(0, 255, (TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
    empilhador.adicionar(frame)
    empilhador.resetar()
    assert empilhador._pilha is None


# ---------- diferenca_de_frames (sinal de movimento/reset) ----------

def test_diferenca_de_frames_sem_anterior_e_zero():
    frame = np.full((TAMANHO_FRAME, TAMANHO_FRAME), 100, dtype=np.uint8)
    assert diferenca_de_frames(frame, None) == 0.0


def test_diferenca_de_frames_identico_e_zero():
    frame = np.full((TAMANHO_FRAME, TAMANHO_FRAME), 100, dtype=np.uint8)
    assert diferenca_de_frames(frame, frame.copy()) == 0.0


def test_diferenca_de_frames_cresce_com_a_mudanca():
    base = np.full((TAMANHO_FRAME, TAMANHO_FRAME), 100, dtype=np.uint8)
    pouca_mudanca = np.full((TAMANHO_FRAME, TAMANHO_FRAME), 110, dtype=np.uint8)
    muita_mudanca = np.full((TAMANHO_FRAME, TAMANHO_FRAME), 250, dtype=np.uint8)

    assert diferenca_de_frames(pouca_mudanca, base) < diferenca_de_frames(muita_mudanca, base)
