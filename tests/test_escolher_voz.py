"""
tests/test_escolher_voz.py
=============================
"Lista as vozes" / "usa a voz ...": escolha manual de qual voz de TTS
o Jarvis usa entre as JÁ instaladas no sistema (voz.voz_tts_id), com
prioridade sobre a heurística automática de idioma/gênero
(`_escolher_voz()`) quando configurada.

Nenhum teste aqui usa SAPI/pyttsx3 de verdade -- tudo é fake.
"""

import pytest

from plugins.escolher_voz import EscolherVozPlugin


_VOZES = [
    {"id": "voz-pt-maria", "nome": "Microsoft Maria Desktop - Portuguese(Brazil)"},
    {"id": "voz-pt-daniel", "nome": "Microsoft Daniel Desktop - Portuguese(Brazil)"},
    {"id": "voz-en-david", "nome": "Microsoft David Desktop - English (United States)"},
]


@pytest.fixture
def plugin(monkeypatch):
    import voz.tts as tts_module
    monkeypatch.setattr(tts_module.TextToSpeech, "listar_vozes", lambda self: list(_VOZES))
    return EscolherVozPlugin()


def test_lista_as_vozes(plugin, contexto):
    assert plugin.matches("lista as vozes")
    resposta = plugin.handle("lista as vozes", contexto)
    assert "Maria" in resposta.text
    assert "Daniel" in resposta.text
    assert "David" in resposta.text


def test_escolhe_por_nome_parcial(plugin, contexto):
    from config.settings import get_settings
    assert plugin.matches("usa a voz daniel")

    resposta = plugin.handle("usa a voz daniel", contexto)

    assert "Daniel" in resposta.text
    assert get_settings().get("voz.voz_tts_id") == "voz-pt-daniel"


def test_escolhe_por_numero(plugin, contexto):
    from config.settings import get_settings
    resposta = plugin.handle("muda a voz pra 3", contexto)

    assert "David" in resposta.text
    assert get_settings().get("voz.voz_tts_id") == "voz-en-david"


def test_voz_nao_encontrada_nao_salva_nada(plugin, contexto):
    from config.settings import get_settings
    resposta = plugin.handle("usa a voz robocop", contexto)

    assert "Não encontrei" in resposta.text
    assert not get_settings().get("voz.voz_tts_id")


def test_volta_pra_voz_padrao_limpa_escolha(plugin, contexto):
    from config.settings import get_settings
    get_settings().set("voz.voz_tts_id", "voz-pt-daniel")
    get_settings().save()

    resposta = plugin.handle("usa a voz padrão", contexto)

    assert "padrão" in resposta.text.lower()
    assert get_settings().get("voz.voz_tts_id") == ""


def test_sem_vozes_instaladas_avisa_em_vez_de_quebrar(monkeypatch, contexto):
    import voz.tts as tts_module
    monkeypatch.setattr(tts_module.TextToSpeech, "listar_vozes", lambda self: [])
    plugin = EscolherVozPlugin()

    resposta = plugin.handle("lista as vozes", contexto)

    assert "Não encontrei" in resposta.text


# ---------- TextToSpeech: resolução da voz configurada ----------

class _VozFalsa:
    def __init__(self, id_, descricao):
        self.Id = id_
        self._descricao = descricao

    def GetDescription(self):
        return self._descricao


def test_resolver_voz_configurada_bate_pelo_id():
    from voz.tts import TextToSpeech
    from config.settings import get_settings
    get_settings().set("voz.voz_tts_id", "voz-pt-daniel")

    tts = TextToSpeech()
    voices = [_VozFalsa("voz-pt-maria", "Maria"), _VozFalsa("voz-pt-daniel", "Daniel")]

    resolvida = tts._resolver_voz_configurada(voices)

    assert resolvida is not None and resolvida.Id == "voz-pt-daniel"


def test_resolver_voz_configurada_sem_escolha_retorna_none():
    from voz.tts import TextToSpeech
    tts = TextToSpeech()
    voices = [_VozFalsa("voz-pt-maria", "Maria")]

    assert tts._resolver_voz_configurada(voices) is None


def test_resolver_voz_configurada_id_nao_existe_mais_retorna_none():
    """Voz escolhida foi desinstalada/trocada -- não pode quebrar,
    só deixa quem chama cair na heurística automática de sempre."""
    from voz.tts import TextToSpeech
    from config.settings import get_settings
    get_settings().set("voz.voz_tts_id", "voz-que-nao-existe-mais")

    tts = TextToSpeech()
    voices = [_VozFalsa("voz-pt-maria", "Maria")]

    assert tts._resolver_voz_configurada(voices) is None
