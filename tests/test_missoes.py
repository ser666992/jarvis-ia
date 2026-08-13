from types import SimpleNamespace

from core.confidence import Answer, Confidence


class _Plugins:
    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.calls = []

    def dispatch(self, command, context):
        self.calls.append(command)
        answer = self.answers.pop(0) if self.answers else Answer("feito", Confidence.CONFIRMED)
        return "fake", answer


class _Jarvis:
    user_id = "mission-user"
    ia_manager = object()

    def __init__(self, plugins=None):
        self.plugins = plugins or _Plugins()

    def _context(self):
        return {"jarvis": self, "user_id": self.user_id}


def test_mission_persists_and_executes_safe_steps(monkeypatch):
    from automacao import missoes, modo_automatico
    monkeypatch.setattr(
        modo_automatico, "planejar",
        lambda *a: {"passos": ["abre o navegador", "tira um screenshot"], "recusa": None})
    jarvis = _Jarvis()
    mission = missoes.criar(jarvis, "preparar ambiente")
    result = missoes.executar_ate_parar(jarvis, mission["id"])
    assert result["missao"]["status"] == "concluida"
    assert jarvis.plugins.calls == ["abre o navegador", "tira um screenshot"]


def test_high_risk_step_waits_for_explicit_approval(monkeypatch):
    from automacao import missoes, modo_automatico
    monkeypatch.setattr(
        modo_automatico, "planejar",
        lambda *a: {"passos": ["enviar mensagem para alguém"], "recusa": None})
    jarvis = _Jarvis()
    mission = missoes.criar(jarvis, "responder contato")
    blocked = missoes.executar_proximo(jarvis, mission["id"])
    assert blocked["motivo"] == "aguardando aprovação"
    assert jarvis.plugins.calls == []
    missoes.aprovar_passo(jarvis.user_id, mission["id"], 1)
    assert missoes.executar_proximo(jarvis, mission["id"])["executado"] is True


def test_failed_step_retries_then_blocks(monkeypatch):
    from automacao import missoes, modo_automatico
    monkeypatch.setattr(
        modo_automatico, "planejar",
        lambda *a: {"passos": ["abre o navegador"], "recusa": None})
    plugins = _Plugins([
        Answer("falhou", Confidence.GUESS), Answer("falhou novamente", Confidence.GUESS)])
    jarvis = _Jarvis(plugins)
    mission = missoes.criar(jarvis, "abrir site")
    assert missoes.executar_proximo(jarvis, mission["id"])["executado"] is False
    missoes.executar_proximo(jarvis, mission["id"])
    assert missoes.obter(jarvis.user_id, mission["id"])["status"] == "bloqueada"


def test_recursion_is_never_executed(monkeypatch):
    from automacao import missoes, modo_automatico
    monkeypatch.setattr(
        modo_automatico, "planejar",
        lambda *a: {"passos": ["cria missão para abrir o site"], "recusa": None})
    jarvis = _Jarvis()
    mission = missoes.criar(jarvis, "loop")
    result = missoes.executar_proximo(jarvis, mission["id"])
    assert "Recursão" in result["motivo"]
    assert jarvis.plugins.calls == []
