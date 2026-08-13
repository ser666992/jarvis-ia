"""
tests/test_calibracao_voz.py
===============================
Regressão real reportada: baixar `voz.silencio_para_parar_segundos`
agressivamente demais corta frases mais longas no meio de uma pausa
natural de respiração/pensamento (ex.: "quais animais... moram na
amazônia" virando lixo tipo "ora o amargo" -- a gravação parou ANTES
da pessoa terminar). `calibrar_microfone()` mede a maior PAUSA INTERNA
de uma gravação de teste (nunca a pausa final) e recomenda um valor
que sobrevive a essa pausa real, em vez de um palpite genérico igual
pra todo mundo.

Nenhum teste aqui usa microfone de verdade -- `sd.InputStream` é
substituído por um stream falso com blocos pré-definidos.
"""

import numpy as np
import pytest

from voz.stt import SpeechToText


def _bloco(amplitude: int, tamanho: int = 480) -> np.ndarray:
    return np.full((tamanho, 1), amplitude, dtype="int16")


class _StreamFalso:
    def __init__(self, blocos):
        self._blocos = list(blocos)
        self._i = 0

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self, tamanho):
        if self._i < len(self._blocos):
            bloco = self._blocos[self._i]
            self._i += 1
        else:
            bloco = np.zeros((tamanho, 1), dtype="int16")
        return bloco, False


def _preparar_stream_falso(monkeypatch, blocos):
    import voz.stt as stt_module
    monkeypatch.setattr(stt_module.sd, "InputStream", lambda **kw: _StreamFalso(blocos))


@pytest.fixture
def stt():
    return SpeechToText(language="pt-BR")


def test_calibracao_mede_a_maior_pausa_interna(monkeypatch, stt):
    """Simula "quais animais... [pausa de 0.9s] ...moram na amazônia":
    dois trechos falados com uma pausa real no meio -- a recomendação
    tem que ficar ACIMA dessa pausa, não abaixo (senão continuaria
    cortando a mesma frase que motivou a calibração)."""
    calib = [_bloco(0) for _ in range(8)]  # ~240ms de silêncio ambiente
    trecho1 = [_bloco(15000) for _ in range(20)]  # ~0.6s falando
    pausa_interna = [_bloco(0) for _ in range(30)]  # ~0.9s de pausa NO MEIO
    trecho2 = [_bloco(15000) for _ in range(25)]  # ~0.75s falando de novo
    sobra = [_bloco(0) for _ in range(20)]

    blocos = calib + trecho1 + pausa_interna + trecho2 + sobra
    _preparar_stream_falso(monkeypatch, blocos)

    resultado = stt.calibrar_microfone(duracao_segundos=len(blocos) * 0.03)

    assert resultado["maior_pausa_interna_segundos"] == pytest.approx(0.9, abs=0.05)
    # recomendação com margem ACIMA da pausa medida -- nunca abaixo dela
    assert resultado["silencio_recomendado_segundos"] > resultado["maior_pausa_interna_segundos"]
    assert resultado["qualidade"] == "boa"
    assert resultado["aviso"] is None
    # margem grande entre pico de voz (15000) e ambiente (0->piso) -- sensibilidade
    # recomendada fica dentro dos limites sensatos, não em nenhum extremo absurdo.
    assert 1.8 <= resultado["sensibilidade_barge_in_recomendada"] <= 4.5


def test_calibracao_sensibilidade_barge_in_menor_para_margem_pequena(monkeypatch, stt):
    """Voz mais baixa em relação ao ruído ambiente (margem pequena entre
    pico e chão de ruído) deve recomendar um multiplicador MENOR (mais
    sensível) -- senão o barge-in nunca dispararia pra essa pessoa."""
    calib = [_bloco(300) for _ in range(8)]  # ambiente já com algum ruído
    fala_proxima_do_ruido = [_bloco(900) for _ in range(30)]  # margem pequena
    _preparar_stream_falso(monkeypatch, calib + fala_proxima_do_ruido)

    resultado = stt.calibrar_microfone(duracao_segundos=(len(calib) + len(fala_proxima_do_ruido)) * 0.03)

    assert resultado["sensibilidade_barge_in_recomendada"] <= 2.8


def test_calibracao_ignora_pausa_final(monkeypatch, stt):
    """A pausa DEPOIS do último trecho falado (a pessoa simplesmente
    terminou) não pode contar como "pausa interna" -- senão qualquer
    gravação de teste, não importa quão limpa a fala tenha sido,
    sempre recomendaria um valor alto só por causa do silêncio no
    finalzinho."""
    calib = [_bloco(0) for _ in range(8)]
    fala_continua = [_bloco(15000) for _ in range(40)]  # fala de uma vez só, sem pausa no meio
    pausa_final = [_bloco(0) for _ in range(60)]  # ~1.8s de silêncio só no final

    blocos = calib + fala_continua + pausa_final
    _preparar_stream_falso(monkeypatch, blocos)

    resultado = stt.calibrar_microfone(duracao_segundos=len(blocos) * 0.03)

    assert resultado["maior_pausa_interna_segundos"] == 0.0
    assert resultado["silencio_recomendado_segundos"] == 0.5  # valor padrão quando não há pausa interna nenhuma


def test_calibracao_respeita_piso_e_teto(monkeypatch, stt):
    """Uma pausa interna absurdamente longa (ex.: a pessoa parou pra
    pensar bastante) não pode fazer a recomendação explodir pra um
    valor tão alto que o Jarvis pareça travado esperando resposta."""
    calib = [_bloco(0) for _ in range(8)]
    trecho1 = [_bloco(15000) for _ in range(20)]
    pausa_gigante = [_bloco(0) for _ in range(150)]  # ~4.5s de pausa no meio
    trecho2 = [_bloco(15000) for _ in range(20)]
    sobra = [_bloco(0) for _ in range(10)]

    blocos = calib + trecho1 + pausa_gigante + trecho2 + sobra
    _preparar_stream_falso(monkeypatch, blocos)

    resultado = stt.calibrar_microfone(duracao_segundos=len(blocos) * 0.03)

    assert resultado["silencio_recomendado_segundos"] <= 1.5


def test_calibracao_avisa_volume_baixo(monkeypatch, stt):
    calib = [_bloco(0) for _ in range(8)]
    fala_baixinha = [_bloco(80) for _ in range(40)]  # abaixo de _RMS_MINIMO_CONFIAVEL
    _preparar_stream_falso(monkeypatch, calib + fala_baixinha)

    resultado = stt.calibrar_microfone(duracao_segundos=(len(calib) + len(fala_baixinha)) * 0.03)

    assert resultado["qualidade"] == "volume_baixo"
    assert resultado["aviso"] is not None


def test_calibracao_avisa_ruido_alto(monkeypatch, stt):
    calib = [_bloco(1200) for _ in range(8)]  # "ambiente" já ruidoso na calibração
    fala = [_bloco(15000) for _ in range(40)]
    _preparar_stream_falso(monkeypatch, calib + fala)

    resultado = stt.calibrar_microfone(duracao_segundos=(len(calib) + len(fala)) * 0.03)

    assert resultado["qualidade"] == "ruido_alto"
    assert resultado["aviso"] is not None


# ---------- plugin (comando de chat) ----------

def test_plugin_calibra_e_salva_no_config(monkeypatch, contexto):
    from plugins.calibracao_voz import CalibracaoVozPlugin
    from config.settings import get_settings
    import plugins.calibracao_voz as plugin_module

    # notify() toca um som do sistema de verdade -- inofensivo, mas sem
    # razão pra um teste automatizado fazer barulho toda vez que roda.
    monkeypatch.setattr(plugin_module, "notify", lambda *a, **k: None)

    calib = [_bloco(0) for _ in range(8)]
    trecho1 = [_bloco(15000) for _ in range(20)]
    pausa_interna = [_bloco(0) for _ in range(25)]
    trecho2 = [_bloco(15000) for _ in range(20)]
    sobra = [_bloco(0) for _ in range(10)]
    _preparar_stream_falso(monkeypatch, calib + trecho1 + pausa_interna + trecho2 + sobra)

    plugin = CalibracaoVozPlugin()
    assert plugin.matches("calibra o microfone")
    resposta = plugin.handle("calibra o microfone", contexto)

    assert "Calibrado" in resposta.text
    valor_salvo = get_settings().get("voz.silencio_para_parar_segundos")
    assert valor_salvo is not None and valor_salvo > 0
    assert get_settings().get("voz.sensibilidade_barge_in") is not None
    assert get_settings().get("voz.microfone_calibrado") is True
