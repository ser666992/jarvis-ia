"""
jogos/
========
"Aprendiz de jogos": Jarvis aprende a jogar por IMITAÇÃO (observa você
jogar) e depois se aperfeiçoa sozinho jogando de novo (auto-jogo,
ponderando o retreino pela duração de cada tentativa + feedback seu --
ver jogos/treino.py:retreinar_com_sessoes). Genérico: mesmo pipeline
serve pra qualquer jogo de PC, não é específico de nenhum.

Também aprende, desde a PRIMEIRA imitação, quais momentos importam
mais: cada quadro carrega um "sinal de movimento" (jogos.captura.diferenca_de_frames
-- quanto a cena mudou desde o quadro anterior), e jogos/treino.py dá
MAIS peso, no treino, aos momentos em que as coisas estavam
mudando/andando mais rápido que o normal da gravação -- pedido
explícito do usuário: "aprende que se eu fizer isso eu vou mais
rápido". Honesto: é um proxy de MOVIMENTO NA TELA, não uma leitura
real de velocidade dentro do jogo (câmera balançando muito também
conta) -- mas é genérico, funciona em qualquer jogo, sem precisar ler
HUD nenhum.

Honestidade sobre o que isto É e NÃO é (ver plugins/jogos.py pra como
isso é comunicado no chat, e core/diagnostico.py pro status):
  - NÃO é aprendizado por reforço "de verdade" (policy gradient) --
    essa máquina não tem GPU (ver sistema.hardware.detect_gpu()), e
    RL de verdade precisaria de uma quantidade de tentativas inviável
    em CPU. É "behavior cloning" (aprender por imitação) ponderado por
    proxies de recompensa (sinal de movimento por quadro, duração até
    um reset detectado, feedback opcional do usuário) -- aprendizado
    real, mas mais modesto que os agentes de RL que você vê em
    demonstrações com GPU.
  - NÃO vai jogar bem/como um profissional -- aprende comportamentos
    reativos simples (repetir padrões vistos, reagir a mudanças
    bruscas na tela), não estratégia real (não otimiza uma linha de
    corrida, não resolve puzzle).
  - Cada jogo precisa da SUA PRÓPRIA demonstração + treino -- nada
    transfere automaticamente entre jogos diferentes (a arquitetura é
    genérica, a política treinada não é).
  - Roblox especificamente: automação pode violar os Termos de Serviço
    da plataforma em muitas experiências -- risco de banimento de
    conta é do usuário, e isso é avisado explicitamente quando o nome
    do jogo contém "roblox" (ver jogos/jogador.py).

Pipeline: jogos/gravador.py (grava você jogando) ->
jogos/treino.py:treinar_por_imitacao (aprende a imitar) ->
jogos/jogador.py (joga sozinho, grava a própria trajetória) ->
jogos/treino.py:retreinar_com_sessoes (refina com o que aconteceu no
auto-jogo). jogos/captura.py define o formato de observação/ação
compartilhado por gravador e jogador -- nunca diverge entre os dois.
jogos/armazenamento.py resolve os caminhos em disco (data/jogos/<jogo>/).
"""

from jogos.armazenamento import (
    apagar_jogo,
    jogos_conhecidos,
    tem_politica_treinada,
)
from jogos.gravador import ativa as gravacao_ativa
from jogos.gravador import iniciar_gravacao, parar_gravacao
from jogos.jogador import ativa as jogo_ativo
from jogos.jogador import iniciar_jogo_sozinho, parar_jogo, pausado_por_foco, registrar_feedback
from jogos.modelo import HAS_TORCH
from jogos.treino import retreinar_com_sessoes, treinar_por_imitacao

__all__ = [
    "available", "status", "HAS_TORCH",
    "iniciar_gravacao", "parar_gravacao", "gravacao_ativa",
    "treinar_por_imitacao", "retreinar_com_sessoes",
    "iniciar_jogo_sozinho", "parar_jogo", "jogo_ativo", "pausado_por_foco", "registrar_feedback",
    "jogos_conhecidos", "tem_politica_treinada", "apagar_jogo",
]


def available() -> bool:
    """Disponibilidade GERAL: pelo menos GRAVAR uma demonstração tem
    que ser possível (é sempre o primeiro passo do pipeline). Treinar
    e jogar sozinho também exigem `torch` (HAS_TORCH) -- reportado
    separadamente em core/diagnostico.py, pra distinguir "não consigo
    nem começar" de "gravei, mas não consigo treinar ainda"."""
    from jogos import gravador
    return gravador.available()


def status(nome_jogo: str) -> dict:
    """Resumo pro comando de chat "como você está indo no <jogo>":
    quantas demonstrações, quantas sessões de auto-jogo, se já existe
    política treinada, e se a duração média dos episódios está
    melhorando (compara a primeira metade das sessões gravadas com a
    segunda) -- proxy honesto de progresso, não uma nota/pontuação
    real do jogo."""
    import numpy as np

    from jogos import armazenamento

    demos = armazenamento.listar_demonstracoes(nome_jogo)
    sessoes = armazenamento.listar_sessoes(nome_jogo)

    duracoes_por_sessao = []
    for caminho in sessoes:
        dados = np.load(caminho)
        eids = dados["episodio_ids"]
        if len(eids) == 0:
            continue
        _, contagens = np.unique(eids, return_counts=True)
        duracoes_por_sessao.append(float(np.mean(contagens)))

    tendencia = None
    if len(duracoes_por_sessao) >= 2:
        metade = len(duracoes_por_sessao) // 2
        media_antiga = np.mean(duracoes_por_sessao[:metade]) if metade else duracoes_por_sessao[0]
        media_recente = np.mean(duracoes_por_sessao[metade:])
        if media_recente > media_antiga * 1.05:
            tendencia = "melhorando"
        elif media_recente < media_antiga * 0.95:
            tendencia = "piorando"
        else:
            tendencia = "estável"

    return {
        "n_demonstracoes": len(demos),
        "n_sessoes": len(sessoes),
        "duracao_media_episodio_quadros": round(float(np.mean(duracoes_por_sessao)), 1) if duracoes_por_sessao else None,
        "tendencia": tendencia,
        "tem_politica_treinada": armazenamento.tem_politica_treinada(nome_jogo),
    }
