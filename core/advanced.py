"""Recursos avançados persistentes: projetos, checkpoints, memória temporária e métricas."""

import json
from datetime import datetime, timedelta

from core.database import get_database


def _now():
    return datetime.now().isoformat()


def ensure_schema():
    get_database().executescript("""
        CREATE TABLE IF NOT EXISTS neutron_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
            status TEXT NOT NULL DEFAULT 'ativo', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, UNIQUE(user_id, name)
        );
        CREATE TABLE IF NOT EXISTS neutron_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL, title TEXT NOT NULL, data TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES neutron_projects(id)
        );
        CREATE TABLE IF NOT EXISTS neutron_temp_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL, content TEXT NOT NULL,
            expires_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS neutron_provider_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL, success INTEGER NOT NULL,
            elapsed_ms INTEGER NOT NULL, error TEXT, created_at TEXT NOT NULL
        );
    """)


def save_project(user_id: str, name: str, description: str = "") -> dict:
    ensure_schema()
    now = _now()
    get_database().execute("""
        INSERT INTO neutron_projects(user_id,name,description,status,created_at,updated_at)
        VALUES(?,?,?,'ativo',?,?)
        ON CONFLICT(user_id,name) DO UPDATE SET description=excluded.description,
        updated_at=excluded.updated_at
    """, (user_id, name.strip(), description.strip(), now, now))
    return get_database().query_one(
        "SELECT * FROM neutron_projects WHERE user_id=? AND name=?",
        (user_id, name.strip()))


def list_projects(user_id: str) -> list:
    ensure_schema()
    return get_database().query(
        "SELECT * FROM neutron_projects WHERE user_id=? ORDER BY updated_at DESC", (user_id,))


def add_checkpoint(project_id: int, title: str, data=None) -> dict:
    ensure_schema()
    cursor = get_database().execute(
        "INSERT INTO neutron_checkpoints(project_id,title,data,created_at) VALUES(?,?,?,?)",
        (project_id, title.strip(), json.dumps(data or {}, ensure_ascii=False), _now()))
    return get_database().query_one(
        "SELECT * FROM neutron_checkpoints WHERE id=?", (cursor.lastrowid,))


def list_checkpoints(project_id: int) -> list:
    ensure_schema()
    return get_database().query(
        "SELECT * FROM neutron_checkpoints WHERE project_id=? ORDER BY id DESC", (project_id,))


def remember_temporarily(user_id: str, content: str, hours: float = 24) -> dict:
    ensure_schema()
    expires = (datetime.now() + timedelta(hours=max(0.01, hours))).isoformat()
    cursor = get_database().execute(
        "INSERT INTO neutron_temp_memory(user_id,content,expires_at,created_at) VALUES(?,?,?,?)",
        (user_id, content.strip(), expires, _now()))
    return get_database().query_one(
        "SELECT * FROM neutron_temp_memory WHERE id=?", (cursor.lastrowid,))


def active_temp_memory(user_id: str) -> list:
    ensure_schema()
    get_database().execute("DELETE FROM neutron_temp_memory WHERE expires_at<=?", (_now(),))
    return get_database().query(
        "SELECT * FROM neutron_temp_memory WHERE user_id=? ORDER BY id DESC", (user_id,))


def record_provider_metric(provider: str, success: bool, elapsed_ms: int, error: str = ""):
    ensure_schema()
    get_database().execute("""
        INSERT INTO neutron_provider_metrics(provider,success,elapsed_ms,error,created_at)
        VALUES(?,?,?,?,?)
    """, (provider or "desconhecido", int(success), max(0, int(elapsed_ms)), error[:500], _now()))


def provider_summary() -> list:
    ensure_schema()
    return get_database().query("""
        SELECT provider, COUNT(*) calls, SUM(success) successes,
        ROUND(AVG(elapsed_ms),1) avg_ms,
        ROUND(100.0*SUM(success)/COUNT(*),1) success_rate
        FROM neutron_provider_metrics GROUP BY provider ORDER BY calls DESC
    """)
