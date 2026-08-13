"""
tests/test_modelo_vosk.py
============================
Seleção do modelo de reconhecimento de voz em português: PEQUENO por
padrão (o modelo grande, vosk-model-pt-fb, tem uma falha reproduzível
de carregamento com a vosk 0.3.45 instalada -- ver docstring de
voz/stt.py), com opção configurável de usar o grande de propósito
(`voz.modelo_stt_tamanho`) e fallback pro pequeno se o grande falhar
ao carregar.

Nenhum teste aqui baixa ou carrega um modelo de verdade -- `vosk.Model`
é substituído por um fake que só registra como foi chamado.
"""

import pytest

from voz.stt import _VOSK_MODELO_PT_GRANDE, SpeechToText


class _ModeloFalso:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def chamadas(monkeypatch):
    """Substitui vosk.Model por um fake que registra os kwargs de cada
    chamada -- permite checar COM QUE PARÂMETRO o modelo foi pedido,
    sem precisar baixar/carregar nada de verdade."""
    import voz.stt as stt_module
    registro = []

    class _FakeVoskModel:
        def __init__(self, **kwargs):
            registro.append(kwargs)
            if kwargs.get("model_name") == "nome-que-nao-existe":
                raise Exception("model name does not exist")

    monkeypatch.setattr(stt_module.vosk, "Model", _FakeVoskModel)
    return registro


def test_padrao_usa_modelo_pequeno_para_portugues(chamadas):
    stt = SpeechToText(language="pt-BR")
    stt._carregar_modelo_vosk()

    assert chamadas == [{"lang": "pt"}]


def test_configuravel_para_grande(chamadas, monkeypatch):
    from config.settings import get_settings
    get_settings().set("voz.modelo_stt_tamanho", "grande")

    stt = SpeechToText(language="pt-BR")
    stt._carregar_modelo_vosk()

    assert chamadas == [{"model_name": _VOSK_MODELO_PT_GRANDE}]


def test_cai_pro_pequeno_se_download_do_grande_falhar(monkeypatch, chamadas):
    """Download/carregamento do modelo grande falhando (sem internet na
    primeira vez, incompatibilidade de formato, etc.) não pode deixar o
    modo de voz inteiro indisponível -- tem que cair pro modelo pequeno
    em vez de propagar o erro."""
    import voz.stt as stt_module
    from config.settings import get_settings
    get_settings().set("voz.modelo_stt_tamanho", "grande")

    class _FakeVoskModelFalhaNoGrande:
        def __init__(self, **kwargs):
            chamadas.append(kwargs)
            if "model_name" in kwargs:
                raise Exception("falha de rede simulada")

    monkeypatch.setattr(stt_module.vosk, "Model", _FakeVoskModelFalhaNoGrande)

    stt = SpeechToText(language="pt-BR")
    modelo = stt._carregar_modelo_vosk()  # não deve levantar

    assert modelo is not None
    assert chamadas == [{"model_name": _VOSK_MODELO_PT_GRANDE}, {"lang": "pt"}]


def test_idioma_nao_portugues_ignora_config_de_tamanho(chamadas):
    from config.settings import get_settings
    get_settings().set("voz.modelo_stt_tamanho", "grande")

    stt = SpeechToText(language="en-US")
    stt._carregar_modelo_vosk()

    assert chamadas == [{"lang": "en-us"}]
