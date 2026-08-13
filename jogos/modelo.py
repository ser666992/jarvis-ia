"""
jogos/modelo.py
==================
PoliticaJogo: rede pequena (CNN) que aprende a mapear observação (pilha
de frames, ver jogos/captura.py) pra ação (quais teclas segurar +
movimento do mouse + cliques). Tamanho pensado pra treinar em CPU em
minutos, não horas -- mesma arquitetura geral (3 conv + FC) usada
pelos primeiros agentes de Atari, com menos canais por camada (16/32/32
em vez de 32/64/64) porque aqui não há GPU disponível
(sistema.hardware.detect_gpu()) e o dataset de treino é uma gravação
de alguns minutos, não milhões de frames.

Três "cabeças" de saída sobre a mesma representação (multi-tarefa,
tudo aprendido junto):
  - teclas: um logit por tecla do vocabulário (jogos.captura.NOMES_TECLAS)
    -- multi-label (mais de uma pode estar "ativa" ao mesmo tempo,
    ex.: W+Shift pra correr), por isso sigmoid/BCE, não softmax.
  - mouse: dx/dy previstos (tanh, mesma escala -1..1 normalizada em
    jogos.captura.estado_para_vetor).
  - cliques: dois logits (esquerdo/direito), mesmo esquema das teclas.

`PoliticaJogo` não precisa de `torch` instalado pra ser IMPORTADA (só
pra ser INSTANCIADA/usada) -- mesmo espírito de degradação graciosa do
resto do projeto: `jogos.available()` já teria avisado antes de
qualquer código tentar de fato criar uma instância.
"""

import os

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    nn = None

from jogos.captura import N_FRAMES_EMPILHADOS, NOMES_TECLAS, TAMANHO_FRAME

_N_TECLAS = len(NOMES_TECLAS)
_BaseModulo = nn.Module if HAS_TORCH else object


class PoliticaJogo(_BaseModulo):
    def __init__(self):
        if not HAS_TORCH:
            raise RuntimeError("Instale 'torch' (requirements-ia.txt) para treinar/rodar uma política de jogo.")
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(N_FRAMES_EMPILHADOS, 16, kernel_size=8, stride=4),
            nn.ReLU(inplace=True),
            nn.Conv2d(16, 32, kernel_size=4, stride=2),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 32, kernel_size=3, stride=1),
            nn.ReLU(inplace=True),
        )
        tam_achatado = self._tamanho_achatado()
        self.tronco = nn.Sequential(nn.Linear(tam_achatado, 256), nn.ReLU(inplace=True))
        self.cabeca_teclas = nn.Linear(256, _N_TECLAS)
        self.cabeca_mouse = nn.Linear(256, 2)
        self.cabeca_cliques = nn.Linear(256, 2)

    def _tamanho_achatado(self) -> int:
        with torch.no_grad():
            fake = torch.zeros(1, N_FRAMES_EMPILHADOS, TAMANHO_FRAME, TAMANHO_FRAME)
            return self.conv(fake).numel()

    def forward(self, x):
        """x: (lote, N_FRAMES_EMPILHADOS, TAMANHO_FRAME, TAMANHO_FRAME),
        valores 0..255 -- normalizado aqui dentro pra 0..1, quem chama
        não precisa normalizar antes. Retorna um dict com os logits/
        valores de cada cabeça (ver docstring do módulo)."""
        x = x.float() / 255.0
        caracteristicas = self.conv(x).flatten(1)
        tronco = self.tronco(caracteristicas)
        return {
            "teclas": self.cabeca_teclas(tronco),
            "mouse": torch.tanh(self.cabeca_mouse(tronco)),
            "cliques": self.cabeca_cliques(tronco),
        }


def salvar(modelo: PoliticaJogo, caminho: str):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    torch.save(modelo.state_dict(), caminho)


def carregar(caminho: str) -> PoliticaJogo:
    modelo = PoliticaJogo()
    modelo.load_state_dict(torch.load(caminho, map_location="cpu"))
    modelo.eval()
    return modelo
