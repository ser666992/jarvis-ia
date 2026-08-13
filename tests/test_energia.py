"""
tests/test_energia.py
========================
Troca de plano de energia do Windows (controle_pc/energia.py, via
`powercfg`) -- "modo economia de energia"/"desempenho máximo". Aceita
tanto o nome LOCAL de verdade (o que `powercfg /list` retorna, no
idioma do Windows instalado) quanto um apelido comum em português.

Nenhum teste aqui chama powercfg de verdade -- subprocess.run é
substituído por um fake.
"""

import pytest

import controle_pc.energia as energia


_SAIDA_POWERCFG_LIST = (
    "Existem os seguintes esquemas de energia:\n"
    "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Equilibrado) *\n"
    "Power Scheme GUID: a1841308-3541-4fab-bc81-f71556f20b4a  (Economia de energia)\n"
    "Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (Alto desempenho)\n"
)


class _ResultadoFalso:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _preparar_subprocess(monkeypatch, respostas):
    """`respostas`: lista de _ResultadoFalso, uma por chamada esperada
    a subprocess.run, na ordem em que ocorrem."""
    chamadas = []

    def _fake_run(comando, **kwargs):
        chamadas.append(comando)
        return respostas[len(chamadas) - 1]

    monkeypatch.setattr(energia.subprocess, "run", _fake_run)
    return chamadas


@pytest.fixture(autouse=True)
def _forcar_windows(monkeypatch):
    monkeypatch.setattr(energia.sys, "platform", "win32")


def test_listar_planos_parseia_a_saida_do_powercfg(monkeypatch):
    _preparar_subprocess(monkeypatch, [_ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST)])

    planos = energia.listar_planos()

    assert len(planos) == 3
    equilibrado = next(p for p in planos if p["nome"] == "Equilibrado")
    assert equilibrado["ativo"] is True
    assert equilibrado["guid"] == "381b4222-f694-41f0-9685-ff5bb260df2e"
    economia = next(p for p in planos if p["nome"] == "Economia de energia")
    assert economia["ativo"] is False


def test_plano_ativo_retorna_o_marcado_com_asterisco(monkeypatch):
    _preparar_subprocess(monkeypatch, [_ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST)])

    ativo = energia.plano_ativo()

    assert ativo["nome"] == "Equilibrado"


def test_ativar_plano_por_nome_local_exato(monkeypatch):
    chamadas = _preparar_subprocess(monkeypatch, [
        _ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST),  # listar_planos() dentro de ativar_plano
        _ResultadoFalso(stdout=""),                     # /setactive
        _ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST.replace("(Equilibrado) *", "(Equilibrado)").replace(
            "(Alto desempenho)", "(Alto desempenho) *")),  # plano_ativo() depois da troca
    ])

    resultado = energia.ativar_plano("Alto desempenho")

    assert resultado["nome"] == "Alto desempenho"
    assert chamadas[1] == ["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"]


def test_ativar_plano_por_apelido_em_portugues(monkeypatch):
    chamadas = _preparar_subprocess(monkeypatch, [
        _ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST),
        _ResultadoFalso(stdout=""),
        _ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST),
    ])

    energia.ativar_plano("desempenho máximo")

    assert chamadas[1] == ["powercfg", "/setactive", energia._GUIDS_CONHECIDOS["desempenho"]]


def test_ativar_plano_economia_de_energia_por_apelido(monkeypatch):
    chamadas = _preparar_subprocess(monkeypatch, [
        _ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST),
        _ResultadoFalso(stdout=""),
        _ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST),
    ])

    energia.ativar_plano("economia de energia")

    assert chamadas[1] == ["powercfg", "/setactive", energia._GUIDS_CONHECIDOS["economia"]]


def test_ativar_plano_nao_encontrado_levanta_value_error(monkeypatch):
    _preparar_subprocess(monkeypatch, [_ResultadoFalso(stdout=_SAIDA_POWERCFG_LIST)])

    with pytest.raises(ValueError):
        energia.ativar_plano("modo turbo inexistente xyz")


def test_powercfg_falhando_levanta_runtime_error(monkeypatch):
    _preparar_subprocess(monkeypatch, [_ResultadoFalso(stdout="", stderr="acesso negado", returncode=1)])

    with pytest.raises(RuntimeError):
        energia.listar_planos()


def test_indisponivel_fora_do_windows(monkeypatch):
    monkeypatch.setattr(energia.sys, "platform", "linux")

    assert energia.available() is False
    with pytest.raises(RuntimeError):
        energia.listar_planos()
