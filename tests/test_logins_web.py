"""
tests/test_logins_web.py
===========================
Login automático em sites (automacao/logins_web.py + plugins/logins_web.py
+ gui/app.py). A regra mais importante do módulo inteiro -- e a que
mais importa continuar testada -- é a de segurança: uma senha digitada
ou falada no chat NUNCA pode ser aceita/processada, porque
`Jarvis.process()` grava toda mensagem no histórico de conversa antes
de qualquer plugin rodar (ver docstring de plugins/logins_web.py).

`keyring` é sempre trocado por um fake em memória (`_FakeKeyring`) --
sem isso, os testes escreveriam de verdade no cofre de credenciais do
Windows (Credential Locker) com o serviço "jarvis_login".
"""

import pytest

from plugins.logins_web import LoginsWebPlugin, SAVE_INTENT_RE


class _FakeKeyring:
    """Substitui `keyring` em memória -- ver aviso no topo do arquivo."""

    def __init__(self):
        self._store = {}

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def get_password(self, service, username):
        return self._store.get((service, username))

    def delete_password(self, service, username):
        chave = (service, username)
        if chave not in self._store:
            raise Exception("senha não encontrada no keyring falso")
        del self._store[chave]


@pytest.fixture
def keyring_falso(monkeypatch):
    from automacao import logins_web
    fake = _FakeKeyring()
    monkeypatch.setattr(logins_web, "keyring", fake)
    monkeypatch.setattr(logins_web, "HAS_KEYRING", True)
    return fake


# ---------- segurança: senha no chat nunca é aceita ----------

@pytest.mark.parametrize("texto", [
    "salva o login do github, usuario fulano, senha 123456",
    "salva o login do github",
    "guarda esse login: site amazon senha abc123",
    "cadastra o login da netflix",
    "novo login",
    "login e senha do spotify",
])
def test_intencao_de_salvar_login_e_detectada(texto):
    assert SAVE_INTENT_RE.search(texto), f"deveria ter detectado intenção de salvar em: {texto!r}"


def test_plugin_recusa_salvar_login_pelo_chat(monkeypatch, contexto):
    """Mesmo com usuário/senha na própria mensagem, o plugin nunca deve
    chamar salvar_login() -- só deve devolver a recusa explicando o
    caminho seguro (comando na GUI ou CLI)."""
    from automacao import logins_web

    chamado = {"sim": False}

    def _nao_deveria_ser_chamado(*a, **k):
        chamado["sim"] = True
        raise AssertionError("salvar_login() foi chamado a partir do texto do chat -- vazamento de segurança")

    monkeypatch.setattr(logins_web, "salvar_login", _nao_deveria_ser_chamado)

    plugin = LoginsWebPlugin()
    texto = "salva o login do github, usuario fulano, senha SuperSecreta123"
    assert plugin.matches(texto)
    resposta = plugin.handle(texto, contexto)

    assert not chamado["sim"]
    assert "não guardo login/senha digitados no chat" in resposta.text
    assert "SuperSecreta123" not in resposta.text


def test_plugin_nao_ecoa_senha_recebida_no_texto(contexto):
    """Ainda que alguém escreva a senha na mensagem, ela nunca deve
    aparecer de volta na resposta do plugin (nem por engano, ex.: um
    regex genérico que devolvesse parte do texto original)."""
    plugin = LoginsWebPlugin()
    resposta = plugin.handle("salva o login do gmail com a senha Abacate123!", contexto)
    assert "Abacate123" not in resposta.text


# ---------- fluxo normal: salvar (via caminho seguro) / listar / logar / remover ----------

def test_salvar_e_listar_login(keyring_falso, contexto):
    from automacao import logins_web

    # Simula o caminho seguro (diálogo da GUI / CLI) chamando
    # salvar_login() DIRETO -- nunca através do texto do chat.
    logins_web.salvar_login("github", "https://github.com/login", "fulano", "senha-real-123")

    plugin = LoginsWebPlugin()
    resposta = plugin.handle("logins salvos", contexto)
    assert "github" in resposta.text
    assert "fulano" in resposta.text
    # a senha em si nunca deve aparecer em nenhuma listagem
    assert "senha-real-123" not in resposta.text

    # a senha só existe no keyring (falso), nunca no banco
    salvo = logins_web.listar_login("github")
    assert salvo["site"] == "github"
    assert keyring_falso.get_password("jarvis_login", "github") == "senha-real-123"


def test_logar_sem_login_salvo_da_erro_amigavel(keyring_falso, contexto):
    plugin = LoginsWebPlugin()
    resposta = plugin.handle("loga no siteinexistente123", contexto)
    assert "não tenho nenhum login salvo" in resposta.text.lower()


def test_remover_login(keyring_falso, contexto):
    from automacao import logins_web

    logins_web.salvar_login("netflix", "https://netflix.com/login", "user", "abc123")
    assert logins_web.listar_login("netflix") is not None

    plugin = LoginsWebPlugin()
    resposta = plugin.handle("remove o login do netflix", contexto)
    assert "removi" in resposta.text.lower()
    assert logins_web.listar_login("netflix") is None
    # o segredo também precisa sumir do keyring, não só do banco
    assert keyring_falso.get_password("jarvis_login", "netflix") is None


def test_remover_login_inexistente(keyring_falso, contexto):
    plugin = LoginsWebPlugin()
    resposta = plugin.handle("remove o login do siteinexistente123", contexto)
    assert "não achei" in resposta.text.lower()


# ---------- interceptação no lado da GUI (gui/app.py) ----------

def test_gui_intercepta_comando_de_salvar_e_extrai_site():
    """gui/app.py precisa reconhecer a MESMA intenção do plugin (senão
    o comando "escaparia" pro chat normal, que recusa) e extrair o nome
    do site pra pré-preencher o diálogo -- ver gui/app.py:_on_send()."""
    from gui.app import SAVE_INTENT_RE as gui_save_re
    from gui.app import _SAVE_LOGIN_SITE_RE

    assert gui_save_re.search("salva o login do github")

    m = _SAVE_LOGIN_SITE_RE.search("salva o login do github")
    assert m and m.group(1).strip() == "github"

    # sem site explícito na frase -- não deve inventar um
    assert _SAVE_LOGIN_SITE_RE.search("novo login") is None
