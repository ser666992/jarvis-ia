"""
tests/test_modo_autonomo.py
==============================
Modo Autônomo (automacao/modo_autonomo.py + plugins/modo_autonomo.py).
Cobre o CRUD de objetivos, o comando de chat que liga/desliga o
interruptor, e o "gate" de disparo automático (_tick): nunca deve
chamar a IA/executar nada se o modo estiver desligado, ou se o PC não
estiver ocioso -- essas duas checagens vêm ANTES de qualquer chamada
cara, então dá pra testar sem precisar de um provedor de IA de verdade.
"""

from config.settings import get_settings
from plugins.modo_autonomo import ModoAutonomoPlugin


def test_nao_colide_com_modo_automatico_sem_acento(contexto):
    """Bug real encontrado em auditoria: plugins/modo_automatico.py
    tinha uma regex corrigida (_TRIGGER_RE, com \\b) especificamente
    pra não bater como prefixo de "modo autonomo" -- mas essa regex só
    era usada dentro de handle(), nunca em matches() (que caía no
    matches() padrão de BasePlugin, substring simples em `triggers`,
    onde "modo auto" bate como prefixo de "modo autonomo" sem acento).
    Resultado: "ativa o modo autonomo" (sem acento -- comum em fala
    transcrita/teclado sem acento) era sequestrado por modo_automatico
    em vez de chegar em modo_autonomo. Ver plugins/modo_automatico.py:matches()."""
    from core.plugin_manager import PluginManager
    pm = PluginManager("plugins")

    for frase in ("ativa o modo autonomo", "liga o modo autonomo", "ativa o modo autônomo"):
        vencedor = next((p.name for p in pm.plugins if p.matches(frase)), None)
        assert vencedor == "modo_autonomo", f"{frase!r} foi pro plugin {vencedor!r}, esperava modo_autonomo"

    for frase in ("ativa auto: abre o spotify", "modo auto: abre o discord e o vscode"):
        vencedor = next((p.name for p in pm.plugins if p.matches(frase)), None)
        assert vencedor == "modo_automatico", f"{frase!r} foi pro plugin {vencedor!r}, esperava modo_automatico"


def test_ativar_e_desativar_modo_autonomo(contexto):
    plugin = ModoAutonomoPlugin()

    resposta = plugin.handle("ativa o modo autônomo", contexto)
    assert "ativado" in resposta.text.lower()
    assert get_settings().get("personalidade.modo_autonomo") is True

    resposta = plugin.handle("desativa o modo autônomo", contexto)
    assert "desativado" in resposta.text.lower()
    assert get_settings().get("personalidade.modo_autonomo") is False


def test_cadastrar_listar_e_remover_objetivo(contexto):
    plugin = ModoAutonomoPlugin()

    resposta = plugin.handle("novo objetivo autônomo: organiza meus arquivos de downloads", contexto)
    assert "Cadastrado" in resposta.text
    assert "organiza meus arquivos de downloads" in resposta.text

    resposta = plugin.handle("meus objetivos autônomos", contexto)
    assert "organiza meus arquivos de downloads" in resposta.text

    from automacao import modo_autonomo
    pendentes = modo_autonomo.listar_objetivos(contexto["user_id"])
    assert len(pendentes) == 1
    objetivo_id = pendentes[0]["id"]

    resposta = plugin.handle(f"remove o objetivo autônomo {objetivo_id}", contexto)
    assert "Removi" in resposta.text
    assert modo_autonomo.listar_objetivos(contexto["user_id"]) == []


def test_cadastrar_objetivo_vazio_pede_esclarecimento(contexto):
    plugin = ModoAutonomoPlugin()
    resposta = plugin.handle("novo objetivo autônomo:", contexto)
    assert "qual" in resposta.text.lower()


def test_cadastrar_objetivo_so_com_dois_pontos_e_espaco(contexto):
    """Mesmo caso do teste acima, mas com espaço em branco depois dos
    dois-pontos -- nesse caso o regex principal (que exige capturar
    algo em `(.+)`) nem chega a bater, então precisa do fallback de
    "gatilho vazio" pra não cair silenciosamente na conversa/IA."""
    plugin = ModoAutonomoPlugin()
    assert plugin.matches("novo objetivo autônomo:   ")
    resposta = plugin.handle("novo objetivo autônomo:   ", contexto)
    assert "qual" in resposta.text.lower()


def test_objetivos_sao_isolados_por_usuario(contexto):
    """Um objetivo cadastrado por um usuário não pode aparecer pra
    outro -- básico de privacidade em máquina compartilhada."""
    from automacao import modo_autonomo

    modo_autonomo.adicionar_objetivo("alice", "tarefa da alice")
    modo_autonomo.adicionar_objetivo("bob", "tarefa do bob")

    assert [o["objetivo"] for o in modo_autonomo.listar_objetivos("alice")] == ["tarefa da alice"]
    assert [o["objetivo"] for o in modo_autonomo.listar_objetivos("bob")] == ["tarefa do bob"]


# ---------- _tick: nunca deve chamar a IA fora das condições certas ----------

class _JarvisFalso:
    """Stub mínimo -- só o que automacao.modo_autonomo._tick() precisa
    ler. Se o teste chegar a precisar de mais que isso, é sinal de que
    _tick() tentou ir além do gate (bug)."""

    def __init__(self, user_id="usuario_teste"):
        self.user_id = user_id
        self.settings = get_settings()
        self.ia_manager = None  # se _tick() tentar usar isso sem checar antes, estoura AttributeError


def test_tick_nao_faz_nada_com_modo_desligado(monkeypatch):
    from automacao import modo_autonomo

    get_settings().set("personalidade.modo_autonomo", False)
    modo_autonomo.adicionar_objetivo("usuario_teste", "algo")

    chamou_ocioso = {"sim": False}
    monkeypatch.setattr(
        "sistema.ociosidade.esta_ocioso",
        lambda *_a, **_k: chamou_ocioso.__setitem__("sim", True) or True,
    )

    modo_autonomo._tick(_JarvisFalso())

    assert not chamou_ocioso["sim"], "checou ociosidade mesmo com o modo autônomo desligado -- deveria ter parado antes"
    assert len(modo_autonomo.listar_objetivos("usuario_teste")) == 1  # nada foi executado


def test_tick_nao_executa_se_pc_nao_esta_ocioso(monkeypatch):
    from automacao import modo_autonomo

    get_settings().set("personalidade.modo_autonomo", True)
    modo_autonomo.adicionar_objetivo("usuario_teste", "algo")

    monkeypatch.setattr("sistema.ociosidade.esta_ocioso", lambda *_a, **_k: False)

    def _nao_deveria_executar(*_a, **_k):
        raise AssertionError("executar_proximo_objetivo() foi chamado com o PC em uso -- gate de ociosidade furou")

    monkeypatch.setattr(modo_autonomo, "executar_proximo_objetivo", _nao_deveria_executar)

    modo_autonomo._tick(_JarvisFalso())
    assert len(modo_autonomo.listar_objetivos("usuario_teste")) == 1


def test_tick_nao_executa_sem_objetivo_pendente(monkeypatch):
    from automacao import modo_autonomo

    get_settings().set("personalidade.modo_autonomo", True)
    monkeypatch.setattr("sistema.ociosidade.esta_ocioso", lambda *_a, **_k: True)

    def _nao_deveria_executar(*_a, **_k):
        raise AssertionError("executar_proximo_objetivo() foi chamado sem nenhum objetivo pendente")

    monkeypatch.setattr(modo_autonomo, "executar_proximo_objetivo", _nao_deveria_executar)

    modo_autonomo._tick(_JarvisFalso())  # não deve levantar
