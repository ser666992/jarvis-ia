"""
core/database.py
==================
Helper genérico de acesso ao SQLite, reutilizado pelos módulos novos
(`sistema`, `seguranca`, `automacao`, `atualizacoes`) para suas
próprias tabelas -- tudo no mesmo arquivo `data/jarvis.db` já usado
por `core/memory.py`, mantendo "banco de dados" centralizado em um
único lugar em vez de espalhar arquivos `.db` pelo projeto.

`core/memory.py` mantém sua própria conexão (não foi alterado, para
não arriscar regressão em código já testado) -- este helper é para
tabelas NOVAS.

Variável de ambiente JARVIS_DB_PATH: sobrescreve o caminho do banco.
Use isso ao rodar testes/scripts exploratórios (ex.: instanciar
`Jarvis()` fora do fluxo normal) para não escrever no banco real do
usuário -- `core/memory.py` respeita a mesma variável.
"""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("JARVIS_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "jarvis.db"
)


class Database:
    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()):
        """Pra INSERT/UPDATE/DELETE. O Cursor devolvido já teve sua
        conexão FECHADA (connect() fecha ao sair do `with`, antes deste
        método retornar) -- só `.lastrowid`/`.rowcount` são seguros de
        ler depois (valores já capturados pelo sqlite3 no momento do
        execute, não exigem conexão viva). Chamar `.fetchone()`/
        `.fetchall()` no cursor devolvido levanta
        `sqlite3.ProgrammingError` (conexão fechada) -- use `query()`/
        `query_one()` para SELECT."""
        with self.connect() as conn:
            return conn.execute(sql, params)

    def executescript(self, script: str):
        with self.connect() as conn:
            conn.executescript(script)

    def query(self, sql: str, params: tuple = ()):
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: tuple = ()):
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


_default_db = None


def get_database() -> Database:
    global _default_db
    if _default_db is None:
        _default_db = Database()
    return _default_db
