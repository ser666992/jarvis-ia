"""
controle_pc/energia.py
=========================
Troca de plano de energia do Windows (`powercfg`) -- "modo economia de
energia" / "desempenho máximo" / "equilibrado". Reversível na hora (é
só trocar de novo), mesma categoria de controle_pc/janelas.py
(minimizar/focar/organizar) -- não exige confirmação.

O Windows sempre traz pelo menos os três planos padrão instalados
(Economia de energia / Equilibrado / Alto desempenho -- nomes variam
por idioma do sistema). `_resolver_guid()` busca primeiro por
substring no nome LOCAL de verdade (retornado por `powercfg /list`,
funciona em qualquer idioma), com os GUIDs bem conhecidos desses três
planos padrão como fallback só se a busca por nome não achar nada
(idioma atípico, ou o nome foi customizado).
"""

import re
import subprocess
import sys

from logs.logger import get_logger

log = get_logger("controle_pc")

# GUIDs padrão do Windows pros três planos de energia de fábrica --
# mesmos em QUALQUER instalação (só o nome exibido muda por idioma).
_GUIDS_CONHECIDOS = {
    "economia": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "equilibrado": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "desempenho": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
}
_ALIAS_PARA_CHAVE = {
    "economia de energia": "economia", "economizar energia": "economia", "poupar bateria": "economia",
    "economia": "economia",
    "equilibrado": "equilibrado", "balanceado": "equilibrado", "normal": "equilibrado",
    "alto desempenho": "desempenho", "desempenho maximo": "desempenho", "desempenho máximo": "desempenho",
    "performance maxima": "desempenho", "performance máxima": "desempenho", "desempenho": "desempenho",
}
_LINHA_RE = re.compile(r"^Power Scheme GUID:\s*([0-9a-fA-F-]{36})\s*\(([^)]*)\)\s*(\*)?", re.MULTILINE)


def available() -> bool:
    return sys.platform == "win32"


def _rodar_powercfg(*args) -> str:
    resultado = subprocess.run(["powercfg", *args], capture_output=True, text=True, timeout=10)
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.strip() or f"powercfg {' '.join(args)} falhou (código {resultado.returncode})")
    return resultado.stdout


def listar_planos() -> list:
    """[{"guid", "nome", "ativo"}] -- "nome" já vem no idioma real do
    Windows instalado (não é traduzido/adivinhado aqui)."""
    if not available():
        raise RuntimeError("Troca de plano de energia só é suportada no Windows.")
    saida = _rodar_powercfg("/list")
    return [
        {"guid": m.group(1), "nome": m.group(2).strip(), "ativo": bool(m.group(3))}
        for m in _LINHA_RE.finditer(saida)
    ]


def plano_ativo() -> dict:
    for p in listar_planos():
        if p["ativo"]:
            return p
    return {}


def _resolver_guid(alvo: str, planos: list):
    alvo_low = alvo.strip().lower()
    for p in planos:
        if alvo_low in p["nome"].lower():
            return p["guid"]
    chave = _ALIAS_PARA_CHAVE.get(alvo_low)
    if chave:
        return _GUIDS_CONHECIDOS[chave]
    for frase, chave in _ALIAS_PARA_CHAVE.items():
        if frase in alvo_low or alvo_low in frase:
            return _GUIDS_CONHECIDOS[chave]
    return None


def ativar_plano(nome_ou_alias: str) -> dict:
    """Troca o plano de energia ativo -- aceita tanto o nome LOCAL de
    verdade (ex.: "Alto desempenho") quanto um apelido comum em
    português (ex.: "desempenho máximo", "economia de energia").
    Levanta ValueError se não encontrar nenhum plano correspondente
    (nem por nome local, nem por apelido conhecido). Retorna o plano
    ativo depois da troca (mesmo formato de plano_ativo())."""
    planos = listar_planos()
    guid = _resolver_guid(nome_ou_alias, planos)
    if guid is None:
        nomes = ", ".join(p["nome"] for p in planos) or "nenhum plano listado"
        raise ValueError(f'Não encontrei um plano de energia parecido com "{nome_ou_alias}". Planos disponíveis: {nomes}.')
    _rodar_powercfg("/setactive", guid)
    return plano_ativo()
