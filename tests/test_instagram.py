"""
tests/test_instagram.py
===========================
Regressão real corrigida numa sessão de manutenção: o envio automático
de respostas (automacao/instagram_auto.py:_tick) lia mensagens SÓ do
inbox em memória alimentado pelo app do celular -- quando o app foi
removido do projeto, esse inbox nunca mais era populado, e o ciclo
automático ficava rodando pra sempre sem achar nada, SILENCIOSAMENTE
(sem erro nenhum). Estes testes travam esse comportamento: com o app
fora de cena, tem que cair pro ADB sem fio -- exatamente como
plugins/instagram.py ("minhas mensagens do instagram") já fazia.

`dispositivos.adb` é sempre trocado por um fake -- nenhum teste aqui
deve tentar rodar o binário `adb` de verdade nem esperar um celular
conectado.
"""

import pytest


@pytest.fixture
def adb_falso(monkeypatch):
    """Substitui dispositivos.adb -- ver aviso no topo do arquivo."""
    from automacao import instagram_auto
    from plugins import instagram as instagram_plugin

    estado = {"disponivel": False, "dispositivos": [], "notificacoes": []}

    class _ADBFalso:
        def available(self):
            return estado["disponivel"]

        def list_devices(self):
            return estado["dispositivos"]

        def list_notifications(self, package=None):
            return estado["notificacoes"]

    fake = _ADBFalso()
    monkeypatch.setattr(instagram_auto, "adb", fake)
    monkeypatch.setattr(instagram_plugin, "adb", fake)
    return estado


def test_sem_inbox_e_sem_adb_nao_acha_nada(adb_falso):
    """O caso que quebrou de verdade: app removido (inbox sempre
    vazio) e celular não pareado por ADB -- não pode dar erro, só
    reportar "nada encontrado"."""
    from automacao import instagram_auto
    assert instagram_auto._mensagens_pendentes() == []


def test_cai_pro_adb_quando_inbox_esta_vazio(adb_falso):
    """O fallback que faltava: com o inbox vazio (sempre, já que o app
    foi removido) mas um celular pareado por ADB, as notificações
    precisam continuar aparecendo."""
    from automacao import instagram_auto

    adb_falso["disponivel"] = True
    adb_falso["dispositivos"] = ["192.168.0.10:5555"]
    adb_falso["notificacoes"] = [
        {"pacote": "com.instagram.android", "titulo": "amigo_teste", "texto": "oi, tudo bem?"},
    ]

    mensagens = instagram_auto._mensagens_pendentes()
    assert len(mensagens) == 1
    assert mensagens[0]["texto"] == "oi, tudo bem?"


def test_nao_tenta_adb_sem_dispositivo_conectado(adb_falso):
    """ADB "disponível" (binário instalado) mas sem nenhum celular
    pareado ainda -- não deve levantar tentando listar notificações de
    um dispositivo que não existe."""
    from automacao import instagram_auto

    adb_falso["disponivel"] = True
    adb_falso["dispositivos"] = []  # binário existe, ninguém pareado

    assert instagram_auto._mensagens_pendentes() == []


def test_inbox_tem_prioridade_sobre_adb(adb_falso, monkeypatch):
    """Se um dia o inbox voltar a ser alimentado por alguma outra via,
    ele continua tendo prioridade sobre o ADB (captura nativa é mais
    confiável que o parsing de dumpsys)."""
    from automacao import instagram_auto
    from automacao.notification_inbox import registrar

    adb_falso["disponivel"] = True
    adb_falso["dispositivos"] = ["192.168.0.10:5555"]
    adb_falso["notificacoes"] = [
        {"pacote": "com.instagram.android", "titulo": "via_adb", "texto": "mensagem via adb"},
    ]
    registrar("com.instagram.android", "via_inbox", "mensagem via inbox")

    mensagens = instagram_auto._mensagens_pendentes()
    assert len(mensagens) == 1
    assert mensagens[0]["titulo"] == "via_inbox"


def test_plugin_instagram_usa_o_mesmo_fallback(adb_falso):
    """plugins/instagram.py ("minhas mensagens do instagram") e
    automacao/instagram_auto.py (envio automático) não podem voltar a
    divergir sobre de onde vêm as mensagens -- foi exatamente essa
    divergência que causou a regressão original."""
    from plugins.instagram import InstagramPlugin

    adb_falso["disponivel"] = True
    adb_falso["dispositivos"] = ["192.168.0.10:5555"]
    adb_falso["notificacoes"] = [
        {"pacote": "com.instagram.android", "titulo": "amigo_teste", "texto": "mensagem de teste"},
    ]

    plugin = InstagramPlugin()
    resposta = plugin.handle("minhas mensagens do instagram", {})
    assert "mensagem de teste" in resposta.text


def test_plugin_instagram_sem_fonte_avisa_sem_erro(adb_falso):
    from plugins.instagram import InstagramPlugin

    plugin = InstagramPlugin()
    resposta = plugin.handle("minhas mensagens do instagram", {})
    assert "não vejo nenhuma mensagem" in resposta.text.lower()


def test_tick_nao_falha_sem_fonte_de_mensagens(adb_falso, monkeypatch):
    """_tick() é a rotina de fundo do envio automático -- precisa
    simplesmente não fazer nada (sem estourar exceção) quando não há
    IA configurada ou não há mensagem nenhuma pra responder."""
    from automacao import instagram_auto

    class _JarvisFalso:
        ia_manager = object()

        class settings:
            @staticmethod
            def get(chave, padrao=None):
                return True if chave == "instagram.envio_automatico" else padrao

        memory = None

    instagram_auto._tick(_JarvisFalso())  # não deve levantar


def test_status_instagram_confirma_sessao(monkeypatch):
    from plugins.instagram import InstagramPlugin
    from automacao import instagram_auto

    monkeypatch.setattr(instagram_auto, "available", lambda: True)
    monkeypatch.setattr(instagram_auto, "instagram_conectado", lambda: True)
    resposta = InstagramPlugin().handle("verifica conexão do instagram", {})
    assert "sessão confirmada" in resposta.text.lower()


def test_desafio_de_seguranca_nao_conta_como_login():
    from automacao.instagram_auto import _esta_logado

    class _Pagina:
        url = "https://www.instagram.com/challenge/action/"

        def goto(self, *args, **kwargs):
            return None

    assert _esta_logado(_Pagina()) is False


@pytest.mark.parametrize("url,esperado", [
    ("https://www.instagram.com/direct/inbox/", "conectado"),
    ("https://www.instagram.com/accounts/login/", "desconectado"),
    ("https://www.instagram.com/challenge/action/", "verificacao"),
    ("https://www.instagram.com/checkpoint/", "verificacao"),
])
def test_estado_da_nova_conexao(url, esperado):
    from automacao.instagram_auto import _estado_autenticacao

    class _Pagina:
        def __init__(self):
            self.url = url

        def goto(self, *args, **kwargs):
            return None

    assert _estado_autenticacao(_Pagina()) == esperado


def test_modo_de_conexao_invalido():
    from automacao.instagram_auto import conectar_instagram

    with pytest.raises(ValueError):
        conectar_instagram("modo-inexistente")


@pytest.mark.parametrize("url,esperado", [
    ("https://www.instagram.com/accounts/login/", "desconectado"),
    ("https://www.instagram.com/challenge/", "verificacao"),
    ("https://www.instagram.com/direct/inbox/", "conectado"),
])
def test_estado_do_navegador_normal_via_cdp(url, esperado):
    from automacao.instagram_auto import _estado_url
    assert _estado_url(url) == esperado


def test_login_dedicado_abre_navegador_normal(monkeypatch):
    from automacao import instagram_auto

    aberto = []
    monkeypatch.setattr(instagram_auto, "fechar_sessao", lambda: None)
    monkeypatch.setattr(instagram_auto, "_abrir_login_normal", lambda: aberto.append(True))
    mensagem = instagram_auto.conectar_instagram("dedicado")

    assert aberto == [True]
    assert "navegador normal" in mensagem.lower()


def test_extrai_preview_web_recebido_e_enviado():
    from automacao.instagram_auto import _extrair_preview_botao
    recebido = _extrair_preview_botao("Amigo\nOi, tudo bem?\n\u00a0\n·\n2 min")
    enviado = _extrair_preview_botao("Amigo\nVocê: estou bem\n\u00a0\n·\n3h")
    assert recebido["recebida"] is True
    assert recebido["texto"] == "Oi, tudo bem?"
    assert enviado["recebida"] is False


def test_ignora_botoes_que_nao_sao_conversas():
    from automacao.instagram_auto import _extrair_preview_botao
    assert _extrair_preview_botao("Enviar mensagem") is None
    assert _extrair_preview_botao("Story\nMúsica") is None
