"""
seguranca/crypto.py
======================
Criptografia de segredos (ex.: API keys salvas em config.json).

Se `cryptography` estiver instalado, usa Fernet (AES simétrico) de
verdade, com a chave mestra local guardada em `data/.jarvis.key`
(gerada automaticamente -- nunca deve ser versionada/compartilhada).

Sem `cryptography` instalado, `encrypt()`/`decrypt()` fazem só uma
ofuscação reversível em base64 (NÃO é criptografia de verdade) e isso
é declarado explicitamente em `is_real_encryption()` -- honestidade
aqui importa mais que fingir segurança que não existe.
"""

import base64
import os

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

_KEY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".jarvis.key"
)


def _load_or_create_key() -> bytes:
    os.makedirs(os.path.dirname(_KEY_PATH), exist_ok=True)
    if os.path.isfile(_KEY_PATH):
        with open(_KEY_PATH, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    with open(_KEY_PATH, "wb") as f:
        f.write(key)
    return key


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    if HAS_CRYPTOGRAPHY:
        f = Fernet(_load_or_create_key())
        return f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return "obfuscado:" + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return token
    if token.startswith("obfuscado:"):
        return base64.b64decode(token[len("obfuscado:"):]).decode("utf-8")
    if HAS_CRYPTOGRAPHY:
        f = Fernet(_load_or_create_key())
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    raise RuntimeError(
        "Token foi criptografado com 'cryptography', mas a biblioteca não está instalada."
    )


def is_real_encryption() -> bool:
    return HAS_CRYPTOGRAPHY
