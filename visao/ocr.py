"""
visao/ocr.py
==============
Leitura de texto em imagens (OCR) via `pytesseract`, que por sua vez
depende do binário Tesseract instalado no sistema operacional (não é
só `pip install` -- ver requirements-visao.txt para instruções).

`localizar_texto_na_tela()` vai além de só ler o texto: devolve TAMBÉM
a posição (coordenadas absolutas de tela) de cada trecho encontrado,
via `pytesseract.image_to_data()` (bounding box por palavra) em vez de
`image_to_string()` (só o texto corrido) -- base de
"clica no texto ..." (ver plugins/clicar_texto.py + controle_pc/entrada.py),
que combina visão computacional com controle de mouse/teclado.
"""

import os

from logs.logger import get_logger

log = get_logger("visao")

try:
    import pytesseract
    from PIL import Image
    HAS_OCR_LIBS = True
except ImportError:
    HAS_OCR_LIBS = False


def _localizar_tesseract():
    """O instalador do Tesseract (UB-Mannheim/winget) NÃO adiciona o
    binário ao PATH por padrão, então o pytesseract não o acha e o OCR
    fica "indisponível" mesmo instalado. Aqui a gente procura nos
    caminhos de instalação padrão do Windows e aponta o pytesseract pra
    ele explicitamente -- assim o OCR funciona logo após instalar, sem
    o usuário ter que mexer no PATH manualmente."""
    if not HAS_OCR_LIBS or os.name != "nt":
        return
    candidatos = [
        os.path.expandvars(r"%ProgramFiles%\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for caminho in candidatos:
        if os.path.isfile(caminho):
            pytesseract.pytesseract.tesseract_cmd = caminho
            return


if HAS_OCR_LIBS:
    _localizar_tesseract()


_disponivel_cache = None  # evita rechecar o binário a cada chamada (ver motivo abaixo)


def available() -> bool:
    """Cacheado após a primeira checagem: `pytesseract.get_tesseract_version()`
    chama o binário Tesseract como SUBPROCESSO de verdade, não é uma
    checagem em memória -- sem cache, `visao_continua` (que chama isto a
    cada tick em que a tela mudou, ver monitor.py:_tick) pagava esse
    custo de processo a cada tick, driblando a instalação do Tesseract
    (que não muda no meio da execução) desnecessariamente. Se a
    instalação mudar (ex.: instalou o Tesseract com o Ultron já rodando),
    reinicie pra refletir."""
    global _disponivel_cache
    if _disponivel_cache is not None:
        return _disponivel_cache
    if not HAS_OCR_LIBS:
        _disponivel_cache = False
        return False
    try:
        pytesseract.get_tesseract_version()
        _disponivel_cache = True
    except Exception:
        _disponivel_cache = False
    return _disponivel_cache


_idioma_cache = None


def _resolver_idioma(lang: str) -> str:
    """Se o idioma pedido (ex.: 'por') NÃO estiver instalado no Tesseract,
    cai pro 'eng' (que vem por padrão) em vez de falhar e devolver texto
    vazio. O instalador do Tesseract não traz o português por padrão, e
    o OCR em inglês lê texto em português numa boa (mesmo alfabeto) --
    então é melhor ler com 'eng' do que não ler nada. Resultado
    cacheado (consultar os idiomas chama o binário)."""
    global _idioma_cache
    if _idioma_cache is None:
        try:
            _idioma_cache = set(pytesseract.get_languages(config=""))
        except Exception:
            _idioma_cache = set()
    if lang in _idioma_cache:
        return lang
    if "eng" in _idioma_cache:
        return "eng"
    return lang  # deixa o pytesseract reclamar se nem eng existir


def read_text_from_file(path: str, lang: str = "por") -> str:
    if not HAS_OCR_LIBS:
        raise RuntimeError("Instale 'pytesseract' e 'Pillow' (e o binário Tesseract OCR) para OCR.")
    image = Image.open(path)
    return pytesseract.image_to_string(image, lang=_resolver_idioma(lang))


def _preprocessar_para_ocr(frame):
    """Melhora a precisão do Tesseract em screenshots/fotos: texto de
    interface costuma ser pequeno e com antialiasing (bordas suavizadas
    em vez de preto sólido), bem diferente do documento escaneado
    (texto grande, preto sólido, fundo branco) em que o Tesseract foi
    majoritariamente treinado -- lido "cru", ele erra/perde letras com
    frequência. Escala de cinza + upscale 2x (mais pixels por letra,
    ajuda muito com texto pequeno de UI) + binarização Otsu (preto/
    branco sólido, remove o antialiasing e variação de fundo) aproxima
    a imagem do caso que o Tesseract lê bem -- sem exigir nenhuma
    dependência nova (só `cv2`, já usado aqui)."""
    import cv2
    cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    maior = cv2.resize(cinza, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, binarizado = cv2.threshold(maior, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binarizado


def read_text_from_frame(frame, lang: str = "por") -> str:
    """frame: numpy array BGR (ex.: vindo de visao.camera.Camera.snapshot()
    ou visao.screen.screenshot())."""
    if not HAS_OCR_LIBS:
        raise RuntimeError("Instale 'pytesseract' e 'Pillow' (e o binário Tesseract OCR) para OCR.")
    processado = _preprocessar_para_ocr(frame)
    image = Image.fromarray(processado)
    return pytesseract.image_to_string(image, lang=_resolver_idioma(lang))


_ESCALA_PREPROCESSAMENTO = 2.0  # mesmo fx/fy usado em _preprocessar_para_ocr -- precisa pra converter bounding box de volta pra coordenada de tela real


def _sub_sequencia_correspondente(palavras: list, alvo: str):
    """Acha a MENOR sequência contígua de palavras (de uma mesma linha)
    cujo texto unido (minúsculo) contém `alvo` -- permite localizar uma
    frase de várias palavras (ex.: "clique aqui") sem devolver a linha
    inteira quando só um trecho dela bate."""
    n = len(palavras)
    for tamanho in range(1, n + 1):
        for inicio in range(0, n - tamanho + 1):
            janela = palavras[inicio:inicio + tamanho]
            texto_janela = " ".join(p["texto"] for p in janela).lower()
            if alvo in texto_janela:
                return janela
    return None


def localizar_texto_na_tela(texto_procurado: str, monitor_index: int = 1, lang: str = "por") -> list:
    """Procura `texto_procurado` (substring, sem diferenciar maiúsculas)
    na tela via OCR e devolve ONDE está, pronto pra clicar --
    `controle_pc.entrada.clicar(x, y)` -- em vez de só o texto puro que
    `read_screen_text()` devolve. Cada correspondência é
    {"texto", "x", "y", "confianca"}, x/y sendo o CENTRO do trecho
    encontrado em coordenadas ABSOLUTAS de tela (já somando o offset do
    monitor e desfazendo o upscale de `_preprocessar_para_ocr`), e a
    lista vem ordenada da maior pra menor confiança do OCR.

    Agrupa palavras por linha (block/par/line do Tesseract) antes de
    procurar, pra também achar frases de mais de uma palavra -- uma
    busca por só uma palavra funciona igual, é o caso trivial (janela
    de tamanho 1)."""
    if not HAS_OCR_LIBS:
        raise RuntimeError("Instale 'pytesseract' e 'Pillow' (e o binário Tesseract OCR) para OCR.")
    alvo = texto_procurado.strip().lower()
    if not alvo:
        return []

    import mss
    from visao.screen import screenshot

    frame = screenshot(monitor_index)
    processado = _preprocessar_para_ocr(frame)
    image = Image.fromarray(processado)
    dados = pytesseract.image_to_data(image, lang=_resolver_idioma(lang), output_type=pytesseract.Output.DICT)

    linhas = {}
    for i in range(len(dados["text"])):
        texto = dados["text"][i].strip()
        if not texto:
            continue
        try:
            conf = float(dados["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        chave = (dados["block_num"][i], dados["par_num"][i], dados["line_num"][i])
        linhas.setdefault(chave, []).append({
            "texto": texto, "left": dados["left"][i], "top": dados["top"][i],
            "width": dados["width"][i], "height": dados["height"][i], "conf": max(conf, 0.0),
        })

    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        offset_x, offset_y = monitor["left"], monitor["top"]

    encontrados = []
    for palavras in linhas.values():
        texto_linha = " ".join(p["texto"] for p in palavras).lower()
        if alvo not in texto_linha:
            continue
        sub = _sub_sequencia_correspondente(palavras, alvo)
        if not sub:
            continue
        esquerda = min(p["left"] for p in sub)
        direita = max(p["left"] + p["width"] for p in sub)
        topo = min(p["top"] for p in sub)
        base = max(p["top"] + p["height"] for p in sub)
        centro_x = int((esquerda + direita) / 2 / _ESCALA_PREPROCESSAMENTO) + offset_x
        centro_y = int((topo + base) / 2 / _ESCALA_PREPROCESSAMENTO) + offset_y
        encontrados.append({
            "texto": " ".join(p["texto"] for p in sub),
            "x": centro_x, "y": centro_y,
            "confianca": round(sum(p["conf"] for p in sub) / len(sub), 1),
        })

    encontrados.sort(key=lambda e: -e["confianca"])
    return encontrados
