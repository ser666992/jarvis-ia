"""
jogos/treino.py
==================
Duas formas de treinar a política de um jogo (jogos/modelo.py):

- `treinar_por_imitacao(nome_jogo)`: aprendizado supervisionado direto
  das demonstrações gravadas (jogos/gravador.py) -- "faça o que eu
  fiz". Peso base 1.0 pra cada amostra, MULTIPLICADO pelo sinal de
  movimento de cada quadro (`_peso_por_sinal_movimento` --
  jogos.captura.diferenca_de_frames, quanto a cena mudou desde o
  quadro anterior): momentos em que as coisas estavam andando/mudando
  mais rápido que a média da gravação pesam mais no treino. É como o
  modelo aprende, mesmo já na primeira imitação, "se eu fizer isso eu
  vou mais rápido" (pedido explícito do usuário) -- em vez de imitar
  toda a gravação com peso igual, presta mais atenção justamente nos
  momentos de mais ação/progresso.

- `retreinar_com_sessoes(nome_jogo)`: o "melhora sozinho" pedido pelo
  usuário. Mistura as demonstrações originais (sempre peso cheio) com
  sessões de auto-jogo (jogos/jogador.py) já gravadas, ponderando cada
  QUADRO por três coisas: duração do episódio a que pertence
  (sobreviveu mais tempo até o próximo reset = mais peso -- proxy
  honesto de "foi bem", não é medir o placar/vitória de verdade), o
  MESMO sinal de movimento usado acima, e feedback explícito do
  usuário ("isso foi bom"/"isso foi ruim", ver
  jogos/jogador.py:registrar_feedback) -- feedback positivo multiplica
  o peso, negativo zera (exclui do treino). Isto é "behavior cloning
  ponderado por recompensa": mais simples e muito mais barato em CPU
  que treinar por tentativa-e-erro puro (policy gradient/RL de
  verdade, que precisaria de uma quantidade de amostras inviável sem
  GPU), mas incorpora aprendizado real a partir da própria
  experiência -- não é um script fixo.

Honesto: nenhum dos dois é "o jogo entende que ganhou/perdeu", nem o
sinal de movimento é uma leitura real de velocidade/progresso dentro
do jogo -- são sempre proxies (imitação do usuário, duração+feedback,
quanto a tela mudou). Ver core/diagnostico.py e plugins/jogos.py pra
como isso é comunicado.
"""

import numpy as np

from jogos import armazenamento
from jogos.captura import N_FRAMES_EMPILHADOS, NOMES_TECLAS, TAMANHO_FRAME
from jogos.modelo import HAS_TORCH, PoliticaJogo, salvar
from logs.logger import get_logger

log = get_logger("jogos")

N_TECLAS = len(NOMES_TECLAS)
_EPOCAS_PADRAO_IMITACAO = 10
_EPOCAS_PADRAO_REFINO = 5
_TAXA_APRENDIZADO_PADRAO = 1e-3
_TAMANHO_LOTE = 64


def _empilhar_frames(frames: np.ndarray) -> np.ndarray:
    """(N, 84, 84) -> (N, N_FRAMES_EMPILHADOS, 84, 84): pra cada
    índice i, empilha os N_FRAMES_EMPILHADOS quadros mais recentes até
    ali (repetindo o primeiro quadro pra preencher o começo da sessão,
    onde ainda não há histórico suficiente) -- mesmo critério de
    jogos.captura.EmpilhadorFrames, só que reconstruído de uma vez
    sobre uma sessão já gravada, em vez de incrementalmente."""
    n = len(frames)
    pilhas = np.empty((n, N_FRAMES_EMPILHADOS, TAMANHO_FRAME, TAMANHO_FRAME), dtype=np.uint8)
    for i in range(n):
        inicio = max(0, i - N_FRAMES_EMPILHADOS + 1)
        janela = frames[inicio:i + 1]
        faltam = N_FRAMES_EMPILHADOS - len(janela)
        if faltam > 0:
            preenchimento = np.repeat(janela[0:1], faltam, axis=0)
            janela = np.concatenate([preenchimento, janela], axis=0)
        pilhas[i] = janela
    return pilhas


def _peso_por_sinal_movimento(sinais_movimento: np.ndarray) -> np.ndarray:
    """Peso proporcional a quanto a cena estava mudando NESTE quadro
    específico (jogos.captura.diferenca_de_frames), relativo à MÉDIA
    da gravação/sessão inteira -- um momento com o DOBRO de movimento
    que o normal pesa o dobro no treino. É como o modelo aprende "se
    eu fizer isso eu vou mais rápido" (pedido explícito do usuário):
    não é medir velocidade de verdade dentro do jogo, é um proxy
    genérico de quanto a cena estava mudando na tela -- câmera
    balançando muito também gera um valor alto, então isto é honesto
    sobre ser aproximado, não uma leitura de velocímetro. Limitado a
    [0.5, 2.5] pelo mesmo motivo do limite em
    _peso_por_duracao_episodio -- um pico isolado (ex.: uma explosão
    na tela) não pode dominar o treino sozinho. Sem nenhum movimento
    detectado (média zero -- ex.: arquivo gravado antes deste sinal
    existir), devolve peso neutro (1.0) pra todo mundo, sem tentar
    normalizar por zero."""
    if len(sinais_movimento) == 0:
        return np.ones(0, dtype=np.float32)
    media = float(sinais_movimento.mean())
    if media <= 1e-6:
        return np.ones(len(sinais_movimento), dtype=np.float32)
    return np.clip(sinais_movimento / media, 0.5, 2.5).astype(np.float32)


def _carregar_demonstracoes(nome_jogo: str):
    """Retorna (pilhas_de_frames, acoes, pesos) de TODAS as
    demonstrações gravadas -- peso base 1.0 (demonstração humana
    direta, sempre confiável), multiplicado pelo sinal de movimento
    de cada quadro quando disponível (ver _peso_por_sinal_movimento --
    arquivos gravados antes desse sinal existir simplesmente não têm
    a chave "sinais_movimento", e caem no peso neutro)."""
    todas_pilhas, todas_acoes, todos_pesos = [], [], []
    for caminho in armazenamento.listar_demonstracoes(nome_jogo):
        dados = np.load(caminho)
        frames, acoes = dados["frames"], dados["acoes"]
        if len(frames) == 0:
            continue
        pesos = np.ones(len(frames), dtype=np.float32)
        if "sinais_movimento" in dados.files:
            pesos = pesos * _peso_por_sinal_movimento(dados["sinais_movimento"])
        todas_pilhas.append(_empilhar_frames(frames))
        todas_acoes.append(acoes)
        todos_pesos.append(pesos)
    return todas_pilhas, todas_acoes, todos_pesos


def _peso_por_duracao_episodio(episodio_ids: np.ndarray) -> np.ndarray:
    """Peso proporcional ao tamanho do episódio (em quadros) a que
    cada amostra pertence, relativo à MÉDIA dos episódios da mesma
    sessão -- um episódio 2x mais longo que a média pesa 2x mais.
    Limitado a [0.2, 3.0] pra um episódio muito curto/longo não dominar
    o treino sozinho."""
    ids_unicos, contagens = np.unique(episodio_ids, return_counts=True)
    media = contagens.mean() if len(contagens) else 1.0
    mapa_peso = {eid: max(0.2, min(3.0, c / media)) for eid, c in zip(ids_unicos, contagens)}
    return np.array([mapa_peso[eid] for eid in episodio_ids], dtype=np.float32)


def _carregar_sessoes(nome_jogo: str):
    """Retorna (pilhas_de_frames, acoes, pesos) de todas as sessões de
    auto-jogo já gravadas (jogos/jogador.py) -- peso combinando duração
    do episódio, sinal de movimento (ver _peso_por_sinal_movimento) e
    feedback explícito do usuário (positivo multiplica, negativo zera/
    exclui a amostra)."""
    todas_pilhas, todas_acoes, todos_pesos = [], [], []
    for caminho in armazenamento.listar_sessoes(nome_jogo):
        dados = np.load(caminho)
        frames, acoes = dados["frames"], dados["acoes"]
        if len(frames) == 0:
            continue
        episodio_ids = dados["episodio_ids"]
        feedback = dados["feedback"]  # 0.0 (sem feedback) / +1.0 / -1.0 por quadro

        pesos = _peso_por_duracao_episodio(episodio_ids)
        if "sinais_movimento" in dados.files:
            pesos = pesos * _peso_por_sinal_movimento(dados["sinais_movimento"])
        pesos = np.where(feedback > 0, pesos * 2.0, pesos)
        pesos = np.where(feedback < 0, 0.0, pesos)  # feedback negativo exclui a amostra do treino
        if not np.any(pesos > 0):
            continue

        todas_pilhas.append(_empilhar_frames(frames))
        todas_acoes.append(acoes)
        todos_pesos.append(pesos)
    return todas_pilhas, todas_acoes, todos_pesos


def _treinar_com_amostras(modelo, pilhas: np.ndarray, acoes: np.ndarray, pesos: np.ndarray,
                           epocas: int, taxa_aprendizado: float) -> dict:
    import torch

    x = torch.from_numpy(pilhas)
    y = torch.from_numpy(acoes)
    w = torch.from_numpy(pesos)
    n = len(x)

    otimizador = torch.optim.Adam(modelo.parameters(), lr=taxa_aprendizado)
    perda_bce = torch.nn.BCEWithLogitsLoss(reduction="none")
    perda_mse = torch.nn.MSELoss(reduction="none")

    modelo.train()
    perda_final = 0.0
    for _ in range(max(1, epocas)):
        indices = torch.randperm(n)
        soma_perda, n_lotes = 0.0, 0
        for inicio in range(0, n, _TAMANHO_LOTE):
            lote_idx = indices[inicio:inicio + _TAMANHO_LOTE]
            saida = modelo(x[lote_idx])
            y_lote, w_lote = y[lote_idx], w[lote_idx]

            perda_teclas = perda_bce(saida["teclas"], y_lote[:, :N_TECLAS]).mean(dim=1)
            perda_mouse = perda_mse(saida["mouse"], y_lote[:, N_TECLAS:N_TECLAS + 2]).mean(dim=1)
            perda_cliques = perda_bce(saida["cliques"], y_lote[:, N_TECLAS + 2:N_TECLAS + 4]).mean(dim=1)
            perda_por_amostra = perda_teclas + perda_mouse + perda_cliques
            perda = (perda_por_amostra * w_lote).sum() / w_lote.sum().clamp(min=1e-6)

            otimizador.zero_grad()
            perda.backward()
            otimizador.step()
            soma_perda += float(perda.item())
            n_lotes += 1
        perda_final = soma_perda / max(1, n_lotes)
    modelo.eval()
    return {"n_amostras": n, "epocas": epocas, "perda_final": round(perda_final, 4)}


def treinar_por_imitacao(nome_jogo: str, epocas: int = _EPOCAS_PADRAO_IMITACAO,
                          taxa_aprendizado: float = _TAXA_APRENDIZADO_PADRAO) -> dict:
    """Treina do zero (política nova) só com as demonstrações gravadas.
    Levanta RuntimeError se não houver nenhuma demonstração, ou se
    `torch` não estiver instalado."""
    if not HAS_TORCH:
        raise RuntimeError("Instale 'torch' (requirements-ia.txt) pra eu treinar uma política de jogo.")
    pilhas, acoes, pesos = _carregar_demonstracoes(nome_jogo)
    if not pilhas:
        raise RuntimeError(
            f'Nenhuma demonstração gravada pra "{nome_jogo}" ainda -- diga "aprende a jogar {nome_jogo}" primeiro.'
        )
    modelo = PoliticaJogo()
    resultado = _treinar_com_amostras(
        modelo, np.concatenate(pilhas), np.concatenate(acoes), np.concatenate(pesos),
        epocas, taxa_aprendizado,
    )
    salvar(modelo, armazenamento.caminho_politica(nome_jogo))
    log.info("treinou política de '%s' por imitação: %s", nome_jogo, resultado)
    return resultado


def retreinar_com_sessoes(nome_jogo: str, epocas: int = _EPOCAS_PADRAO_REFINO,
                           taxa_aprendizado: float = _TAXA_APRENDIZADO_PADRAO) -> dict:
    """Continua o treino da política JÁ existente, misturando as
    demonstrações originais (peso cheio) com as sessões de auto-jogo
    gravadas até agora (peso por duração do episódio + feedback -- ver
    docstring do módulo). Levanta RuntimeError se ainda não houver uma
    política treinada (precisa de treinar_por_imitacao primeiro) ou
    nenhuma sessão de auto-jogo pra aprender com ela."""
    if not HAS_TORCH:
        raise RuntimeError("Instale 'torch' (requirements-ia.txt) pra eu treinar uma política de jogo.")
    if not armazenamento.tem_politica_treinada(nome_jogo):
        raise RuntimeError(
            f'Ainda não tenho uma política treinada pra "{nome_jogo}" -- diga "aprende a jogar {nome_jogo}" primeiro.'
        )

    pilhas_demo, acoes_demo, pesos_demo = _carregar_demonstracoes(nome_jogo)
    pilhas_sessao, acoes_sessao, pesos_sessao = _carregar_sessoes(nome_jogo)
    if not pilhas_sessao:
        raise RuntimeError(
            f'Ainda não tenho nenhuma sessão de auto-jogo de "{nome_jogo}" pra aprender com ela -- '
            f'diga "joga {nome_jogo} sozinho" primeiro.'
        )

    from jogos.modelo import carregar
    modelo = carregar(armazenamento.caminho_politica(nome_jogo))
    todas_pilhas = pilhas_demo + pilhas_sessao
    todas_acoes = acoes_demo + acoes_sessao
    todos_pesos = pesos_demo + pesos_sessao
    resultado = _treinar_com_amostras(
        modelo, np.concatenate(todas_pilhas), np.concatenate(todas_acoes), np.concatenate(todos_pesos),
        epocas, taxa_aprendizado,
    )
    salvar(modelo, armazenamento.caminho_politica(nome_jogo))
    log.info("refinou política de '%s' com sessões de auto-jogo: %s", nome_jogo, resultado)
    return resultado
