from seguranca.auth import set_password, verify_password, is_admin, has_password
from seguranca.backup import create_backup, list_backups, maybe_auto_backup, iniciar as iniciar_backup_diario
from seguranca.crypto import decrypt, encrypt, is_real_encryption
from seguranca.permissions import (
    PermissionDenied, check_destructive_action, is_admin_mode, requires_confirmation,
)

__all__ = [
    "set_password", "verify_password", "is_admin", "has_password",
    "encrypt", "decrypt", "is_real_encryption",
    "is_admin_mode", "requires_confirmation", "check_destructive_action", "PermissionDenied",
    "create_backup", "list_backups", "maybe_auto_backup", "iniciar_backup_diario",
    "status",
]


def status() -> dict:
    real_crypto = is_real_encryption()
    motivo = (
        "PBKDF2 (auth) + Fernet (cryptography instalado)" if real_crypto else
        "PBKDF2 (auth) ok; criptografia real de segredos indisponível (instale 'cryptography')"
    )
    return {
        "disponivel": True,
        "motivo": motivo,
        "detalhes": {"criptografia_real": real_crypto, "modo_administrador": is_admin_mode()},
    }
