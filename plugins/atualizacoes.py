"""
plugins/atualizacoes.py
==========================
Lado de chat do sistema de atualização (atualizacoes/updater.py):
verificar se há uma versão nova no repositório remoto, e aplicar (git
pull) só com confirmação explícita.

A checagem automática periódica (config `atualizacoes.verificar_automaticamente`,
ligado por padrão) já roda sozinha em segundo plano e avisa por
notificação quando encontra algo novo -- este plugin é só para
consultar sob demanda e para aplicar a atualização quando você decidir.

Comandos:
    "verifica atualização" / "tem atualização nova" / "checa atualização do jarvis"
    "atualiza o jarvis, confirmo"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from seguranca.permissions import PermissionDenied, confirmado_pela_frase_ou_config

_VERIFICAR_RE = re.compile(
    # (?!...biblioteca...) -- sem essa exclusão, "tem alguma atualização
    # de biblioteca" (sistema/observador_internet.py, atualização de
    # DEPENDÊNCIA de terceiros) era sequestrado por este plugin (que é
    # sobre o Ultron se autoatualizar), já que "tem ... atualização" sem
    # mais nada é genérico demais. Achado numa auditoria de colisão de
    # triggers, no mesmo dia em que o Observador da Internet foi criado.
    r"\b(verific[ae]|check?[ae]|tem)\w*\s+.*\batualiza[çc][ãa]o\b(?!.*\b(?:biblioteca|framework|depend[êe]ncia)s?\b)|"
    r"\batualiza[çc][ãa]o\s+(?:nova|dispon[ií]vel)\b(?!.*\b(?:biblioteca|framework|depend[êe]ncia)s?\b)",
    re.IGNORECASE,
)
_ATUALIZAR_RE = re.compile(r"\batualiz[ae]\w*\s+o\s+jarvis\b", re.IGNORECASE)
_TESTAR_RE = re.compile(
    r"\b(test[ae]|valid[ae]|prepar[ae])\w*\s+.*\batualiza[çc][ãa]o\b",
    re.IGNORECASE,
)
_CONFIRM_WORD_RE = re.compile(r"\bconfirmo\b|\btenho certeza\b", re.IGNORECASE)


class AtualizacoesPlugin(BasePlugin):
    name = "atualizacoes"
    description = "Verifica se há uma versão nova do Ultron no repositório remoto, e atualiza (git pull) com confirmação"
    triggers = ["atualização do jarvis", "atualiza o jarvis", "tem atualização", "verifica atualização", "checa atualização"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(_ATUALIZAR_RE.search(t) or _TESTAR_RE.search(t) or _VERIFICAR_RE.search(t))

    def handle(self, text: str, context: dict):
        t = text.strip()
        if _ATUALIZAR_RE.search(t):
            confirmado = confirmado_pela_frase_ou_config(bool(_CONFIRM_WORD_RE.search(t)))
            return self._atualizar(confirmado)
        if _TESTAR_RE.search(t):
            return self._testar()
        if _VERIFICAR_RE.search(t):
            return self._verificar()
        return None

    def _verificar(self):
        import atualizacoes
        resultado = atualizacoes.check_for_updates()
        if not resultado["verificavel"]:
            return Answer(f"Não consegui checar: {resultado['motivo']}", Confidence.GUESS)
        if resultado["atualizacao_disponivel"]:
            return Answer(
                f"Tem atualização nova -- commit local {resultado['commit_local']}, "
                f"remoto {resultado['commit_remoto']}. Diga \"atualiza o jarvis, confirmo\" pra aplicar.",
                Confidence.CONFIRMED,
            )
        return Answer(f"Já está atualizado (v{resultado['versao_local']}).", Confidence.CONFIRMED)

    def _testar(self):
        import atualizacoes
        resultado = atualizacoes.validate_candidate()
        if resultado.get("sucesso"):
            return Answer(
                f"Atualização candidata {resultado.get('commit_candidato', '?')} aprovada "
                "em ambiente isolado. Compilação e testes passaram; nada foi aplicado ainda.",
                Confidence.CONFIRMED,
            )
        return Answer(
            f"Atualização bloqueada na fase {resultado.get('fase', '?')}: "
            f"{resultado.get('erro', 'validação falhou')}.",
            Confidence.GUESS,
        )

    def _atualizar(self, confirmado: bool):
        if not confirmado:
            return Answer(
                "Atualizar roda 'git pull' de verdade -- pode sobrescrever mudanças locais e só "
                "vale totalmente depois de reiniciar o Ultron. Tem certeza? Diga "
                '"atualiza o jarvis, confirmo".',
                Confidence.GUESS,
            )
        import atualizacoes
        try:
            resultado = atualizacoes.aplicar_atualizacao(confirmed=True)
        except PermissionDenied as e:
            return Answer(str(e), Confidence.GUESS)
        except Exception as e:
            return Answer(f"Não consegui atualizar: {e}", Confidence.GUESS)
        if not resultado["sucesso"]:
            return Answer(f"'git pull' falhou:\n{resultado['saida'][:800]}", Confidence.GUESS)
        return Answer(
            f"Atualizado com sucesso:\n{resultado['saida'][:800]}\n\n"
            "Reinicie o Ultron pra rodar com o código novo.",
            Confidence.CONFIRMED,
        )
