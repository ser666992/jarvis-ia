"""
controle_pc/janelas.py
=========================
`alternar_para` reaproveita automacao.janelas.focar (já existe, não
duplica). `organizar_janelas` é capacidade NOVA: arranjar as janelas
visíveis em grade (lado a lado) ou cascata -- automacao/janelas.py só
tinha minimizar/maximizar/restaurar/focar uma janela de cada vez.

Não passa por seguranca.permissions: mover/redimensionar uma janela é
reversível na hora (mesma janela continua aberta, só muda de posição/
tamanho) -- mesmo raciocínio já documentado em automacao/janelas.py.
"""

from logs.logger import get_logger

log = get_logger("controle_pc")

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False


def available() -> bool:
    return HAS_PYGETWINDOW


def alternar_para(titulo_substring: str) -> bool:
    """Traz a janela cujo título contém `titulo_substring` pra frente
    -- reaproveita automacao.janelas.focar, não reimplementa."""
    from automacao import janelas
    return janelas.focar(titulo_substring)


def _janelas_visiveis():
    return [
        w for w in gw.getAllWindows()
        if w.title and w.visible and not w.isMinimized and w.width > 0 and w.height > 0
    ]


def organizar_janelas(modo: str = "grade") -> int:
    """Reorganiza as janelas visíveis na tela -- "grade" (divide a tela
    em blocos iguais, uma janela por bloco) ou "cascata" (empilha com
    deslocamento, título de cada uma sempre visível). Retorna quantas
    janelas foram reorganizadas."""
    if not HAS_PYGETWINDOW:
        raise RuntimeError("Instale 'pygetwindow' (requirements-automacao.txt) para eu organizar janelas.")

    janelas = _janelas_visiveis()
    if not janelas:
        return 0

    tela_largura, tela_altura = _tamanho_tela()

    if modo == "cascata":
        offset = 40
        largura, altura = int(tela_largura * 0.6), int(tela_altura * 0.6)
        for i, w in enumerate(janelas):
            try:
                w.resizeTo(largura, altura)
                w.moveTo((i * offset) % (tela_largura - largura), (i * offset) % (tela_altura - altura))
            except Exception as e:
                log.warning("falha ao reorganizar (cascata) '%s': %s", w.title, e)
        return len(janelas)

    # "grade": calcula uma grade quase quadrada (colunas >= linhas)
    n = len(janelas)
    colunas = 1
    while colunas * colunas < n:
        colunas += 1
    linhas = (n + colunas - 1) // colunas
    largura_bloco = tela_largura // colunas
    altura_bloco = tela_altura // linhas

    for i, w in enumerate(janelas):
        col, lin = i % colunas, i // colunas
        try:
            w.resizeTo(largura_bloco, altura_bloco)
            w.moveTo(col * largura_bloco, lin * altura_bloco)
        except Exception as e:
            log.warning("falha ao reorganizar (grade) '%s': %s", w.title, e)
    return len(janelas)


def _tamanho_tela():
    try:
        import pyautogui
        return pyautogui.size()
    except Exception:
        return (1920, 1080)  # fallback razoável se pyautogui não estiver instalado
