"""
core/knowledge_base.py
=========================
Base de conhecimento CURADA do Ultron, organizada em categorias fixas:

    Programação, História, Geografia, Ciências, Matemática, Jogos,
    Tecnologia

Diferença em relação aos outros dois sistemas de conhecimento do
projeto -- para deixar claro o papel de cada um:

- core/memory.py     -> memória SOBRE O USUÁRIO (nome, hábitos, projetos).
- core/knowledge.py  -> conhecimento APRENDIDO organicamente nas
                        conversas (fatos ditos pelo usuário, assuntos
                        frequentes, conceitos consolidados por repetição).
- core/knowledge_base.py (este arquivo) -> uma base de REFERÊNCIA, com
                        categorias de ASSUNTO fixas e predefinidas, que
                        o Ultron consulta ANTES de responder qualquer
                        pergunta -- é a "enciclopédia interna" dele,
                        que pode ser alimentada manualmente (plugin) ou
                        program aticamente, e que tem prioridade sobre
                        Wikipedia/fallback quando encontra algo relevante.

Regra central pedida: "A IA deve pesquisar nessa base antes de
responder." Isso é aplicado em core/jarvis.py:process() -- antes de
despachar a mensagem para os outros plugins, o Ultron chama
KnowledgeBase.search() e, se achar um item relevante, responde com
base nele (alta confiança, fonte = "base de conhecimento interna").
Só quando a base não tem nada relevante é que o fluxo normal de
plugins (incluindo busca na Wikipedia) e o fallback continuam.
"""

import sqlite3
import os
import unicodedata
from contextlib import contextmanager
from datetime import datetime

from core.confidence import Confidence

DB_PATH = os.environ.get("JARVIS_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "jarvis.db"
)

# Categorias fixas da base de conhecimento. Intencionalmente uma tupla
# fechada (igual a MEMORY_CATEGORIES em core/memory.py) -- tentar usar
# outra categoria levanta ValueError, para a base não virar uma bagunça
# de rótulos inconsistentes.
KB_CATEGORIES = (
    "programacao",   # Programação
    "historia",       # História
    "geografia",      # Geografia
    "ciencias",       # Ciências
    "matematica",     # Matemática
    "jogos",          # Jogos
    "tecnologia",     # Tecnologia
)

# Nomes de exibição (com acentuação correta) para cada categoria interna.
KB_CATEGORY_LABELS = {
    "programacao": "Programação",
    "historia": "História",
    "geografia": "Geografia",
    "ciencias": "Ciências",
    "matematica": "Matemática",
    "jogos": "Jogos",
    "tecnologia": "Tecnologia",
}

# Aliases em português livre -> categoria interna, usados pelo plugin
# para reconhecer a categoria a partir do que o usuário digitar.
KB_CATEGORY_ALIASES = {
    "programação": "programacao",
    "programacao": "programacao",
    "código": "programacao",
    "codigo": "programacao",
    "história": "historia",
    "historia": "historia",
    "geografia": "geografia",
    "ciência": "ciencias",
    "ciencia": "ciencias",
    "ciências": "ciencias",
    "ciencias": "ciencias",
    "matemática": "matematica",
    "matematica": "matematica",
    "jogos": "jogos",
    "jogo": "jogos",
    "games": "jogos",
    "tecnologia": "tecnologia",
    "tech": "tecnologia",
}


def _now() -> str:
    return datetime.now().isoformat()


def _normalize(text: str) -> str:
    """Remove acentos e baixa a caixa, para permitir busca tolerante a
    acentuação (ex.: 'fotossintese' encontra 'fotossíntese')."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class KnowledgeBase:
    """
    Base de conhecimento curada, organizada pelas categorias fixas em
    KB_CATEGORIES. Pensada para ser consultada (search/get_by_category)
    ANTES de qualquer outra fonte de resposta.

    Uso típico:
        kb = KnowledgeBase()
        kb.add_entry("programacao", "O que é uma variável",
                     "Um espaço nomeado na memória que guarda um valor.",
                     source="curadoria interna")
        kb.search("variável")  -> [...]
    """

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()
        self._seed_if_empty()

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
            CREATE TABLE IF NOT EXISTS kb_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,       -- uma de KB_CATEGORIES
                title TEXT NOT NULL,           -- pergunta/termo curto
                content TEXT NOT NULL,         -- a resposta/explicação
                source TEXT NOT NULL DEFAULT 'curadoria interna',
                confidence INTEGER NOT NULL DEFAULT 90,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(category, title)
            );

            CREATE INDEX IF NOT EXISTS idx_kb_category
                ON kb_entries(category);
            """)

    def _validate_category(self, category: str):
        if category not in KB_CATEGORIES:
            raise ValueError(
                f"Categoria inválida: '{category}'. Use uma de: "
                f"{', '.join(KB_CATEGORIES)} "
                f"({', '.join(KB_CATEGORY_LABELS.values())})"
            )

    @staticmethod
    def resolve_category(text: str) -> str | None:
        """Tenta reconhecer uma categoria a partir de uma palavra livre
        em português (com ou sem acento). Retorna a categoria interna
        (ex.: 'programacao') ou None se não reconhecer."""
        t = text.strip().lower()
        if t in KB_CATEGORY_ALIASES:
            return KB_CATEGORY_ALIASES[t]
        # tenta de novo comparando sem acentos, para cobrir variações
        # não listadas explicitamente em KB_CATEGORY_ALIASES
        t_norm = _normalize(t)
        for alias, category in KB_CATEGORY_ALIASES.items():
            if _normalize(alias) == t_norm:
                return category
        return None

    # ---------- escrita ----------

    def add_entry(self, category: str, title: str, content: str,
                  source: str = "curadoria interna",
                  confidence: int = Confidence.RELIABLE_SOURCE) -> dict:
        """
        Adiciona (ou atualiza, se já existir o mesmo título na mesma
        categoria) uma entrada na base de conhecimento.
        """
        self._validate_category(category)
        title = title.strip()
        content = content.strip()
        if not title or not content:
            raise ValueError("Título e conteúdo da entrada não podem ser vazios.")
        confidence = Confidence.normalize(confidence)
        now = _now()

        with self._conn() as conn:
            conn.execute("""
                INSERT INTO kb_entries (category, title, content, source, confidence, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(category, title) DO UPDATE SET
                    content=excluded.content,
                    source=excluded.source,
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at
            """, (category, title, content, source, confidence, now, now))

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM kb_entries WHERE category=? AND title=?",
                (category, title)
            ).fetchone()
        return dict(row)

    def remove_entry(self, category: str, title: str) -> bool:
        self._validate_category(category)
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM kb_entries WHERE category=? AND title=?",
                (category, title)
            )
        return cur.rowcount > 0

    # ---------- leitura / pesquisa ----------

    def get_entry(self, entry_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM kb_entries WHERE id=?", (entry_id,)).fetchone()
        return dict(row) if row else None

    def list_by_category(self, category: str, limit: int = 50) -> list:
        self._validate_category(category)
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM kb_entries WHERE category=?
                ORDER BY confidence DESC, title ASC LIMIT ?
            """, (category, limit)).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, category: str = None, limit: int = 5) -> list:
        """
        Pesquisa na base por texto (em título OU conteúdo), tolerante a
        acentuação (ex.: 'fotossintese' encontra 'Fotossíntese'). Esta é
        a função central chamada pelo Ultron ANTES de responder --
        ver core/jarvis.py:process().

        Resultados ordenados por relevância simples (título batendo
        pesa mais que só o conteúdo) e depois por confiança.
        """
        query = query.strip()
        if not query:
            return []
        query_norm = _normalize(query)

        sql = "SELECT * FROM kb_entries"
        params = []
        if category:
            self._validate_category(category)
            sql += " WHERE category = ?"
            params.append(category)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            title_norm = _normalize(d["title"])
            content_norm = _normalize(d["content"])
            if query_norm in title_norm or query_norm in content_norm:
                d["_title_match"] = query_norm in title_norm
                results.append(d)

        results.sort(key=lambda r: (r["_title_match"], r["confidence"]), reverse=True)
        for r in results:
            r.pop("_title_match", None)
        return results[:limit]

    def best_match(self, query: str, category: str = None) -> dict | None:
        """Atalho: devolve só o resultado mais relevante, ou None."""
        results = self.search(query, category=category, limit=1)
        return results[0] if results else None

    def stats(self) -> dict:
        """Quantidade de entradas por categoria -- útil para /basedeconhecimento."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT category, COUNT(*) as total FROM kb_entries
                GROUP BY category
            """).fetchall()
        counts = {r["category"]: r["total"] for r in rows}
        return {cat: counts.get(cat, 0) for cat in KB_CATEGORIES}

    # ---------- seed inicial ----------

    def _seed_if_empty(self):
        """Popula a base com alguns itens iniciais em cada categoria,
        só na primeira vez (se a tabela estiver vazia), para o usuário
        já ter o que consultar e um exemplo do formato esperado."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM kb_entries").fetchone()["c"]
        if total > 0:
            return

        seed_data = [
            ("programacao", "O que é uma variável",
             "Uma variável é um espaço nomeado na memória usado para guardar "
             "um valor que pode mudar durante a execução de um programa."),
            ("programacao", "O que é Python",
             "Python é uma linguagem de programação de alto nível, "
             "interpretada e de tipagem dinâmica, conhecida pela sintaxe "
             "simples e legível."),
            ("historia", "Quando foi a Proclamação da República no Brasil",
             "A Proclamação da República no Brasil ocorreu em 15 de "
             "novembro de 1889, encerrando o período monárquico."),
            ("historia", "O que foi a Revolução Industrial",
             "A Revolução Industrial foi um período de transformação "
             "econômica e tecnológica iniciado na Inglaterra no século "
             "XVIII, marcado pela mecanização da produção."),
            ("geografia", "Qual é o maior país do mundo em área",
             "A Rússia é o maior país do mundo em área territorial, com "
             "cerca de 17 milhões de km²."),
            ("geografia", "Qual é o maior bioma do Brasil",
             "A Amazônia é o maior bioma brasileiro, ocupando cerca de "
             "49% do território nacional."),
            ("ciencias", "O que é fotossíntese",
             "Fotossíntese é o processo pelo qual plantas e outros "
             "organismos convertem luz solar, água e CO2 em energia "
             "química e oxigênio."),
            ("ciencias", "Quantos planetas tem o sistema solar",
             "O sistema solar tem oito planetas: Mercúrio, Vênus, Terra, "
             "Marte, Júpiter, Saturno, Urano e Netuno."),
            ("matematica", "O que é um número primo",
             "Um número primo é um número natural maior que 1 que só "
             "pode ser dividido exatamente por 1 e por ele mesmo."),
            ("matematica", "O que é o teorema de Pitágoras",
             "O teorema de Pitágoras afirma que, em um triângulo "
             "retângulo, o quadrado da hipotenusa é igual à soma dos "
             "quadrados dos catetos (a² + b² = c²)."),
            ("jogos", "O que é um roguelike",
             "Roguelike é um gênero de jogo caracterizado por geração "
             "procedural de níveis, permadeath (morte permanente) e alta "
             "dificuldade, inspirado no jogo Rogue (1980)."),
            ("jogos", "O que é FPS em jogos",
             "FPS pode significar 'first-person shooter' (jogo de tiro em "
             "primeira pessoa) ou 'frames per second' (quadros por "
             "segundo), dependendo do contexto."),
            ("tecnologia", "O que é a nuvem (cloud computing)",
             "Cloud computing é o fornecimento de recursos de computação "
             "(servidores, armazenamento, software) sob demanda pela "
             "internet, em vez de hardware local."),
            ("tecnologia", "O que é inteligência artificial",
             "Inteligência artificial é a área da computação dedicada a "
             "criar sistemas capazes de realizar tarefas que normalmente "
             "exigiriam inteligência humana, como reconhecer padrões e "
             "tomar decisões."),
        ]

        now = _now()
        with self._conn() as conn:
            for category, title, content in seed_data:
                conn.execute("""
                    INSERT OR IGNORE INTO kb_entries
                        (category, title, content, source, confidence, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?)
                """, (category, title, content, "curadoria interna",
                      Confidence.RELIABLE_SOURCE, now, now))
