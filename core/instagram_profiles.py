"""Perfis resumidos de comunicação por contato do Instagram."""

import json
from datetime import datetime

from core.database import get_database

_SCHEMA = """
CREATE TABLE IF NOT EXISTS instagram_contact_profiles (
    user_id TEXT NOT NULL,
    contact TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, contact)
);
"""


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def save(user_id: str, contact: str, profile: dict, sample_count: int):
    _ensure_schema()
    get_database().execute(
        "INSERT INTO instagram_contact_profiles "
        "(user_id,contact,profile_json,sample_count,updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(user_id,contact) DO UPDATE SET "
        "profile_json=excluded.profile_json,sample_count=excluded.sample_count,"
        "updated_at=excluded.updated_at",
        (user_id, contact, json.dumps(profile, ensure_ascii=False),
         int(sample_count), datetime.now().isoformat()))
    return get(user_id, contact)


def get(user_id: str, contact: str):
    _ensure_schema()
    row = get_database().query_one(
        "SELECT * FROM instagram_contact_profiles WHERE user_id=? AND contact=?",
        (user_id, contact))
    if row:
        row["profile"] = json.loads(row.pop("profile_json"))
    return row


def list_all(user_id: str):
    _ensure_schema()
    rows = get_database().query(
        "SELECT * FROM instagram_contact_profiles WHERE user_id=? ORDER BY contact",
        (user_id,))
    for row in rows:
        row["profile"] = json.loads(row.pop("profile_json"))
    return rows


def prompt_for(user_id: str, contact: str) -> str:
    row = get(user_id, contact)
    if not row:
        return ""
    p = row["profile"]
    parts = [
        f"Tom habitual com {contact}: {p.get('tom', 'natural')}.",
        f"Tamanho: {p.get('tamanho', 'breve')}.",
        f"Vocabulário e marcas de estilo: {p.get('vocabulario', '')}.",
        f"Emojis: {p.get('emojis', '')}.",
        f"Dinâmica da relação: {p.get('dinamica', '')}.",
        f"Evitar: {p.get('evitar', '')}.",
    ]
    return " ".join(x for x in parts if not x.endswith(": ."))
