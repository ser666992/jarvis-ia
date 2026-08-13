"""
seguranca/auth.py
====================
Autenticação local simples: PIN ou senha, com hash PBKDF2-HMAC-SHA256
(stdlib `hashlib`, sem dependência externa). Guarda hash + salt em
SQLite via `core/database.py` -- nunca a senha em texto puro.
"""

import binascii
import hashlib
import hmac
import os
from datetime import datetime

from core.database import get_database

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seguranca_auth (
    user_id TEXT PRIMARY KEY,
    salt TEXT NOT NULL,
    hash TEXT NOT NULL,
    admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

_ITERATIONS = 200_000


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def _hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return binascii.hexlify(dk).decode()


def set_password(user_id: str, password: str, admin: bool = False):
    _ensure_schema()
    salt = os.urandom(16)
    hashed = _hash_password(password, salt)
    get_database().execute(
        """INSERT INTO seguranca_auth (user_id, salt, hash, admin, created_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
               salt=excluded.salt, hash=excluded.hash, admin=excluded.admin""",
        (user_id, binascii.hexlify(salt).decode(), hashed, int(admin), datetime.now().isoformat()),
    )


def verify_password(user_id: str, password: str) -> bool:
    _ensure_schema()
    row = get_database().query_one("SELECT * FROM seguranca_auth WHERE user_id=?", (user_id,))
    if not row:
        return False
    salt = binascii.unhexlify(row["salt"])
    # hmac.compare_digest (tempo constante) em vez de == -- comparação
    # normal de string vaza quanto tempo levou até o primeiro byte
    # diferente, um canal lateral de timing clássico contra comparação
    # de hash/senha (baixo risco prático aqui, app local sem rede
    # exposta, mas é o jeito CORRETO de comparar hash, sem custo extra).
    return hmac.compare_digest(_hash_password(password, salt), row["hash"])


def is_admin(user_id: str) -> bool:
    _ensure_schema()
    row = get_database().query_one("SELECT admin FROM seguranca_auth WHERE user_id=?", (user_id,))
    return bool(row and row["admin"])


def has_password(user_id: str) -> bool:
    _ensure_schema()
    return get_database().query_one("SELECT 1 FROM seguranca_auth WHERE user_id=?", (user_id,)) is not None
