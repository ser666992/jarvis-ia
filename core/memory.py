"""
core/memory.py
==============
Memória permanente do Ultron usando SQLite.

Guarda:
- Histórico completo de conversas
- Fatos aprendidos (chave -> valor) por usuário [legado, ver memory_commands.py]
- Perfil do usuário
- Log de eventos do sistema
- Itens de memória categorizados e priorizados (nome, preferências,
  projetos, conversas importantes, hábitos) -- ver seção
  "Memória categorizada e priorizada" abaixo.
"""

import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.environ.get("JARVIS_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "jarvis.db"
)

# Categorias válidas para a memória categorizada/priorizada.
MEMORY_CATEGORIES = (
    "name",                     # nome do usuário
    "preference",               # preferências
    "project",                  # projetos
    "important_conversation",   # conversas importantes
    "habit",                    # hábitos
)

# Prioridade padrão por categoria, usada quando o chamador não
# especifica uma. Nome e conversas importantes tendem a ser mais
# críticos para o contexto do que um hábito qualquer, por exemplo.
DEFAULT_PRIORITY_BY_CATEGORY = {
    "name": 100,
    "important_conversation": 90,
    "project": 70,
    "preference": 60,
    "habit": 50,
}


class Memory:
    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,          -- 'user' ou 'jarvis'
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, key)
            );

            CREATE TABLE IF NOT EXISTS profile (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                data TEXT,                   -- JSON livre (preferências, etc.)
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                description TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL,      -- name | preference | project | important_conversation | habit
                title TEXT NOT NULL,         -- chave curta, ex: "cor favorita", "projeto Ultron"
                content TEXT NOT NULL,       -- o conteúdo em si
                priority INTEGER NOT NULL DEFAULT 50,  -- 0-100, maior = mais importante
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, category, title)
            );

            CREATE INDEX IF NOT EXISTS idx_memory_items_user_cat
                ON memory_items(user_id, category);
            """)

    # ---------- Histórico de conversa ----------

    def add_message(self, user_id: str, role: str, content: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (user_id, role, content, timestamp) VALUES (?,?,?,?)",
                (user_id, role, content, datetime.now().isoformat())
            )

    def get_history(self, user_id: str, limit: int = 50):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, timestamp FROM conversations "
                "WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def search_history(self, user_id: str, query: str, limit: int = 20):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, timestamp FROM conversations "
                "WHERE user_id=? AND content LIKE ? ORDER BY id DESC LIMIT ?",
                (user_id, f"%{query}%", limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- Fatos aprendidos (aprendizado contínuo) ----------

    def remember_fact(self, user_id: str, key: str, value: str):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO facts (user_id, key, value, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(user_id, key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
            """, (user_id, key, value, datetime.now().isoformat()))

    def recall_fact(self, user_id: str, key: str):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM facts WHERE user_id=? AND key=?",
                (user_id, key)
            ).fetchone()
        return row["value"] if row else None

    def forget_fact(self, user_id: str, key: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM facts WHERE user_id=? AND key=?", (user_id, key))

    def all_facts(self, user_id: str):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key, value, updated_at FROM facts WHERE user_id=? ORDER BY key",
                (user_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- Perfil do usuário ----------

    def get_profile(self, user_id: str):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM profile WHERE user_id=?", (user_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["data"] = json.loads(d["data"]) if d["data"] else {}
        return d

    def create_or_update_profile(self, user_id: str, name: str = None, **extra_fields):
        now = datetime.now().isoformat()
        existing = self.get_profile(user_id)
        data = existing["data"] if existing else {}
        data.update(extra_fields)
        with self._conn() as conn:
            if existing:
                conn.execute("""
                    UPDATE profile SET
                        name = COALESCE(?, name),
                        data = ?,
                        updated_at = ?
                    WHERE user_id = ?
                """, (name, json.dumps(data, ensure_ascii=False), now, user_id))
            else:
                conn.execute("""
                    INSERT INTO profile (user_id, name, data, created_at, updated_at)
                    VALUES (?,?,?,?,?)
                """, (user_id, name, json.dumps(data, ensure_ascii=False), now, now))

    # ---------- Log de eventos do sistema ----------

    def log_event(self, event_type: str, description: str = ""):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events (event_type, description, timestamp) VALUES (?,?,?)",
                (event_type, description, datetime.now().isoformat())
            )

    def recent_events(self, limit: int = 20):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def events_by_type(self, event_type: str, since: str = None, limit: int = 1000):
        """Eventos filtrados por tipo DIRETO no SQL -- diferente de
        `recent_events(limit=N)`, que pega os últimos N eventos de
        QUALQUER tipo (todos os módulos escrevem na mesma tabela
        `events`). Um tipo raro (ex.: "instagram_processada") podia
        cair fora dessa janela se outros módulos gerassem muitos
        eventos de OUTROS tipos no mesmo período (visao_continua,
        habitos, macros...) -- bug real encontrado em
        automacao/instagram_auto.py: a marca de "mensagem já
        processada" ficava invisível depois de ~500 eventos de
        qualquer tipo, fazendo a mesma mensagem ser reprocessada/
        reenviada, e o limite diário de envios ser subcontado."""
        with self._conn() as conn:
            if since:
                rows = conn.execute(
                    "SELECT * FROM events WHERE event_type = ? AND timestamp >= ? ORDER BY id DESC LIMIT ?",
                    (event_type, since, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events WHERE event_type = ? ORDER BY id DESC LIMIT ?",
                    (event_type, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    # ====================================================================
    # Memória categorizada e priorizada
    # ====================================================================
    # Categorias: name, preference, project, important_conversation, habit
    # Cada item tem um "title" (chave curta, única por categoria+usuário)
    # e um "content" (o valor de fato). A prioridade (0-100) determina a
    # ordem em que os itens aparecem em get_context_summary() e em list().
    #
    # Isto é uma camada categorizada por cima da mesma ideia de
    # facts/profile já existentes -- útil quando você quer falar
    # explicitamente em "projetos" ou "hábitos" em vez de chave/valor
    # genérico, e quando a ordem de importância importa.

    def _validate_category(self, category: str):
        if category not in MEMORY_CATEGORIES:
            raise ValueError(
                f"Categoria inválida: '{category}'. Use uma de: {', '.join(MEMORY_CATEGORIES)}"
            )

    def save_memory(self, user_id: str, category: str, title: str, content: str,
                     priority: int = None) -> dict:
        """
        Salva um novo item de memória (ou atualiza se já existir o mesmo
        título na mesma categoria — equivalente a um "upsert").
        """
        self._validate_category(category)
        title = title.strip()
        content = content.strip()
        if priority is None:
            priority = DEFAULT_PRIORITY_BY_CATEGORY.get(category, 50)
        priority = max(0, min(100, int(priority)))
        now = datetime.now().isoformat()

        with self._conn() as conn:
            conn.execute("""
                INSERT INTO memory_items (user_id, category, title, content, priority, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(user_id, category, title) DO UPDATE SET
                    content=excluded.content,
                    priority=excluded.priority,
                    updated_at=excluded.updated_at
            """, (user_id, category, title, content, priority, now, now))

        return self.get_memory(user_id, category, title)

    def update_memory(self, user_id: str, category: str, title: str,
                       content: str = None, priority: int = None) -> dict | None:
        """
        Atualiza um item já existente. Só altera os campos passados.
        Retorna None se o item não existir (use save_memory para criar).
        """
        self._validate_category(category)
        existing = self.get_memory(user_id, category, title)
        if not existing:
            return None

        new_content = content if content is not None else existing["content"]
        new_priority = priority if priority is not None else existing["priority"]
        new_priority = max(0, min(100, int(new_priority)))
        now = datetime.now().isoformat()

        with self._conn() as conn:
            conn.execute("""
                UPDATE memory_items SET content=?, priority=?, updated_at=?
                WHERE user_id=? AND category=? AND title=?
            """, (new_content, new_priority, now, user_id, category, title))

        return self.get_memory(user_id, category, title)

    def get_memory(self, user_id: str, category: str, title: str) -> dict | None:
        """Busca um item específico por categoria + título."""
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM memory_items WHERE user_id=? AND category=? AND title=?
            """, (user_id, category, title)).fetchone()
        return dict(row) if row else None

    def search_memory(self, user_id: str, query: str, category: str = None, limit: int = 20):
        """
        Busca itens cujo título OU conteúdo contenha o texto de busca.
        Se category for informado, restringe a busca a essa categoria.
        Resultados ordenados por prioridade (maior primeiro).
        """
        sql = """
            SELECT * FROM memory_items
            WHERE user_id=? AND (title LIKE ? OR content LIKE ?)
        """
        params = [user_id, f"%{query}%", f"%{query}%"]
        if category:
            self._validate_category(category)
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY priority DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def list_memory(self, user_id: str, category: str = None, limit: int = 100):
        """
        Lista itens de memória, ordenados por prioridade (maior primeiro)
        e, em caso de empate, pelos mais recentemente atualizados.
        Se category for informado, filtra só por ela.
        """
        sql = "SELECT * FROM memory_items WHERE user_id=?"
        params = [user_id]
        if category:
            self._validate_category(category)
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY priority DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def remove_memory(self, user_id: str, category: str, title: str) -> bool:
        """Remove um item de memória. Retorna True se algo foi removido."""
        self._validate_category(category)
        with self._conn() as conn:
            cur = conn.execute("""
                DELETE FROM memory_items WHERE user_id=? AND category=? AND title=?
            """, (user_id, category, title))
        return cur.rowcount > 0

    def set_priority(self, user_id: str, category: str, title: str, priority: int) -> dict | None:
        """Atalho para reajustar só a prioridade de um item já existente."""
        return self.update_memory(user_id, category, title, priority=priority)

    def get_context_summary(self, user_id: str, limit_per_category: int = 5) -> str:
        """
        Monta um resumo textual da memória mais importante do usuário,
        pronto para ser injetado como contexto (ex: em um prompt de LLM
        no fallback, ou exibido em um comando de chat).
        Prioriza os itens de maior prioridade dentro de cada categoria.
        """
        labels = {
            "name": "Nome",
            "preference": "Preferências",
            "project": "Projetos",
            "important_conversation": "Conversas importantes",
            "habit": "Hábitos",
        }
        blocks = []
        for cat in MEMORY_CATEGORIES:
            items = self.list_memory(user_id, category=cat, limit=limit_per_category)
            if not items:
                continue
            lines = [f"- {i['title']}: {i['content']} (prioridade {i['priority']})" for i in items]
            blocks.append(f"{labels[cat]}:\n" + "\n".join(lines))
        if not blocks:
            return "Nenhuma memória registrada ainda para este usuário."
        return "\n\n".join(blocks)
