"""
tests/test_clicar_texto.py
=============================
"Clica no texto ...": combina visao.ocr.localizar_texto_na_tela() com
controle_pc.entrada.clicar() -- clica em qualquer texto visível na
tela, não só em elementos com nome acessível (diferente de
plugins/controle_pc.py, que usa UI Automation por nome de elemento).

Cobertura importante: NÃO pode roubar os gatilhos genéricos "clica no
botão <nome>"/"clica em <nome>" que plugins/controle_pc.py já responde
-- só ativa com um marcador explícito ("texto" ou "na tela"), senão
colidiria (plugins são "primeiro que casar, ganha" por ordem alfabética
de arquivo, e "clicar_texto.py" vem antes de "controle_pc.py").

Nenhum teste aqui usa OCR/mouse de verdade -- tudo é fake.
"""

import pytest

from plugins.clicar_texto import ClicarTextoPlugin


class _FakeOCR:
    def __init__(self, encontrados=None, disponivel=True, erro=None):
        self._encontrados = encontrados if encontrados is not None else []
        self._disponivel = disponivel
        self._erro = erro
        self.chamadas = []

    def available(self):
        return self._disponivel

    def localizar_texto_na_tela(self, alvo, **kwargs):
        self.chamadas.append(alvo)
        if self._erro:
            raise self._erro
        return self._encontrados


class _FakeScreen:
    def __init__(self, disponivel=True):
        self._disponivel = disponivel

    def available(self):
        return self._disponivel


class _FakeEntrada:
    def __init__(self, disponivel=True):
        self._disponivel = disponivel
        self.cliques = []

    def available(self):
        return self._disponivel

    def clicar(self, x, y, botao="left", duplo=False):
        self.cliques.append((x, y, duplo))


def _preparar(monkeypatch, encontrados=None, ocr_disponivel=True, screen_disponivel=True, entrada_disponivel=True, erro=None):
    import visao.ocr as ocr_module
    import visao.screen as screen_module
    import controle_pc.entrada as entrada_module

    fake_ocr = _FakeOCR(encontrados=encontrados, disponivel=ocr_disponivel, erro=erro)
    fake_entrada = _FakeEntrada(disponivel=entrada_disponivel)
    monkeypatch.setattr(ocr_module, "available", fake_ocr.available)
    monkeypatch.setattr(ocr_module, "localizar_texto_na_tela", fake_ocr.localizar_texto_na_tela)
    monkeypatch.setattr(screen_module, "available", lambda: screen_disponivel)
    monkeypatch.setattr(entrada_module, "available", fake_entrada.available)
    monkeypatch.setattr(entrada_module, "clicar", fake_entrada.clicar)
    return fake_ocr, fake_entrada


# ---------- reconhecimento de comando (sem colisão com controle_pc.py) ----------

def test_matches_clica_no_texto():
    plugin = ClicarTextoPlugin()
    assert plugin.matches("clica no texto Salvar")
    assert plugin.matches("clica no texto que diz OK")
    assert plugin.matches("clica em Cancelar na tela")


def test_nao_confunde_com_clica_no_botao_generico():
    """Regressão real evitada: sem "texto"/"na tela" explícito, isto
    tem que ficar pro plugins/controle_pc.py (elemento por nome), não
    ser roubado por este plugin."""
    plugin = ClicarTextoPlugin()
    assert not plugin.matches("clica no botão Salvar")
    assert not plugin.matches("clica em Cancelar")


def test_controle_pc_ainda_responde_ao_clica_no_botao_generico():
    from plugins.controle_pc import ControlePCPlugin
    plugin = ControlePCPlugin()
    assert plugin.matches("clica no botão Salvar")
    assert plugin.matches("clica em Cancelar")


# ---------- handle() ----------

def test_clica_no_texto_encontrado(monkeypatch, contexto):
    _, fake_entrada = _preparar(monkeypatch, encontrados=[{"texto": "Salvar", "x": 100, "y": 200, "confianca": 92.0}])
    plugin = ClicarTextoPlugin()

    resposta = plugin.handle("clica no texto Salvar", contexto)

    assert fake_entrada.cliques == [(100, 200, False)]
    assert "Salvar" in resposta.text


def test_clica_duas_vezes(monkeypatch, contexto):
    _, fake_entrada = _preparar(monkeypatch, encontrados=[{"texto": "abrir arquivo", "x": 50, "y": 60, "confianca": 80.0}])
    plugin = ClicarTextoPlugin()

    plugin.handle("clica duas vezes no texto abrir arquivo", contexto)

    assert fake_entrada.cliques == [(50, 60, True)]


def test_texto_nao_encontrado_nao_clica(monkeypatch, contexto):
    _, fake_entrada = _preparar(monkeypatch, encontrados=[])
    plugin = ClicarTextoPlugin()

    resposta = plugin.handle("clica no texto Inexistente", contexto)

    assert fake_entrada.cliques == []
    assert "não encontrei" in resposta.text.lower()


def test_escolhe_a_correspondencia_de_maior_confianca(monkeypatch, contexto):
    # localizar_texto_na_tela já devolve ordenado por confiança -- o
    # plugin deve usar sempre a PRIMEIRA da lista.
    _, fake_entrada = _preparar(monkeypatch, encontrados=[
        {"texto": "OK", "x": 10, "y": 10, "confianca": 95.0},
        {"texto": "OK", "x": 500, "y": 500, "confianca": 60.0},
    ])
    plugin = ClicarTextoPlugin()

    plugin.handle("clica no texto OK", contexto)

    assert fake_entrada.cliques == [(10, 10, False)]


def test_ocr_indisponivel_avisa_sem_quebrar(monkeypatch, contexto):
    _preparar(monkeypatch, ocr_disponivel=False)
    plugin = ClicarTextoPlugin()

    resposta = plugin.handle("clica no texto Salvar", contexto)

    assert "OCR" in resposta.text


def test_erro_ao_ler_tela_nao_quebra(monkeypatch, contexto):
    _preparar(monkeypatch, erro=RuntimeError("tela bloqueada"))
    plugin = ClicarTextoPlugin()

    resposta = plugin.handle("clica no texto Salvar", contexto)

    assert "tela bloqueada" in resposta.text
