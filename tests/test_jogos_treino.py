"""
tests/test_jogos_treino.py
=============================
Treino por imitação (jogos/treino.py:treinar_por_imitacao) e o
"melhora sozinho" (retreinar_com_sessoes, behavior cloning ponderado
por duração de episódio + feedback do usuário). Dataset sintético
pequeno (poucas dezenas de quadros) -- não testa CONVERGÊNCIA (isso
levaria minutos e não é o que importa aqui), só que o pipeline roda
sem erro e que a PONDERAÇÃO funciona como projetado.
"""

import os

import numpy as np
import pytest

import jogos.treino as treino
from jogos import armazenamento
from jogos.captura import TAMANHO_ACAO, TAMANHO_FRAME


@pytest.fixture(autouse=True)
def _dados_isolados(tmp_path, monkeypatch):
    monkeypatch.setattr(armazenamento, "DADOS_DIR", str(tmp_path))
    yield


def _salvar_demonstracao_falsa(nome_jogo: str, n_quadros: int = 20):
    pasta = armazenamento.pasta_demonstracoes(nome_jogo)
    os.makedirs(pasta, exist_ok=True)
    frames = np.random.randint(0, 255, (n_quadros, TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
    acoes = np.random.randint(0, 2, (n_quadros, TAMANHO_ACAO)).astype(np.float32)
    caminho = os.path.join(pasta, "1.npz")
    np.savez_compressed(caminho, frames=frames, acoes=acoes)
    return caminho


def _salvar_sessao_falsa(nome_jogo: str, episodio_ids, feedback=None, nome_arquivo="1.npz"):
    pasta = armazenamento.pasta_sessoes(nome_jogo)
    os.makedirs(pasta, exist_ok=True)
    n = len(episodio_ids)
    frames = np.random.randint(0, 255, (n, TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
    acoes = np.random.rand(n, TAMANHO_ACAO).astype(np.float32)
    feedback = np.zeros(n, dtype=np.float32) if feedback is None else np.array(feedback, dtype=np.float32)
    caminho = os.path.join(pasta, nome_arquivo)
    np.savez_compressed(
        caminho, frames=frames, acoes=acoes,
        episodio_ids=np.array(episodio_ids, dtype=np.int32), feedback=feedback,
    )
    return caminho


# ---------- treinar_por_imitacao ----------

def test_treinar_sem_demonstracao_levanta_erro():
    with pytest.raises(RuntimeError):
        treino.treinar_por_imitacao("jogo sem nada")


def test_treinar_por_imitacao_salva_politica():
    _salvar_demonstracao_falsa("jogo teste", n_quadros=30)

    resultado = treino.treinar_por_imitacao("jogo teste", epocas=2)

    assert resultado["n_amostras"] == 30
    assert resultado["epocas"] == 2
    assert armazenamento.tem_politica_treinada("jogo teste")


def test_treinar_por_imitacao_junta_varias_demonstracoes():
    pasta = armazenamento.pasta_demonstracoes("jogo teste")
    os.makedirs(pasta, exist_ok=True)
    for i in range(3):
        frames = np.random.randint(0, 255, (10, TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
        acoes = np.random.randint(0, 2, (10, TAMANHO_ACAO)).astype(np.float32)
        np.savez_compressed(os.path.join(pasta, f"{i}.npz"), frames=frames, acoes=acoes)

    resultado = treino.treinar_por_imitacao("jogo teste", epocas=1)

    assert resultado["n_amostras"] == 30  # 3 arquivos x 10 quadros cada


# ---------- retreinar_com_sessoes ----------

def test_retreinar_sem_politica_treinada_levanta_erro():
    with pytest.raises(RuntimeError):
        treino.retreinar_com_sessoes("jogo sem politica")


def test_retreinar_sem_sessoes_levanta_erro():
    _salvar_demonstracao_falsa("jogo teste")
    treino.treinar_por_imitacao("jogo teste", epocas=1)

    with pytest.raises(RuntimeError):
        treino.retreinar_com_sessoes("jogo teste")


def test_retreinar_com_sessoes_roda_e_atualiza_a_politica():
    _salvar_demonstracao_falsa("jogo teste", n_quadros=20)
    treino.treinar_por_imitacao("jogo teste", epocas=1)
    _salvar_sessao_falsa("jogo teste", episodio_ids=[0] * 10 + [1] * 10)

    resultado = treino.retreinar_com_sessoes("jogo teste", epocas=1)

    assert resultado["n_amostras"] == 40  # 20 da demonstração + 20 da sessão (sem feedback negativo, nada excluído)


# ---------- ponderação por duração de episódio ----------

def test_peso_por_duracao_da_mais_peso_a_episodio_mais_longo():
    episodio_ids = np.array([0] * 5 + [1] * 20)  # episódio 1 é 4x mais longo
    pesos = treino._peso_por_duracao_episodio(episodio_ids)
    peso_ep0 = pesos[episodio_ids == 0][0]
    peso_ep1 = pesos[episodio_ids == 1][0]
    assert peso_ep1 > peso_ep0


def test_peso_por_duracao_respeita_limites():
    episodio_ids = np.array([0] * 1 + [1] * 1000)  # razão extrema
    pesos = treino._peso_por_duracao_episodio(episodio_ids)
    assert pesos.min() >= 0.2
    assert pesos.max() <= 3.0


# ---------- feedback no carregamento de sessões ----------

def test_feedback_negativo_exclui_amostras_do_treino():
    pasta = armazenamento.pasta_sessoes("jogo teste")
    os.makedirs(pasta, exist_ok=True)
    n = 10
    feedback_negativo = np.full(n, -1.0, dtype=np.float32)
    _salvar_sessao_falsa("jogo teste", episodio_ids=[0] * n, feedback=feedback_negativo)

    _, _, pesos = treino._carregar_sessoes("jogo teste")
    assert pesos == []  # sessão inteira com feedback negativo -- nenhuma amostra sobra


def test_feedback_positivo_multiplica_o_peso():
    pasta = armazenamento.pasta_sessoes("jogo teste")
    os.makedirs(pasta, exist_ok=True)
    n = 10
    feedback_positivo = np.full(n, 1.0, dtype=np.float32)
    _salvar_sessao_falsa("jogo teste", episodio_ids=[0] * n, feedback=feedback_positivo, nome_arquivo="pos.npz")

    _, _, pesos = treino._carregar_sessoes("jogo teste")
    assert len(pesos) == 1
    # peso base (duração, só 1 episódio -> 1.0) x 2.0 do feedback positivo
    assert np.allclose(pesos[0], 2.0)


def test_sessao_sem_feedback_usa_so_peso_por_duracao():
    _salvar_sessao_falsa("jogo teste", episodio_ids=[0] * 10)  # feedback default = tudo zero

    _, _, pesos = treino._carregar_sessoes("jogo teste")
    assert len(pesos) == 1
    assert np.allclose(pesos[0], 1.0)  # só 1 episódio -> peso neutro


# ---------- sinal de movimento ("aprende que se eu fizer isso eu vou mais rápido") ----------

def test_peso_por_sinal_movimento_da_mais_peso_a_quadro_mais_rapido():
    sinais = np.array([10.0, 10.0, 10.0, 10.0], dtype=np.float32)  # média 10
    sinais[0] = 30.0  # 3x a média nesse quadro específico
    pesos = treino._peso_por_sinal_movimento(sinais)
    assert pesos[0] > pesos[1]


def test_peso_por_sinal_movimento_respeita_limites():
    sinais = np.array([0.01, 1000.0], dtype=np.float32)  # razão extrema
    pesos = treino._peso_por_sinal_movimento(sinais)
    assert pesos.min() >= 0.5
    assert pesos.max() <= 2.5


def test_peso_por_sinal_movimento_sem_movimento_e_neutro():
    """Média zero (nada mudou em nenhum quadro, ou arquivo sem esse
    sinal) não pode tentar dividir por zero -- peso neutro (1.0) pra
    todo mundo."""
    sinais = np.zeros(5, dtype=np.float32)
    pesos = treino._peso_por_sinal_movimento(sinais)
    assert np.allclose(pesos, 1.0)


def test_peso_por_sinal_movimento_vazio_nao_quebra():
    assert len(treino._peso_por_sinal_movimento(np.array([], dtype=np.float32))) == 0


def _salvar_demonstracao_com_sinal(nome_jogo: str, sinais_movimento, nome_arquivo="1.npz"):
    pasta = armazenamento.pasta_demonstracoes(nome_jogo)
    os.makedirs(pasta, exist_ok=True)
    n = len(sinais_movimento)
    frames = np.random.randint(0, 255, (n, TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
    acoes = np.random.randint(0, 2, (n, TAMANHO_ACAO)).astype(np.float32)
    caminho = os.path.join(pasta, nome_arquivo)
    np.savez_compressed(
        caminho, frames=frames, acoes=acoes,
        sinais_movimento=np.array(sinais_movimento, dtype=np.float32),
    )
    return caminho


def test_carregar_demonstracoes_usa_sinal_de_movimento_quando_presente():
    sinais = [10.0] * 9 + [30.0]  # último quadro bem mais "rápido" que o resto
    _salvar_demonstracao_com_sinal("jogo teste", sinais)

    _, _, pesos = treino._carregar_demonstracoes("jogo teste")
    assert pesos[0][-1] > pesos[0][0]  # o quadro "mais rápido" pesa mais no treino


def test_carregar_demonstracoes_sem_sinal_usa_peso_neutro():
    """Arquivo gravado ANTES deste sinal existir (sem a chave
    "sinais_movimento") não pode quebrar -- cai no peso neutro de
    sempre (1.0), mesmo comportamento de antes desta funcionalidade."""
    _salvar_demonstracao_falsa("jogo teste", n_quadros=10)

    _, _, pesos = treino._carregar_demonstracoes("jogo teste")
    assert np.allclose(pesos[0], 1.0)


def test_carregar_sessoes_combina_duracao_e_sinal_de_movimento():
    pasta = armazenamento.pasta_sessoes("jogo teste")
    os.makedirs(pasta, exist_ok=True)
    n = 10
    frames = np.random.randint(0, 255, (n, TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
    acoes = np.random.rand(n, TAMANHO_ACAO).astype(np.float32)
    sinais = np.array([10.0] * 9 + [50.0], dtype=np.float32)  # último quadro bem mais rápido
    np.savez_compressed(
        os.path.join(pasta, "1.npz"), frames=frames, acoes=acoes,
        episodio_ids=np.zeros(n, dtype=np.int32), feedback=np.zeros(n, dtype=np.float32),
        sinais_movimento=sinais,
    )

    _, _, pesos = treino._carregar_sessoes("jogo teste")
    assert pesos[0][-1] > pesos[0][0]
