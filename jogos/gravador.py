"""
jogos/gravador.py
====================
Sessão de gravação de demonstração: enquanto o usuário joga
normalmente, grava screenshots (reduzidos, ver jogos/captura.py) e a
ação real dele (teclado + mouse, via `pynput`, escuta GLOBAL -- não
simula nada, só observa) a uma taxa fixa. É a base do aprendizado por
imitação (jogos/treino.py:treinar_por_imitacao) -- sem isso não tem o
que treinar.

Mesmo padrão de automacao/escuta_ativa.py (sessão com tempo limitado,
thread daemon dedicada, aviso sonoro no início/fim, pode ser encerrada
a qualquer momento):
  - Só começa com comando EXPLÍCITO do usuário -- nunca liga sozinha.
  - Teto de segurança (`jogos.duracao_maxima_demonstracao_minutos`,
    15 min por padrão).
  - Avisa quando começa e quando termina.
  - "para de gravar" encerra antes do teto, a qualquer momento.

Diferente de escuta_ativa: aqui cada "tick" é barato (um screenshot +
ler o estado atual do teclado/mouse), então roda num LOOP DE INTERVALO
FIXO (jogos.taxa_quadros_por_segundo, 10 por padrão) em vez de uma
gravação bloqueante longa por iteração.

Também grava, quadro a quadro, um "sinal de movimento"
(jogos.captura.diferenca_de_frames -- quanto a cena mudou desde o
quadro anterior). Sozinho isso não vira nada ainda; é
jogos/treino.py quem usa pra dar MAIS peso, no treino por imitação,
aos momentos em que as coisas estavam mudando/andando mais rápido que
o normal -- pedido explícito do usuário: "aprende que se eu fizer isso
eu vou mais rápido".
"""

import threading
import time

import numpy as np

from jogos import armazenamento
from jogos.captura import diferenca_de_frames, estado_para_vetor, preprocessar_frame
from logs.logger import get_logger

log = get_logger("jogos")

try:
    from pynput import keyboard as _pynput_keyboard
    from pynput import mouse as _pynput_mouse
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

_DURACAO_PADRAO_MINUTOS = 15.0
_FPS_PADRAO = 10

# Protege o estado de teclado/mouse abaixo (_teclas_seguradas/_dx_acumulado/
# _dy_acumulado/_clique_esquerdo/_clique_direito) -- escrito pelos callbacks
# do pynput (rodam na(s) thread(s) do próprio listener) e lido/resetado por
# _loop_gravacao (outra thread). Sem o lock, `set(_estado["_teclas_seguradas"])`
# iterando enquanto _on_press/_on_release chama .add()/.discard() em cima podia
# levantar "RuntimeError: Set changed size during iteration" -- bug real
# encontrado em revisão (o try/except por tick já evitava crashar a sessão
# inteira, mas perdia o quadro daquele tick à toa).
_lock_entrada = threading.Lock()

_estado = {
    "ativa": False,
    "nome_jogo": None,
    "inicio": None,
    "fim_previsto": None,
    "frames": [],
    "acoes": [],
    "sinais_movimento": [],
    "_teclas_seguradas": set(),
    "_pos_mouse_anterior": None,
    "_dx_acumulado": 0.0,
    "_dy_acumulado": 0.0,
    "_clique_esquerdo": False,
    "_clique_direito": False,
    "_parar_evento": None,
    "_thread": None,
    "_kb_listener": None,
    "_mouse_listener": None,
    "_ultimo_caminho_salvo": "",
}


def available() -> bool:
    from visao import screen
    return HAS_PYNPUT and screen.available()


def ativa() -> bool:
    return bool(_estado["ativa"])


def _duracao_maxima_minutos() -> float:
    from config.settings import get_settings
    return float(get_settings().get("jogos.duracao_maxima_demonstracao_minutos", _DURACAO_PADRAO_MINUTOS))


def _taxa_fps() -> int:
    from config.settings import get_settings
    return int(get_settings().get("jogos.taxa_quadros_por_segundo", _FPS_PADRAO))


def _on_press(key):
    from jogos.captura import normalizar_tecla_pynput
    nome = normalizar_tecla_pynput(key)
    if nome:
        with _lock_entrada:
            _estado["_teclas_seguradas"].add(nome)


def _on_release(key):
    from jogos.captura import normalizar_tecla_pynput
    nome = normalizar_tecla_pynput(key)
    if nome:
        with _lock_entrada:
            _estado["_teclas_seguradas"].discard(nome)


def _on_move(x, y):
    anterior = _estado["_pos_mouse_anterior"]
    if anterior is not None:
        with _lock_entrada:
            _estado["_dx_acumulado"] += x - anterior[0]
            _estado["_dy_acumulado"] += y - anterior[1]
    _estado["_pos_mouse_anterior"] = (x, y)  # só a thread do mouse listener escreve isso -- sem risco de corrida


def _on_click(x, y, button, pressed):
    with _lock_entrada:
        if str(button).endswith("left"):
            _estado["_clique_esquerdo"] = pressed
        elif str(button).endswith("right"):
            _estado["_clique_direito"] = pressed


def _ler_e_resetar_estado_de_entrada():
    """Lê o estado atual de teclado/mouse (cópia segura) e já zera o
    acumulador de movimento do mouse pro próximo tick -- tudo dentro do
    MESMO lock, pra não intercalar com um _on_press/_on_move no meio
    da leitura (a causa do bug de RuntimeError descrito acima)."""
    with _lock_entrada:
        teclas = set(_estado["_teclas_seguradas"])
        dx, dy = _estado["_dx_acumulado"], _estado["_dy_acumulado"]
        _estado["_dx_acumulado"] = 0.0
        _estado["_dy_acumulado"] = 0.0
        clique_esquerdo = _estado["_clique_esquerdo"]
        clique_direito = _estado["_clique_direito"]
    return teclas, dx, dy, clique_esquerdo, clique_direito


def iniciar_gravacao(nome_jogo: str, duracao_minutos: float = None) -> dict:
    """Inicia uma sessão de gravação de até `duracao_minutos` (limitado
    por `jogos.duracao_maxima_demonstracao_minutos`). Levanta
    RuntimeError se já houver uma gravação em andamento, ou se faltar
    `pynput`/captura de tela."""
    if ativa():
        raise RuntimeError('Já existe uma gravação em andamento -- diga "para de gravar" antes de iniciar outra.')
    if not available():
        raise RuntimeError(
            "Instale 'pynput' (requirements-automacao.txt) e 'mss' (requirements-visao.txt) "
            "pra eu conseguir gravar uma demonstração."
        )

    duracao_minutos = max(0.5, min(float(duracao_minutos or _duracao_maxima_minutos()), _duracao_maxima_minutos()))
    _estado.update({
        "ativa": True,
        "nome_jogo": nome_jogo,
        "inicio": time.time(),
        "fim_previsto": time.time() + duracao_minutos * 60,
        "frames": [],
        "acoes": [],
        "sinais_movimento": [],
        "_teclas_seguradas": set(),
        "_pos_mouse_anterior": None,
        "_dx_acumulado": 0.0,
        "_dy_acumulado": 0.0,
        "_clique_esquerdo": False,
        "_clique_direito": False,
        "_parar_evento": threading.Event(),
    })

    _estado["_kb_listener"] = _pynput_keyboard.Listener(on_press=_on_press, on_release=_on_release)
    _estado["_mouse_listener"] = _pynput_mouse.Listener(on_move=_on_move, on_click=_on_click)
    _estado["_kb_listener"].start()
    _estado["_mouse_listener"].start()

    from automacao.notify import notify
    notify(
        "Gravando demonstração",
        f'Observando você jogar "{nome_jogo}" por até {duracao_minutos:.0f} min -- '
        'diga "para de gravar" quando quiser encerrar antes.',
    )

    thread = threading.Thread(target=_loop_gravacao, args=(nome_jogo,), daemon=True)
    _estado["_thread"] = thread
    thread.start()
    return {"nome_jogo": nome_jogo, "duracao_minutos": duracao_minutos}


def _loop_gravacao(nome_jogo: str):
    from visao import screen

    intervalo = 1.0 / max(1, _taxa_fps())
    parar_evento = _estado["_parar_evento"]
    frame_anterior = None
    try:
        while not parar_evento.is_set() and time.time() < _estado["fim_previsto"]:
            inicio_tick = time.time()
            try:
                frame = screen.screenshot()
                frame_proc = preprocessar_frame(frame)
                sinal_movimento = diferenca_de_frames(frame_proc, frame_anterior)
                frame_anterior = frame_proc

                teclas, dx, dy, clique_esquerdo, clique_direito = _ler_e_resetar_estado_de_entrada()
                vetor_acao = estado_para_vetor(teclas, dx, dy, clique_esquerdo, clique_direito)
                _estado["frames"].append(frame_proc)
                _estado["acoes"].append(vetor_acao)
                _estado["sinais_movimento"].append(sinal_movimento)
            except Exception as e:
                log.warning("falha ao capturar quadro da gravação: %s", e)
            decorrido = time.time() - inicio_tick
            if decorrido < intervalo:
                time.sleep(intervalo - decorrido)
    finally:
        _finalizar(nome_jogo)


def _finalizar(nome_jogo: str) -> str:
    """Para os listeners, salva o que foi gravado (se houver ao menos
    um quadro) e devolve o caminho salvo (ou "" se nada foi gravado --
    ex.: parou imediatamente após iniciar)."""
    for listener_key in ("_kb_listener", "_mouse_listener"):
        listener = _estado.get(listener_key)
        if listener:
            listener.stop()
        _estado[listener_key] = None

    caminho = ""
    n_frames = len(_estado["frames"])
    if n_frames > 0:
        import os
        pasta = armazenamento.pasta_demonstracoes(nome_jogo)
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, f"{int(time.time())}.npz")
        np.savez_compressed(
            caminho,
            frames=np.array(_estado["frames"], dtype=np.uint8),
            acoes=np.array(_estado["acoes"], dtype=np.float32),
            sinais_movimento=np.array(_estado["sinais_movimento"], dtype=np.float32),
        )

    _estado["ativa"] = False
    _estado["_ultimo_caminho_salvo"] = caminho
    from automacao.notify import notify
    if n_frames > 0:
        notify("Gravação encerrada", f'Gravei {n_frames} quadro(s) de "{nome_jogo}".')
    else:
        notify("Gravação encerrada", "Nenhum quadro foi capturado -- gravação descartada.")
    return caminho


def parar_gravacao() -> dict:
    """Encerra a gravação em andamento (se houver) antes do teto de
    tempo. Pode levar até ~1 tick (jogos.taxa_quadros_por_segundo) pra
    surtir efeito de verdade -- mesmo raciocínio de
    automacao/escuta_ativa.py:parar(). Bloqueia até a gravação
    (incluindo salvar em disco) terminar de verdade, então o número de
    quadros/caminho devolvidos já são os finais."""
    if not ativa():
        return {"parou": False, "n_quadros": 0, "caminho": "", "nome_jogo": ""}
    nome_jogo = _estado["nome_jogo"]
    _estado["_parar_evento"].set()
    thread = _estado.get("_thread")
    if thread:
        thread.join(timeout=15.0)
    return {
        "parou": True, "n_quadros": len(_estado["frames"]),
        "caminho": _estado["_ultimo_caminho_salvo"], "nome_jogo": nome_jogo,
    }
