"""
jogos/captura.py
===================
Peça compartilhada entre `gravador.py` (grava a ação REAL do usuário
jogando) e `jogador.py` (decodifica a ação PREVISTA pelo modelo) --
fica num só lugar pra gravação e auto-jogo NUNCA divergirem no formato
de observação/ação (se divergissem, uma política treinada numa
gravação ficaria incompatível com o loop que tenta usá-la depois).

Observação: frame de tela reduzido (padrão usado por agentes tipo
Atari/DQN, muito mais barato que trabalhar no tamanho real da tela) --
84x84 em escala de cinza, empilhando os últimos N_FRAMES_EMPILHADOS
quadros (dá noção de MOVIMENTO pro modelo, um frame parado sozinho não
diz se algo está indo pra esquerda ou pra direita).

Ação: vocabulário FIXO de teclas comuns em jogos de PC (não é
específico de nenhum jogo -- mesma abstração de "controle virtual" que
pesquisa de agentes generalistas usa) + movimento relativo do mouse +
os dois botões. `NOMES_TECLAS` usa os mesmos nomes que
`controle_pc.entrada`/`pyautogui` esperam em `keyDown`/`keyUp`, pra
`jogador.py` poder usar o nome direto sem tradução.
"""

import numpy as np

TAMANHO_FRAME = 84
N_FRAMES_EMPILHADOS = 4

NOMES_TECLAS = [
    "w", "a", "s", "d", "space", "shift", "ctrl", "e", "f", "q", "r",
    "enter", "esc", "up", "down", "left", "right",
]
_N_TECLAS = len(NOMES_TECLAS)
# vetor de ação: [uma posição por tecla (0/1)] + [dx, dy do mouse] + [clique esquerdo, clique direito]
TAMANHO_ACAO = _N_TECLAS + 2 + 2
_IDX_DX = _N_TECLAS
_IDX_DY = _N_TECLAS + 1
_IDX_CLIQUE_ESQ = _N_TECLAS + 2
_IDX_CLIQUE_DIR = _N_TECLAS + 3

# Limite de deslocamento do mouse por tick, em pixels -- normaliza dx/dy
# pra escala -1..1 antes de guardar/treinar (evita que o tamanho da tela
# de quem gravou vaze pra escala numérica do modelo).
_DX_DY_MAX_PIXELS = 200.0


def nova_acao_vazia() -> np.ndarray:
    return np.zeros(TAMANHO_ACAO, dtype=np.float32)


# pynput.keyboard.Key (teclas especiais) -> nome canônico usado aqui.
_PYNPUT_ESPECIAIS = {
    "space": "space",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "enter": "enter",
    "esc": "esc",
    "up": "up", "down": "down", "left": "left", "right": "right",
}


def normalizar_tecla_pynput(key) -> str:
    """Converte uma tecla do pynput (Key especial ou KeyCode de
    caractere) pro nome canônico em NOMES_TECLAS -- None se a tecla não
    faz parte do vocabulário (ex.: F5, Tab -- ignoradas de propósito,
    não fazem parte do "controle virtual" genérico definido aqui)."""
    nome_especial = getattr(key, "name", None)
    if nome_especial is not None:
        return _PYNPUT_ESPECIAIS.get(nome_especial)
    char = getattr(key, "char", None)
    if char and char.lower() in NOMES_TECLAS:
        return char.lower()
    return None


def estado_para_vetor(teclas_seguradas, dx: float = 0.0, dy: float = 0.0,
                       clique_esquerdo: bool = False, clique_direito: bool = False) -> np.ndarray:
    """`teclas_seguradas`: iterável de nomes canônicos (subconjunto de
    NOMES_TECLAS) atualmente pressionados. dx/dy: deslocamento do mouse
    desde o último quadro, em pixels (normalizado aqui pra -1..1)."""
    vetor = nova_acao_vazia()
    for tecla in teclas_seguradas:
        if tecla in NOMES_TECLAS:
            vetor[NOMES_TECLAS.index(tecla)] = 1.0
    vetor[_IDX_DX] = max(-1.0, min(1.0, dx / _DX_DY_MAX_PIXELS))
    vetor[_IDX_DY] = max(-1.0, min(1.0, dy / _DX_DY_MAX_PIXELS))
    vetor[_IDX_CLIQUE_ESQ] = 1.0 if clique_esquerdo else 0.0
    vetor[_IDX_CLIQUE_DIR] = 1.0 if clique_direito else 0.0
    return vetor


def vetor_para_acao(vetor, limiar: float = 0.5) -> dict:
    """Decodifica um vetor de ação (saída do modelo ou de uma gravação)
    de volta pra uma forma utilizável por controle_pc.entrada:
    {"teclas": [...nomes pressionados...], "dx", "dy",
    "clique_esquerdo", "clique_direito"} -- dx/dy já desfazem a
    normalização (voltam a ser pixels)."""
    teclas = [nome for i, nome in enumerate(NOMES_TECLAS) if vetor[i] >= limiar]
    return {
        "teclas": teclas,
        "dx": float(vetor[_IDX_DX]) * _DX_DY_MAX_PIXELS,
        "dy": float(vetor[_IDX_DY]) * _DX_DY_MAX_PIXELS,
        "clique_esquerdo": bool(vetor[_IDX_CLIQUE_ESQ] >= limiar),
        "clique_direito": bool(vetor[_IDX_CLIQUE_DIR] >= limiar),
    }


def preprocessar_frame(frame_bgr) -> np.ndarray:
    """Reduz um frame de tela (numpy BGR, ex.: de visao.screen.screenshot())
    pra TAMANHO_FRAME x TAMANHO_FRAME em escala de cinza -- barato de
    processar/guardar/treinar em CPU, suficiente pra reconhecer padrão
    visual grosso (não é OCR nem detecção fina, só "o que está
    acontecendo na tela, em linhas gerais")."""
    import cv2
    frame = np.asarray(frame_bgr)
    if frame.ndim == 2:
        cinza = frame
    elif frame.ndim == 3 and frame.shape[2] == 1:
        cinza = frame[:, :, 0]
    elif frame.ndim == 3 and frame.shape[2] == 3:
        cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        cinza = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    else:
        raise ValueError(
            f"Frame inválido: esperado HxW, HxWx1, HxWx3 ou HxWx4; recebido {frame.shape}.")
    return cv2.resize(cinza, (TAMANHO_FRAME, TAMANHO_FRAME), interpolation=cv2.INTER_AREA).astype(np.uint8)


def diferenca_de_frames(frame_atual: np.ndarray, frame_anterior) -> float:
    """Diferença média de pixel entre dois frames JÁ pré-processados
    (ver preprocessar_frame) -- proxy genérico de "quanto a cena mudou"
    nesse instante. Usado de dois jeitos: jogos/jogador.py já usa isso
    pra detectar reset (uma mudança BRUSCA de cena); jogos/gravador.py
    e jogos/treino.py usam a MESMA métrica, quadro a quadro, como sinal
    de "quanto de ação/movimento estava rolando" -- é a base de
    jogos.treino.py aprender com MAIS peso os momentos em que as coisas
    estavam se movendo/mudando mais rápido que o normal (pedido
    explícito do usuário: "aprende que se eu fizer isso eu vou mais
    rápido"), em vez de imitar tudo em peso igual. Honesto: é um proxy
    de movimento na TELA, não de velocidade real dentro do jogo (câmera
    balançando muito também gera um valor alto) -- mas é genérico,
    funciona em qualquer jogo, sem precisar ler HUD nenhum.

    Retorna 0.0 se `frame_anterior` for None (primeiro quadro de uma
    gravação/sessão, sem comparação possível)."""
    if frame_anterior is None:
        return 0.0
    return float(np.mean(np.abs(frame_atual.astype(np.int16) - frame_anterior.astype(np.int16))))


class EmpilhadorFrames:
    """Mantém os últimos N_FRAMES_EMPILHADOS quadros JÁ pré-processados
    -- dá noção de MOVIMENTO ao modelo (um único frame parado não diz
    se um obstáculo está se aproximando ou se afastando). `.resetar()`
    limpa a pilha (chamado no início de uma gravação/sessão nova, ou
    quando um reset de episódio é detectado)."""

    def __init__(self):
        self._pilha = None

    def resetar(self):
        self._pilha = None

    def adicionar(self, frame_processado: np.ndarray) -> np.ndarray:
        """`frame_processado`: já reduzido por preprocessar_frame()
        (TAMANHO_FRAME x TAMANHO_FRAME, um canal) -- pré-processar é
        responsabilidade de quem chama, não deste método, porque
        jogos/jogador.py já precisa do frame reduzido pra OUTRAS
        coisas no mesmo tick (detecção de reset por diff, gravar a
        sessão) -- pré-processar aqui DE NOVO faria isso duas vezes à
        toa e, pior, quebraria de verdade (cv2.cvtColor não aceita uma
        imagem que já está em escala de cinza como se fosse BGR --
        bug real encontrado testando este módulo).

        Retorna o estado empilhado atual (N_FRAMES_EMPILHADOS,
        TAMANHO_FRAME, TAMANHO_FRAME) já incluindo este frame -- no
        primeiro frame de uma pilha nova, repete o mesmo frame
        N_FRAMES_EMPILHADOS vezes (não há histórico ainda, e um
        histórico "vazio"/zerado pareceria uma tela preta pro modelo)."""
        if self._pilha is None:
            self._pilha = np.stack([frame_processado] * N_FRAMES_EMPILHADOS, axis=0)
        else:
            self._pilha = np.concatenate([self._pilha[1:], frame_processado[np.newaxis, ...]], axis=0)
        return self._pilha
