"""Cofre de segredos: Credential Manager/keyring, com fallback criptografado local."""

import json
import os

from seguranca.crypto import decrypt, encrypt, is_real_encryption

SERVICE = "neutron_vault"
_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "vault.json")

try:
    import keyring
except ImportError:
    keyring = None


def set_secret(name: str, value: str):
    if keyring is not None:
        try:
            keyring.set_password(SERVICE, name, value)
            return
        except Exception:
            pass
    if not is_real_encryption():
        raise RuntimeError("Instale 'keyring' ou 'cryptography' para guardar segredos com segurança.")
    data = _read_file()
    data[name] = encrypt(value)
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


def get_secret(name: str) -> str:
    if keyring is not None:
        try:
            value = keyring.get_password(SERVICE, name)
            if value is not None:
                return value
        except Exception:
            pass
    token = _read_file().get(name)
    return decrypt(token) if token else ""


def delete_secret(name: str):
    if keyring is not None:
        try:
            keyring.delete_password(SERVICE, name)
        except Exception:
            pass
    data = _read_file()
    if name in data:
        del data[name]
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)


def _read_file():
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}
