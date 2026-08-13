"""
controle_pc/entrada.py
=========================
Mouse e teclado simulados, via `pyautogui` (requirements-automacao.txt
já previa isso: "automação de teclado/mouse mais avançada, para
plugins que quiserem ir além do que automacao/apps.py já cobre").

Sem confirmação exigida (ver __init__.py do pacote pra explicação):
mover o mouse/clicar/digitar é entrada simulada reversível, mesma
categoria de automacao/janelas.py (minimizar/focar) -- o que a AÇÃO
resultante faz dentro do programa focado não é algo que dá pra prever
ou controlar aqui, mesma limitação de qualquer automação de UI.
"""

from logs.logger import get_logger

log = get_logger("controle_pc")

try:
    import pyautogui
    pyautogui.FAILSAFE = True  # mover o mouse pro canto superior esquerdo aborta -- rede de segurança padrão do pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


def available() -> bool:
    return HAS_PYAUTOGUI


def _exigir():
    if not HAS_PYAUTOGUI:
        raise RuntimeError("Instale 'pyautogui' (requirements-automacao.txt) para eu controlar mouse/teclado.")


def mover_mouse(x: int, y: int, duracao: float = 0.0):
    _exigir()
    pyautogui.moveTo(x, y, duration=duracao)


def mover_mouse_relativo(dx: int, dy: int):
    """Desloca o mouse RELATIVO à posição atual (dx/dy em pixels) --
    diferente de mover_mouse (posição ABSOLUTA). Usado por
    jogos/jogador.py pra simular movimento de câmera/mira: um jogo não
    liga pra posição absoluta do cursor, só pro quanto ele se moveu
    desde o frame anterior."""
    _exigir()
    pyautogui.moveRel(dx, dy, duration=0.0)


def segurar_tecla(tecla: str):
    """Pressiona `tecla` e MANTÉM segurada até soltar_tecla() ser
    chamado -- diferente de pressionar_tecla() (toque único,
    pressiona-e-solta na hora). Usado por jogos/jogador.py pra ações
    contínuas tipo "andar pra frente enquanto W estiver ativo"."""
    _exigir()
    pyautogui.keyDown(tecla)


def soltar_tecla(tecla: str):
    _exigir()
    pyautogui.keyUp(tecla)


def clicar(x: int = None, y: int = None, botao: str = "left", duplo: bool = False):
    """Clica na posição dada, ou na posição atual do mouse se x/y não
    forem passados (útil depois de mover_mouse ou de
    controle_pc.elementos.localizar_elemento)."""
    _exigir()
    if duplo:
        pyautogui.doubleClick(x=x, y=y, button=botao)
    else:
        pyautogui.click(x=x, y=y, button=botao)


def digitar_texto(texto: str, intervalo: float = 0.02):
    """Digita `texto` na caixa/campo que estiver com foco no momento --
    quem chama é responsável por garantir que o campo certo já está
    focado (ex.: clicar nele antes)."""
    _exigir()
    pyautogui.write(texto, interval=intervalo)


def pressionar_tecla(tecla: str):
    """Uma tecla ou atalho -- `tecla` pode ser um nome único
    ("enter", "esc", "f5") ou uma combinação separada por "+"
    ("ctrl+s", "alt+tab")."""
    _exigir()
    partes = [p.strip() for p in tecla.lower().split("+") if p.strip()]
    if len(partes) > 1:
        pyautogui.hotkey(*partes)
    else:
        pyautogui.press(partes[0] if partes else tecla)
