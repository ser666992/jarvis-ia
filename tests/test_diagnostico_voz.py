"""
tests/test_diagnostico_voz.py
================================
"Diagnóstico completo" (plugins/consciencia.py -> core/diagnostico.py)
agora também reporta se o microfone já foi calibrado
(`voz.microfone_calibrado`) -- item pedido explicitamente pelo usuário
("8 ideias", ideia 7), pra quem for investigar por que o Jarvis está
cortando frases saber, sem precisar lembrar de rodar "calibra o
microfone" só pra descobrir se já rodou antes.
"""

from core.diagnostico import _checar_voz


def _item_calibracao(itens):
    return next(i for i in itens if i["nome"] == "calibração do microfone")


def test_nao_calibrado_por_padrao():
    item = _item_calibracao(_checar_voz())
    assert item["ok"] is False
    assert "calibra o microfone" in item["detalhe"]


def test_reporta_valores_depois_de_calibrado():
    from config.settings import get_settings
    settings = get_settings()
    settings.set("voz.microfone_calibrado", True)
    settings.set("voz.silencio_para_parar_segundos", 0.72)
    settings.set("voz.sensibilidade_barge_in", 3.4)

    item = _item_calibracao(_checar_voz())

    assert item["ok"] is True
    assert "0.72" in item["detalhe"]
    assert "3.4" in item["detalhe"]


def test_area_e_sempre_voz():
    for item in _checar_voz():
        assert item["area"] == "Voz"
