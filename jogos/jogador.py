"""
jogos/jogador.py
===================
Loop de auto-jogo: usa a política já treinada (jogos/treino.py) pra
jogar sozinho -- captura tela, decide ação, executa via
controle_pc.entrada (segura/solta tecla, move o mouse). Grava a própria
trajetória (frame + ação prevista) durante a sessão, servindo de
matéria-prima pro "melhora sozinho"
(jogos/treino.py:retreinar_com_sessoes).

Duas medidas de segurança que valem a pena destacar:
  - **Checagem de foco a cada tick**: só envia tecla/mouse se a janela
    do jogo (por substring do título, via `pygetwindow`) ainda for a
    janela em primeiro plano -- se o usuário alt-tabar/minimizar, o
    auto-jogo PAUSA sozinho em vez de continuar mandando entrada pra
    janela errada. Por isso `pygetwindow` é EXIGIDO aqui (available()
    abaixo), diferente de outros usos dele no projeto onde é opcional
    -- o risco de mandar entrada simulada pra janela errada é real
    demais pra abrir mão dessa checagem silenciosamente.
  - **Solta toda tecla ao parar**: parar_jogo() (e qualquer saída do
    loop, inclusive por erro -- sempre via `finally`) solta TODAS as
    teclas seguradas no momento. Sem isso uma tecla podia ficar
    "presa" (keyDown sem o keyUp correspondente) se a sessão for
    interrompida no meio de uma ação. `pyautogui.FAILSAFE` (já ligado
    em controle_pc/entrada.py -- mouse no canto superior esquerdo
    aborta TUDO) funciona como botão de pânico físico de graça aqui.

Detecção de "episódio" (reset/game over/reinício) E sinal de
"velocidade/ação" usam a MESMA métrica (jogos.captura.diferenca_de_frames
-- diferença média de pixel entre um quadro e o anterior), só que em
duas escalas diferentes: um salto BRUSCO (`jogos.limiar_deteccao_reset`)
normalmente significa tela de game over/loading/reinício de fase --
fecha o episódio atual (sua DURAÇÃO em quadros vira um proxy de "foi
bem" usado no retreino) e abre um novo. Já o valor quadro a quadro
(sem precisar passar do limiar) é gravado como "sinal_movimento" e
usado por jogos/treino.py pra dar mais peso aos momentos em que as
coisas estavam mudando/andando mais rápido que o normal -- pedido
explícito do usuário: "aprende que se eu fizer isso eu vou mais
rápido". Heurística honesta, não é detecção de verdade do estado do
jogo -- ver core/diagnostico.py e plugins/jogos.py pra como as
limitações são comunicadas ao usuário.
"""

import threading
import time

import numpy as np

from jogos import armazenamento
from jogos.captura import EmpilhadorFrames, diferenca_de_frames, preprocessar_frame, vetor_para_acao
from jogos.modelo import HAS_TORCH
from logs.logger import get_logger

log = get_logger("jogos")

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False

_DURACAO_PADRAO_MINUTOS = 20.0
_FPS_PADRAO = 10
_LIMIAR_RESET_PADRAO = 40.0

_estado = {
    "ativa": False,
    "nome_jogo": None,
    "titulo_janela": None,
    "inicio": None,
    "fim_previsto": None,
    "frames": [],
    "acoes": [],
    "episodio_ids": [],
    "feedback": [],
    "sinais_movimento": [],
    "_episodio_atual": 0,
    "_modelo": None,
    "_empilhador": None,
    "_pausado_por_foco": False,
    "_teclas_pressionadas": set(),
    "_parar_evento": None,
    "_thread": None,
    "_ultimo_resumo": {},
}


def available() -> bool:
    from controle_pc import entrada
    from visao import screen
    return HAS_TORCH and HAS_PYGETWINDOW and entrada.available() and screen.available()


def ativa() -> bool:
    return bool(_estado["ativa"])


def pausado_por_foco() -> bool:
    return bool(_estado["_pausado_por_foco"])


def _duracao_maxima_minutos() -> float:
    from config.settings import get_settings
    return float(get_settings().get("jogos.duracao_maxima_sessao_minutos", _DURACAO_PADRAO_MINUTOS))


def _taxa_fps() -> int:
    from config.settings import get_settings
    return int(get_settings().get("jogos.taxa_quadros_por_segundo", _FPS_PADRAO))


def _limiar_reset() -> float:
    from config.settings import get_settings
    return float(get_settings().get("jogos.limiar_deteccao_reset", _LIMIAR_RESET_PADRAO))


def iniciar_jogo_sozinho(nome_jogo: str, duracao_minutos: float = None, titulo_janela: str = None) -> dict:
    """Inicia uma sessão de auto-jogo de até `duracao_minutos`
    (limitado por `jogos.duracao_maxima_sessao_minutos`), usando a
    política já treinada de `nome_jogo`. `titulo_janela` (opcional):
    substring do título da janela do jogo, se for diferente do nome
    "amigável" usado no chat (padrão: o próprio nome_jogo). Levanta
    RuntimeError se já houver uma sessão ativa, se faltar dependência,
    ou se ainda não existir política treinada pra esse jogo."""
    if ativa():
        raise RuntimeError('Já existe uma sessão de auto-jogo em andamento -- diga "para de jogar" antes de iniciar outra.')
    if not available():
        raise RuntimeError(
            "Instale 'torch' (requirements-ia.txt), 'pygetwindow' e 'pyautogui'/'mss' "
            "(requirements-automacao.txt/requirements-visao.txt) pra eu conseguir jogar sozinho."
        )
    if not armazenamento.tem_politica_treinada(nome_jogo):
        raise RuntimeError(
            f'Ainda não tenho uma política treinada pra "{nome_jogo}" -- diga "aprende a jogar {nome_jogo}" primeiro.'
        )

    from jogos.modelo import carregar
    modelo = carregar(armazenamento.caminho_politica(nome_jogo))

    duracao_minutos = max(0.5, min(float(duracao_minutos or _duracao_maxima_minutos()), _duracao_maxima_minutos()))
    _estado.update({
        "ativa": True,
        "nome_jogo": nome_jogo,
        "titulo_janela": titulo_janela or nome_jogo,
        "inicio": time.time(),
        "fim_previsto": time.time() + duracao_minutos * 60,
        "frames": [],
        "acoes": [],
        "episodio_ids": [],
        "feedback": [],
        "sinais_movimento": [],
        "_episodio_atual": 0,
        "_modelo": modelo,
        "_empilhador": EmpilhadorFrames(),
        "_pausado_por_foco": False,
        "_teclas_pressionadas": set(),
        "_parar_evento": threading.Event(),
        "_ultimo_resumo": {},
    })

    from automacao.notify import notify
    aviso_roblox = (
        " Aviso: automação em experiências do Roblox pode violar os Termos de Serviço da "
        "plataforma -- o risco de banimento de conta é seu."
        if "roblox" in nome_jogo.lower() else ""
    )
    notify(
        "Jogando sozinho",
        f'Jogando "{nome_jogo}" por até {duracao_minutos:.0f} min -- diga "para de jogar" a qualquer momento.'
        + aviso_roblox,
    )

    thread = threading.Thread(target=_loop_jogo, args=(nome_jogo,), daemon=True)
    _estado["_thread"] = thread
    thread.start()
    return {"nome_jogo": nome_jogo, "duracao_minutos": duracao_minutos}


def _janela_em_foco(titulo_substring: str) -> bool:
    try:
        ativa_janela = gw.getActiveWindow()
        return bool(ativa_janela and titulo_substring.lower() in (ativa_janela.title or "").lower())
    except Exception:
        return False  # não deu pra checar -- mais seguro assumir que NÃO está em foco e pausar


def _prever_acao(modelo, pilha: np.ndarray) -> np.ndarray:
    import torch
    with torch.no_grad():
        entrada_tensor = torch.from_numpy(pilha).unsqueeze(0)
        saida = modelo(entrada_tensor)
        teclas = torch.sigmoid(saida["teclas"])[0].numpy()
        mouse = saida["mouse"][0].numpy()
        cliques = torch.sigmoid(saida["cliques"])[0].numpy()
    return np.concatenate([teclas, mouse, cliques]).astype(np.float32)


def _aplicar_acao(acao: dict):
    from controle_pc import entrada
    alvo = set(acao["teclas"])
    atuais = _estado["_teclas_pressionadas"]
    for tecla in atuais - alvo:
        try:
            entrada.soltar_tecla(tecla)
        except Exception as e:
            log.warning("falha ao soltar tecla '%s': %s", tecla, e)
    for tecla in alvo - atuais:
        try:
            entrada.segurar_tecla(tecla)
        except Exception as e:
            log.warning("falha ao segurar tecla '%s': %s", tecla, e)
    _estado["_teclas_pressionadas"] = alvo

    if abs(acao["dx"]) >= 1 or abs(acao["dy"]) >= 1:
        try:
            entrada.mover_mouse_relativo(int(acao["dx"]), int(acao["dy"]))
        except Exception as e:
            log.warning("falha ao mover o mouse: %s", e)
    if acao["clique_esquerdo"]:
        try:
            entrada.clicar(botao="left")
        except Exception as e:
            log.warning("falha ao clicar (esquerdo): %s", e)
    if acao["clique_direito"]:
        try:
            entrada.clicar(botao="right")
        except Exception as e:
            log.warning("falha ao clicar (direito): %s", e)


def _soltar_todas_teclas():
    from controle_pc import entrada
    for tecla in list(_estado["_teclas_pressionadas"]):
        try:
            entrada.soltar_tecla(tecla)
        except Exception as e:
            log.warning("falha ao soltar tecla '%s' ao pausar/parar: %s", tecla, e)
    _estado["_teclas_pressionadas"] = set()


def _loop_jogo(nome_jogo: str):
    from visao import screen

    intervalo = 1.0 / max(1, _taxa_fps())
    limiar_reset = _limiar_reset()
    titulo_janela = _estado["titulo_janela"]
    empilhador = _estado["_empilhador"]
    parar_evento = _estado["_parar_evento"]
    frame_anterior = None

    try:
        while not parar_evento.is_set() and time.time() < _estado["fim_previsto"]:
            inicio_tick = time.time()
            try:
                if not _janela_em_foco(titulo_janela):
                    if not _estado["_pausado_por_foco"]:
                        _soltar_todas_teclas()
                    _estado["_pausado_por_foco"] = True
                else:
                    _estado["_pausado_por_foco"] = False

                    frame = screen.screenshot()
                    frame_proc = preprocessar_frame(frame)

                    sinal_movimento = diferenca_de_frames(frame_proc, frame_anterior)
                    if sinal_movimento > limiar_reset:
                        _estado["_episodio_atual"] += 1
                        empilhador.resetar()
                    frame_anterior = frame_proc

                    pilha = empilhador.adicionar(frame_proc)
                    vetor_acao = _prever_acao(_estado["_modelo"], pilha)
                    _aplicar_acao(vetor_para_acao(vetor_acao))

                    _estado["frames"].append(frame_proc)
                    _estado["acoes"].append(vetor_acao)
                    _estado["episodio_ids"].append(_estado["_episodio_atual"])
                    _estado["feedback"].append(0.0)
                    _estado["sinais_movimento"].append(sinal_movimento)
            except Exception as e:
                log.warning("falha num tick de auto-jogo: %s", e)
            decorrido = time.time() - inicio_tick
            if decorrido < intervalo:
                time.sleep(intervalo - decorrido)
    finally:
        _finalizar(nome_jogo)


def registrar_feedback(bom: bool) -> bool:
    """Marca todos os quadros do episódio MAIS RECENTE (o que está
    rolando agora, ou o último que rolou) com o sinal do usuário --
    ver jogos/treino.py:retreinar_com_sessoes pra como isso pesa no
    retreino. Retorna False se não há nenhum quadro registrado ainda
    pra marcar."""
    if not _estado["episodio_ids"]:
        return False
    episodio_alvo = _estado["episodio_ids"][-1]
    valor = 1.0 if bom else -1.0
    for i in range(len(_estado["episodio_ids"]) - 1, -1, -1):
        if _estado["episodio_ids"][i] != episodio_alvo:
            break
        _estado["feedback"][i] = valor
    return True


def _finalizar(nome_jogo: str) -> dict:
    _soltar_todas_teclas()

    n_frames = len(_estado["frames"])
    resumo = {"n_quadros": n_frames, "n_episodios": _estado["_episodio_atual"] + 1, "caminho": ""}
    if n_frames > 0:
        import os
        pasta = armazenamento.pasta_sessoes(nome_jogo)
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, f"{int(time.time())}.npz")
        np.savez_compressed(
            caminho,
            frames=np.array(_estado["frames"], dtype=np.uint8),
            acoes=np.array(_estado["acoes"], dtype=np.float32),
            episodio_ids=np.array(_estado["episodio_ids"], dtype=np.int32),
            feedback=np.array(_estado["feedback"], dtype=np.float32),
            sinais_movimento=np.array(_estado["sinais_movimento"], dtype=np.float32),
        )
        resumo["caminho"] = caminho

    _estado["ativa"] = False
    _estado["_ultimo_resumo"] = resumo
    from automacao.notify import notify
    notify(
        "Auto-jogo encerrado",
        f'Joguei "{nome_jogo}": {resumo["n_quadros"]} quadro(s) em {resumo["n_episodios"]} episódio(s).',
    )
    return resumo


def parar_jogo() -> dict:
    """Encerra a sessão de auto-jogo em andamento (se houver) antes do
    teto de tempo. Bloqueia até a sessão (incluindo soltar as teclas e
    salvar em disco) terminar de verdade."""
    if not ativa():
        return {"parou": False, **_estado["_ultimo_resumo"]}
    _estado["_parar_evento"].set()
    thread = _estado.get("_thread")
    if thread:
        thread.join(timeout=15.0)
    return {"parou": True, **_estado["_ultimo_resumo"]}
