"""
tests/test_plugins_jogos.py
==============================
Comandos de chat do "Aprendiz de jogos" (plugins/jogos.py). Toda
função de jogos/ é substituída por fake -- estes testes cobrem
reconhecimento de frase, mensagens de resposta, o aviso de ToS do
Roblox, o gate de confirmação em "esquece..." e (o mais importante,
dada a história deste projeto com colisão de plugins) que os
comandos daqui NUNCA são roubados por plugins/skill_forge.py nem
plugins/autonomia.py, e vice-versa.
"""

import jogos
import pytest

from plugins.jogos import JogosPlugin


@pytest.fixture
def plugin():
    return JogosPlugin()


# ---------- reconhecimento de frase ----------

def test_matches_frases_principais(plugin):
    assert plugin.matches("aprende a jogar F1")
    assert plugin.matches("vou te ensinar a jogar Roblox")
    assert plugin.matches("para de gravar")
    assert plugin.matches("joga F1 sozinho")
    assert plugin.matches("joga roblox agora")
    assert plugin.matches("para de jogar")
    assert plugin.matches("melhora o que você aprendeu sobre F1")
    assert plugin.matches("como você está indo no F1")
    assert plugin.matches("esquece o que você aprendeu sobre F1")


def test_feedback_so_reconhecido_com_jogo_ativo(plugin, monkeypatch):
    monkeypatch.setattr(jogos, "jogo_ativo", lambda: False)
    assert not plugin.matches("isso foi bom")
    assert not plugin.matches("isso foi ruim")

    monkeypatch.setattr(jogos, "jogo_ativo", lambda: True)
    assert plugin.matches("isso foi bom")
    assert plugin.matches("isso foi ruim")


# ---------- sem colisão com skill_forge/autonomia (via despacho real) ----------

def test_nao_colide_com_skill_forge_nem_autonomia():
    from core.plugin_manager import PluginManager
    pm = PluginManager("plugins")

    casos = [
        ("aprende a jogar F1", "jogos"),
        ("vou te ensinar a jogar Roblox", "jogos"),
        ("joga F1 sozinho", "jogos"),
        ("cria um jogo sobre gatos", "skill_forge"),
        ("aprende algo novo", "autonomia"),
        ("aprenda algo sozinho", "autonomia"),
    ]
    for frase, esperado in casos:
        vencedor = next((p.name for p in pm.plugins if p.matches(frase)), None)
        assert vencedor == esperado, f"{frase!r} foi pro plugin {vencedor!r}, esperava {esperado!r}"


# ---------- aprender/gravar ----------

def test_iniciar_gravacao_sucesso(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "iniciar_gravacao", lambda nome: {"nome_jogo": nome, "duracao_minutos": 15.0})
    resposta = plugin.handle("aprende a jogar F1", contexto)
    assert "F1" in resposta.text
    assert "para de gravar" in resposta.text.lower()


def test_iniciar_gravacao_erro_vira_resposta_amigavel(plugin, monkeypatch, contexto):
    def _levanta(nome):
        raise RuntimeError("Instale 'pynput'.")
    monkeypatch.setattr(jogos, "iniciar_gravacao", _levanta)
    resposta = plugin.handle("aprende a jogar F1", contexto)
    assert "pynput" in resposta.text


def test_parar_gravacao_sem_sessao_ativa(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "parar_gravacao", lambda: {"parou": False, "n_quadros": 0, "caminho": "", "nome_jogo": ""})
    resposta = plugin.handle("para de gravar", contexto)
    assert "não havia" in resposta.text.lower()


def test_parar_gravacao_sem_quadros(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "parar_gravacao", lambda: {"parou": True, "n_quadros": 0, "caminho": "", "nome_jogo": "f1"})
    resposta = plugin.handle("para de gravar", contexto)
    assert "nenhum quadro" in resposta.text.lower()


def test_parar_gravacao_treina_e_reporta(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "parar_gravacao", lambda: {
        "parou": True, "n_quadros": 120, "caminho": "x.npz", "nome_jogo": "f1",
    })
    monkeypatch.setattr(jogos, "treinar_por_imitacao", lambda nome: {"n_amostras": 120, "epocas": 10, "perda_final": 0.5})
    resposta = plugin.handle("para de gravar", contexto)
    assert "120" in resposta.text
    assert "joga f1 sozinho" in resposta.text.lower()


def test_parar_gravacao_falha_ao_treinar(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "parar_gravacao", lambda: {
        "parou": True, "n_quadros": 5, "caminho": "x.npz", "nome_jogo": "f1",
    })
    def _levanta(nome):
        raise RuntimeError("Instale 'torch'.")
    monkeypatch.setattr(jogos, "treinar_por_imitacao", _levanta)
    resposta = plugin.handle("para de gravar", contexto)
    assert "torch" in resposta.text


# ---------- jogar sozinho ----------

def test_jogar_sozinho_sucesso(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "iniciar_jogo_sozinho", lambda nome: {"nome_jogo": nome, "duracao_minutos": 20.0})
    resposta = plugin.handle("joga F1 sozinho", contexto)
    assert "F1" in resposta.text
    assert "roblox" not in resposta.text.lower()


def test_jogar_sozinho_roblox_inclui_aviso_de_tos(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "iniciar_jogo_sozinho", lambda nome: {"nome_jogo": nome, "duracao_minutos": 20.0})
    resposta = plugin.handle("joga roblox sozinho", contexto)
    assert "termos de serviço" in resposta.text.lower()
    assert "banimento" in resposta.text.lower()


def test_jogar_sozinho_sem_politica_treinada(plugin, monkeypatch, contexto):
    def _levanta(nome):
        raise RuntimeError(f'Ainda não tenho uma política treinada pra "{nome}".')
    monkeypatch.setattr(jogos, "iniciar_jogo_sozinho", _levanta)
    resposta = plugin.handle("joga F1 sozinho", contexto)
    assert "política treinada" in resposta.text


def test_parar_jogo(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "parar_jogo", lambda: {"parou": True, "n_quadros": 300, "n_episodios": 4, "caminho": "x.npz"})
    resposta = plugin.handle("para de jogar", contexto)
    assert "300" in resposta.text and "4" in resposta.text


# ---------- feedback ----------

def test_feedback_bom_chama_registrar_feedback(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "jogo_ativo", lambda: True)
    chamadas = []
    monkeypatch.setattr(jogos, "registrar_feedback", lambda bom: chamadas.append(bom))
    resposta = plugin.handle("isso foi bom", contexto)
    assert chamadas == [True]
    assert "anotado" in resposta.text.lower()


def test_feedback_ruim_chama_registrar_feedback(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "jogo_ativo", lambda: True)
    chamadas = []
    monkeypatch.setattr(jogos, "registrar_feedback", lambda bom: chamadas.append(bom))
    resposta = plugin.handle("isso foi ruim", contexto)
    assert chamadas == [False]


# ---------- melhorar / status / esquecer ----------

def test_melhorar_sucesso(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "retreinar_com_sessoes", lambda nome: {"n_amostras": 200, "epocas": 5, "perda_final": 0.3})
    resposta = plugin.handle("melhora o que você aprendeu sobre F1", contexto)
    assert "F1" in resposta.text
    assert "200" in resposta.text


def test_status_sem_dados(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "status", lambda nome: {
        "n_demonstracoes": 0, "n_sessoes": 0, "duracao_media_episodio_quadros": None,
        "tendencia": None, "tem_politica_treinada": False,
    })
    resposta = plugin.handle("como você está indo no F1", contexto)
    assert "ainda não sei nada" in resposta.text.lower()


def test_status_com_dados_mostra_tendencia(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "status", lambda nome: {
        "n_demonstracoes": 2, "n_sessoes": 5, "duracao_media_episodio_quadros": 42.0,
        "tendencia": "melhorando", "tem_politica_treinada": True,
    })
    resposta = plugin.handle("como você está indo no F1", contexto)
    assert "melhorando" in resposta.text
    assert "42.0" in resposta.text


def test_esquecer_sem_confirmar_pede_confirmacao(plugin, monkeypatch, contexto):
    from config.settings import get_settings
    get_settings().set("seguranca.exigir_confirmacao_acoes_destrutivas", True)
    apagou_chamado = []
    monkeypatch.setattr(jogos, "apagar_jogo", lambda nome: apagou_chamado.append(nome) or True)

    resposta = plugin.handle("esquece o que você aprendeu sobre F1", contexto)

    assert apagou_chamado == []  # não apagou sem confirmação
    assert "bloqueada" in resposta.text.lower() or "confirm" in resposta.text.lower()


def test_esquecer_com_confirmo_apaga(plugin, monkeypatch, contexto):
    from config.settings import get_settings
    get_settings().set("seguranca.exigir_confirmacao_acoes_destrutivas", True)
    monkeypatch.setattr(jogos, "apagar_jogo", lambda nome: True)

    resposta = plugin.handle("esquece o que você aprendeu sobre F1, confirmo", contexto)

    assert "esqueci" in resposta.text.lower()


def test_esquecer_nada_pra_apagar(plugin, monkeypatch, contexto):
    monkeypatch.setattr(jogos, "apagar_jogo", lambda nome: False)
    resposta = plugin.handle("esquece o que você aprendeu sobre F1, confirmo", contexto)
    assert "não tinha nada" in resposta.text.lower()
