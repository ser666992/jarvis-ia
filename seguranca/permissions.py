"""
seguranca/permissions.py
===========================
Gate simples para ações potencialmente destrutivas/irreversíveis
(fechar processo, mover/apagar arquivo, etc.). Módulos de automação e
dispositivos devem checar `requires_confirmation()`/`is_admin_mode()`
antes de executar algo assim, e o plugin/chat que chama isso deve
SEMPRE pedir confirmação explícita do usuário antes de passar
`confirmed=True` -- este módulo não executa nada sozinho, só
centraliza a política de permissões.
"""

from config.settings import get_settings


class PermissionDenied(Exception):
    pass


def is_admin_mode() -> bool:
    return bool(get_settings().get("seguranca.modo_administrador", False))


def requires_confirmation() -> bool:
    return bool(get_settings().get("seguranca.exigir_confirmacao_acoes_destrutivas", True))


def confirmado_pela_frase_ou_config(confirmado_na_frase: bool) -> bool:
    """Atalho pros plugins de chat: considera a ação confirmada se a
    palavra de confirmação apareceu na frase ("confirmo" etc.) OU se o
    usuário desligou a exigência de confirmação globalmente ("não peça
    confirmação", ver plugins/system_control.py). Centraliza essa
    regra pra não duplicar `not requires_confirmation()` em cada
    plugin que faz essa checagem antes de chamar check_destructive_action."""
    return confirmado_na_frase or not requires_confirmation()


def check_destructive_action(action_description: str, confirmed: bool = False):
    """Levanta PermissionDenied se a ação exigir confirmação e ela não
    tiver sido dada explicitamente. Uso:

        seguranca.check_destructive_action("apagar arquivo X", confirmed=usuario_confirmou)
    """
    if requires_confirmation() and not confirmed:
        raise PermissionDenied(
            f"Ação destrutiva bloqueada sem confirmação explícita: {action_description}"
        )
