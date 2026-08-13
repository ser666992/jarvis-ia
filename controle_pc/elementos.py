"""
controle_pc/elementos.py
===========================
Localizar um elemento de interface (botão, item de menu, campo) por
TEXTO (via UI Automation, mesma técnica de visao_continua/monitor.py)
ou por IMAGEM (template matching via `pyautogui.locateOnScreen`, pra
ícones/botões sem texto acessível) e interagir com ele -- em vez de
precisar saber a coordenada de pixel exata na tela, que muda a cada
resolução/tema/janela.
"""

import sys

from logs.logger import get_logger

log = get_logger("controle_pc")

# IMPORTANTE: pywinauto NÃO é importado aqui em cima, de propósito --
# ver o mesmo comentário em visao_continua/monitor.py. Importar
# pywinauto executa inicialização de COM (apartment threading) na hora
# do import; fazer isso cedo demais (ex.: durante o startup do Jarvis,
# na mesma thread que outras libs também mexem em COM, como
# win32com/Playwright) pode causar `RPC_E_CHANGED_MODE` -- erro real,
# reproduzido. A importação fica dentro de _localizar_por_texto(), só
# na hora que alguém realmente pede pra clicar em algo por nome.
HAS_PYWINAUTO = sys.platform == "win32"

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


def _hwnd_janela_foco():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


# Só tipos de controle genuinamente CLICÁVEIS -- exclui de propósito
# "Text"/"Pane"/"Document"/"Group"/"Custom" (texto estático, painéis,
# conteúdo de editor/terminal). Achado em teste real: um painel de
# terminal com tipo "Text" e só 194 caracteres (abaixo de um teto por
# TAMANHO que eu tinha tentado primeiro) "encontrava" a si mesmo como
# se fosse um botão só por conter a palavra buscada em algum lugar do
# texto exibido -- filtrar por TIPO em vez de só por tamanho resolve a
# causa raiz (um "Text" nunca é algo que faça sentido clicar).
_TIPOS_CLICAVEIS = (
    "Button", "MenuItem", "Menu", "Hyperlink", "CheckBox",
    "RadioButton", "ComboBox", "SplitButton", "TabItem", "ListItem",
)


def _localizar_por_texto(texto: str):
    """Procura, entre os elementos CLICÁVEIS da janela em foco, um cujo
    nome acessível contenha `texto` (case-insensitive) -- retorna o
    centro (x, y) e o retângulo, ou None se não achou.

    String de busca vazia é recusada de propósito -- toda string
    contém a vazia, então sem essa checagem qualquer busca "vazia"
    bateria com o primeiro elemento clicável que encontrasse.

    IMPORTANTE (correção de desempenho real, mesmo bug encontrado em
    visao_continua/monitor.py:_elementos_janela_foco): `janela.descendants()`
    SEM filtro enumera e materializa TODOS os descendentes da janela via
    UI Automation (uma chamada COM fora de processo por elemento pra ler
    `control_type`/`name`) antes de filtrar por tipo em Python -- em
    janelas complexas (navegador, IDE) isso podia fazer "clica no botão
    X" travar por vários segundos. Agora cada tipo clicável é buscado
    com `descendants(control_type=tipo)`, que aplica o filtro no UI
    Automation nativo -- só os elementos que já batem o tipo cruzam a
    fronteira COM -- e a busca para assim que encontra o primeiro nome
    batendo, sem precisar esgotar os tipos restantes."""
    if not HAS_PYWINAUTO:
        return None
    alvo = texto.strip().lower()
    if not alvo:
        return None
    hwnd = _hwnd_janela_foco()
    if not hwnd:
        return None
    try:
        from pywinauto import Desktop as _PywinautoDesktop  # import atrasado -- ver comentário no topo do arquivo
        janela = _PywinautoDesktop(backend="uia").window(handle=hwnd)
        for tipo in _TIPOS_CLICAVEIS:
            try:
                achados = janela.descendants(control_type=tipo)
            except Exception:
                continue
            for c in achados:
                try:
                    info = c.element_info
                    nome_bruto = (info.name or "").strip()
                    if not nome_bruto:
                        continue
                    nome = nome_bruto.lower()
                    if alvo not in nome:
                        continue
                    rect = info.rectangle
                    cx = (rect.left + rect.right) // 2
                    cy = (rect.top + rect.bottom) // 2
                    return {"x": cx, "y": cy, "retangulo": (rect.left, rect.top, rect.right, rect.bottom), "nome": info.name}
                except Exception:
                    continue
    except Exception as e:
        log.warning("falha ao localizar elemento por texto: %s", e)
    return None


def _localizar_por_imagem(caminho_imagem: str, confianca: float = 0.8):
    if not HAS_PYAUTOGUI:
        return None
    try:
        caixa = pyautogui.locateOnScreen(caminho_imagem, confidence=confianca)
    except Exception as e:
        log.warning("falha ao localizar elemento por imagem: %s", e)
        return None
    if not caixa:
        return None
    cx, cy = pyautogui.center(caixa)
    return {"x": cx, "y": cy, "retangulo": (caixa.left, caixa.top, caixa.left + caixa.width, caixa.top + caixa.height), "nome": caminho_imagem}


def localizar_elemento(texto: str = None, imagem: str = None) -> dict:
    """Retorna {"x", "y", "retangulo", "nome"} do elemento encontrado,
    ou None. Passe `texto` (nome acessível, ex.: "Salvar") OU `imagem`
    (caminho de um recorte de tela do ícone/botão) -- se os dois forem
    passados, tenta texto primeiro."""
    if texto:
        achado = _localizar_por_texto(texto)
        if achado:
            return achado
    if imagem:
        return _localizar_por_imagem(imagem)
    return None


def clicar_elemento(texto: str = None, imagem: str = None, botao: str = "left") -> bool:
    """Localiza (por texto ou imagem) e clica no centro do elemento.
    Retorna False se não encontrou nada pra clicar."""
    from controle_pc.entrada import clicar
    elemento = localizar_elemento(texto=texto, imagem=imagem)
    if not elemento:
        return False
    clicar(elemento["x"], elemento["y"], botao=botao)
    return True
