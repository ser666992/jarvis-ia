"""Regressões do encadeamento Wikipedia -> IA -> internet."""

from core.confidence import Answer, Confidence
from plugins.knowledge_search import KnowledgeSearchPlugin


def test_wikipedia_sem_resultado_deixa_proximos_estagios_rodarem(monkeypatch):
    class _Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"{}"

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _Resposta())
    plugin = KnowledgeSearchPlugin()
    assert plugin.handle("o que é um tema muito específico", {}) is None


def test_wikipedia_offline_deixa_proximos_estagios_rodarem(monkeypatch):
    def _falha(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr("urllib.request.urlopen", _falha)
    plugin = KnowledgeSearchPlugin()
    assert plugin.handle("quem é uma pessoa desconhecida", {}) is None


def test_nucleo_tenta_internet_antes_do_fallback(monkeypatch):
    from core.jarvis import Jarvis
    from automacao import navegador

    jarvis = Jarvis.__new__(Jarvis)
    jarvis.ia_manager = None
    jarvis.log = None
    monkeypatch.setattr(navegador, "available", lambda: True)
    monkeypatch.setattr(
        navegador,
        "pesquisar_e_resumir",
        lambda ia, consulta: "Resposta encontrada em https://exemplo.test",
    )

    resposta = jarvis._query_internet("qual é a resposta?")
    assert isinstance(resposta, Answer)
    assert resposta.confidence == Confidence.SINGLE_SOURCE
