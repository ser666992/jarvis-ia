"""
tests/test_jogos_modelo.py
=============================
PoliticaJogo (jogos/modelo.py): forward com o formato certo, salvar/
carregar preserva os pesos. Roda de verdade (torch está instalado
neste ambiente, ver requirements-ia.txt) -- rede pequena o bastante
pra isso ser rápido.
"""

import os

import numpy as np
import pytest
import torch

from jogos.captura import N_FRAMES_EMPILHADOS, NOMES_TECLAS, TAMANHO_FRAME
from jogos.modelo import PoliticaJogo, carregar, salvar

N_TECLAS = len(NOMES_TECLAS)


def _entrada_fake(tamanho_lote=2):
    return torch.randint(0, 255, (tamanho_lote, N_FRAMES_EMPILHADOS, TAMANHO_FRAME, TAMANHO_FRAME), dtype=torch.uint8)


def test_forward_devolve_as_tres_cabecas_com_shape_certo():
    modelo = PoliticaJogo()
    saida = modelo(_entrada_fake(tamanho_lote=3))

    assert saida["teclas"].shape == (3, N_TECLAS)
    assert saida["mouse"].shape == (3, 2)
    assert saida["cliques"].shape == (3, 2)


def test_mouse_fica_limitado_a_menos1_1_por_causa_do_tanh():
    modelo = PoliticaJogo()
    saida = modelo(_entrada_fake())
    mouse = saida["mouse"].detach().numpy()
    assert np.all(mouse >= -1.0) and np.all(mouse <= 1.0)


def test_salvar_e_carregar_preserva_os_pesos(tmp_path):
    modelo = PoliticaJogo()
    caminho = os.path.join(tmp_path, "sub", "politica.pt")
    salvar(modelo, caminho)
    assert os.path.isfile(caminho)

    recarregado = carregar(caminho)
    x = _entrada_fake()
    with torch.no_grad():
        original = modelo(x)
        depois = recarregado(x)
    for chave in ("teclas", "mouse", "cliques"):
        assert torch.allclose(original[chave], depois[chave])


def test_modelo_recarregado_fica_em_modo_eval():
    modelo = PoliticaJogo()
    assert modelo.training is True  # padrão do nn.Module ao criar

    import tempfile
    caminho = os.path.join(tempfile.mkdtemp(), "politica.pt")
    salvar(modelo, caminho)
    recarregado = carregar(caminho)
    assert recarregado.training is False  # carregar() já chama .eval()


def test_instanciar_sem_torch_levanta_erro_amigavel(monkeypatch):
    import jogos.modelo as modelo_module
    monkeypatch.setattr(modelo_module, "HAS_TORCH", False)
    with pytest.raises(RuntimeError):
        modelo_module.PoliticaJogo()
