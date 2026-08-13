"""
tests/test_ocr_localizar.py
==============================
`visao.ocr.localizar_texto_na_tela()`: base de "clica no texto ..."
(plugins/clicar_texto.py) -- diferente de read_screen_text() (só o
texto corrido), esta função devolve TAMBÉM a posição de cada trecho
encontrado, em coordenadas absolutas de tela, prontas pra
controle_pc.entrada.clicar(x, y). Cobre: palavra única, frase de várias
palavras, ordenação por confiança, offset de monitor, e quando OCR
está indisponível.

Nenhum teste aqui roda o Tesseract de verdade -- pytesseract e a
captura de tela são substituídos por fakes.
"""

import numpy as np
import pytest

import visao.ocr as ocr


def _dados_ocr(palavras):
    """Monta um dict no formato de pytesseract.image_to_data(output_type=DICT)
    a partir de uma lista de (texto, left, top, width, height, conf, block, par, line)."""
    dados = {k: [] for k in ("text", "left", "top", "width", "height", "conf", "block_num", "par_num", "line_num")}
    for texto, left, top, width, height, conf, block, par, line in palavras:
        dados["text"].append(texto)
        dados["left"].append(left)
        dados["top"].append(top)
        dados["width"].append(width)
        dados["height"].append(height)
        dados["conf"].append(conf)
        dados["block_num"].append(block)
        dados["par_num"].append(par)
        dados["line_num"].append(line)
    return dados


class _FakeMonitorCtx:
    def __init__(self, monitores):
        self._monitores = monitores

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def monitors(self):
        return self._monitores


@pytest.fixture(autouse=True)
def _preprocessamento_identidade(monkeypatch):
    # bypassa o cv2 de verdade (upscale/binarização) -- irrelevante pro
    # que este teste cobre (a lógica de busca/coordenada), e evita
    # depender dos detalhes exatos do pré-processamento.
    monkeypatch.setattr(ocr, "_preprocessar_para_ocr", lambda frame: frame)
    monkeypatch.setattr(ocr, "HAS_OCR_LIBS", True)


def _preparar(monkeypatch, palavras, monitores=None, offset=(0, 0)):
    import mss as mss_module
    import visao.screen as screen_module

    monkeypatch.setattr(screen_module, "screenshot", lambda monitor_index=1: np.zeros((10, 10), dtype=np.uint8))
    monkeypatch.setattr(ocr.pytesseract, "image_to_data", lambda *a, **k: _dados_ocr(palavras))
    monitores = monitores or [{}, {"left": offset[0], "top": offset[1], "width": 1920, "height": 1080}]
    monkeypatch.setattr(mss_module, "mss", lambda: _FakeMonitorCtx(monitores))


def test_encontra_palavra_unica(monkeypatch):
    _preparar(monkeypatch, [
        ("Salvar", 100, 200, 60, 20, "95", 1, 1, 1),
    ])

    encontrados = ocr.localizar_texto_na_tela("salvar")

    assert len(encontrados) == 1
    assert encontrados[0]["texto"] == "Salvar"
    # centro em coordenada de tela real = bounding box / escala (2.0) + offset (0 aqui)
    assert encontrados[0]["x"] == int((100 + 160) / 2 / 2)
    assert encontrados[0]["y"] == int((200 + 220) / 2 / 2)


def test_encontra_frase_de_varias_palavras(monkeypatch):
    _preparar(monkeypatch, [
        ("Clique", 0, 0, 40, 10, "90", 1, 1, 1),
        ("aqui", 50, 0, 20, 10, "88", 1, 1, 1),
        ("agora", 80, 0, 25, 10, "80", 1, 1, 1),  # mesma linha, fora da frase buscada
    ])

    encontrados = ocr.localizar_texto_na_tela("clique aqui")

    assert len(encontrados) == 1
    assert encontrados[0]["texto"] == "Clique aqui"
    # bounding box da UNIÃO de "Clique"+"aqui" só (não inclui "agora")
    assert encontrados[0]["x"] == int((0 + 70) / 2 / 2)


def test_nao_encontra_retorna_lista_vazia(monkeypatch):
    _preparar(monkeypatch, [("Cancelar", 0, 0, 50, 10, "90", 1, 1, 1)])

    assert ocr.localizar_texto_na_tela("salvar") == []


def test_ordena_por_confianca_decrescente(monkeypatch):
    _preparar(monkeypatch, [
        ("OK", 0, 0, 20, 10, "60", 1, 1, 1),
        ("OK", 0, 50, 20, 10, "95", 2, 1, 1),
    ])

    encontrados = ocr.localizar_texto_na_tela("ok")

    assert len(encontrados) == 2
    assert encontrados[0]["confianca"] > encontrados[1]["confianca"]
    assert encontrados[0]["confianca"] == 95.0


def test_aplica_offset_do_monitor(monkeypatch):
    _preparar(monkeypatch, [("Salvar", 100, 200, 60, 20, "95", 1, 1, 1)], offset=(1920, 0))

    encontrados = ocr.localizar_texto_na_tela("salvar")

    assert encontrados[0]["x"] == int((100 + 160) / 2 / 2) + 1920


def test_ignora_palavras_com_confianca_negativa(monkeypatch):
    # tesseract usa conf=-1 pra "não é uma palavra de verdade" (ex.: linha em branco)
    _preparar(monkeypatch, [("Salvar", 0, 0, 60, 20, "-1", 1, 1, 1)])

    encontrados = ocr.localizar_texto_na_tela("salvar")

    assert len(encontrados) == 1
    assert encontrados[0]["confianca"] == 0.0  # conf negativa é tratada como 0, não descarta a palavra


def test_texto_vazio_nao_busca_nada(monkeypatch):
    _preparar(monkeypatch, [("Salvar", 0, 0, 60, 20, "95", 1, 1, 1)])

    assert ocr.localizar_texto_na_tela("   ") == []


def test_sem_ocr_disponivel_levanta_erro(monkeypatch):
    monkeypatch.setattr(ocr, "HAS_OCR_LIBS", False)

    with pytest.raises(RuntimeError):
        ocr.localizar_texto_na_tela("salvar")
