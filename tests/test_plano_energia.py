"""
tests/test_plano_energia.py
==============================
"Modo economia de energia" / "modo desempenho máximo" (plugins/plano_energia.py
-> controle_pc/energia.py -> powercfg). Nenhum teste aqui chama
powercfg de verdade -- controle_pc.energia é substituído por um fake.
"""

import pytest

from plugins.plano_energia import PlanoEnergiaPlugin


class _FakeEnergia:
    def __init__(self, planos=None, disponivel=True, erro_ativar=None):
        self._planos = planos or [
            {"guid": "g-eco", "nome": "Economia de energia", "ativo": False},
            {"guid": "g-eq", "nome": "Equilibrado", "ativo": True},
            {"guid": "g-des", "nome": "Alto desempenho", "ativo": False},
        ]
        self._disponivel = disponivel
        self._erro_ativar = erro_ativar
        self.pedidos = []

    def available(self):
        return self._disponivel

    def plano_ativo(self):
        return next((p for p in self._planos if p["ativo"]), {})

    def ativar_plano(self, alvo):
        self.pedidos.append(alvo)
        if self._erro_ativar:
            raise self._erro_ativar
        for p in self._planos:
            p["ativo"] = False
        # heurística simples só pro teste: acha por substring no nome ou no apelido esperado
        mapa = {"economia de energia": "Economia de energia", "desempenho máximo": "Alto desempenho",
                "equilibrado": "Equilibrado", "alto desempenho": "Alto desempenho"}
        escolhido_nome = mapa.get(alvo.lower(), alvo)
        for p in self._planos:
            if p["nome"] == escolhido_nome:
                p["ativo"] = True
                return p
        raise ValueError(f'plano "{alvo}" não encontrado')


@pytest.fixture
def fake_energia(monkeypatch):
    import controle_pc.energia as energia_module
    fake = _FakeEnergia()
    monkeypatch.setattr(energia_module, "available", fake.available)
    monkeypatch.setattr(energia_module, "plano_ativo", fake.plano_ativo)
    monkeypatch.setattr(energia_module, "ativar_plano", fake.ativar_plano)
    return fake


def test_matches_frases_de_troca():
    plugin = PlanoEnergiaPlugin()
    assert plugin.matches("modo economia de energia")
    assert plugin.matches("modo desempenho máximo")
    assert plugin.matches("modo equilibrado")
    assert plugin.matches("qual o plano de energia atual")


def test_ativa_modo_economia_de_energia(fake_energia, contexto):
    plugin = PlanoEnergiaPlugin()

    resposta = plugin.handle("modo economia de energia", contexto)

    assert fake_energia.pedidos == ["economia de energia"]
    assert "Economia de energia" in resposta.text


def test_ativa_modo_desempenho_maximo(fake_energia, contexto):
    plugin = PlanoEnergiaPlugin()

    resposta = plugin.handle("modo desempenho máximo", contexto)

    assert fake_energia.pedidos == ["desempenho máximo"]
    assert "Alto desempenho" in resposta.text


def test_consulta_plano_atual(fake_energia, contexto):
    plugin = PlanoEnergiaPlugin()

    resposta = plugin.handle("qual o plano de energia atual", contexto)

    assert "Equilibrado" in resposta.text
    assert fake_energia.pedidos == []  # consulta não troca nada


def test_troca_generica_reconhece_apelido_dentro_da_frase(fake_energia, contexto):
    """"alto desempenho" bate direto no dicionário de apelidos
    (_FRASES_ATIVAR), então tem prioridade sobre o regex genérico de
    "troca...pra <nome>" -- ambos os caminhos levam ao plano certo."""
    plugin = PlanoEnergiaPlugin()

    resposta = plugin.handle("troca o plano de energia pra alto desempenho", contexto)

    assert fake_energia.pedidos == ["desempenho máximo"]
    assert "Alto desempenho" in resposta.text


def test_troca_generica_pra_nome_local_sem_apelido_conhecido(fake_energia, contexto):
    """Um nome de plano que não bate em nenhum apelido conhecido ainda
    precisa cair no regex genérico "troca...pra <nome>", pra suportar
    planos customizados/OEM que a pessoa nomeou como quiser."""
    plugin = PlanoEnergiaPlugin()

    plugin.handle("troca o plano de energia pra Equilibrado", contexto)

    assert fake_energia.pedidos == ["Equilibrado"]


def test_plano_nao_encontrado_nao_quebra(fake_energia, contexto):
    plugin = PlanoEnergiaPlugin()

    resposta = plugin.handle("troca o plano de energia pra modo turbo xyz", contexto)

    assert "não encontrei" in resposta.text.lower() or "não encontrado" in resposta.text.lower()


def test_fora_do_windows_avisa(monkeypatch, contexto):
    import controle_pc.energia as energia_module
    monkeypatch.setattr(energia_module, "available", lambda: False)
    plugin = PlanoEnergiaPlugin()

    resposta = plugin.handle("modo economia de energia", contexto)

    assert "Windows" in resposta.text
