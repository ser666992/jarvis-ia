"""
core/knowledge.py
====================
Sistema de APRENDIZADO do Ultron: construção de uma base de
conhecimento própria, separada da memória de fatos/perfil
(core/memory.py).

O que este módulo faz, dos 4 requisitos pedidos:

1. Salvar novas informações
   -> learn() grava cada informação aprendida com metadados completos:
      data, fonte, categoria e confiança (ver KnowledgeItem).

2. Detectar assuntos frequentes
   -> toda vez que um assunto é mencionado de novo, increment_mention()
      soma 1 ao contador daquele assunto. detect_frequent_topics()
      lista os assuntos mais mencionados acima de um limiar.
   -> a confiança de um item sobe automaticamente conforme ele é
      reconfirmado/mencionado de novo (ver _confidence_for_mentions),
      reaproveitando os níveis fixos já definidos em core/confidence.py.

3. Construir conhecimento próprio
   -> consolidate() promove um "assunto frequente" (mencionado várias
      vezes) a um KnowledgeItem de categoria "concept" com confiança
      alta -- ou seja, o próprio sistema sintetiza, a partir de
      repetição, algo que passa a tratar como conhecimento consolidado,
      sem que o usuário tenha pedido explicitamente para "salvar" aquilo.

4. Relacionar informações
   -> relate() cria uma ligação nomeada entre dois itens de
      conhecimento (ex.: "Ultron" --usa--> "SQLite").
   -> auto_relate_by_keywords() relaciona automaticamente itens novos
      a itens já existentes que compartilham palavras-chave
      relevantes, formando uma rede de conhecimento (grafo simples)
      sem precisar de comando manual.
   -> related_to() / knowledge_graph() permitem navegar essa rede.

Cada informação aprendida tem sempre, sem exceção, estes 4 metadados:
- created_at (data em que foi aprendida)
- source     (de onde veio: "usuário", "wikipedia", "inferência", ...)
- category   (fact | concept | topic | relation_note | ...)
- confidence (nível fixo de core/confidence.py: 100/90/70/50/30/10)
"""

import sqlite3
import os
import re
from contextlib import contextmanager
from datetime import datetime

from core.confidence import Confidence

DB_PATH = os.environ.get("JARVIS_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "jarvis.db"
)

# Categorias de conhecimento aprendido. Diferentes das categorias de
# memory.py (que são sobre o USUÁRIO: preferências, hábitos, projetos).
# Aqui as categorias são sobre o tipo do CONHECIMENTO em si.
KNOWLEDGE_CATEGORIES = (
    "fact",            # uma afirmação pontual aprendida ("X é Y")
    "concept",         # conhecimento consolidado a partir de repetição/análise
    "topic",           # um assunto/tema observado nas conversas
    "definition",      # definição de um termo (ex.: vinda de busca externa)
    "user_provided",   # informação que o próprio usuário ensinou explicitamente
    "inference",       # algo que o Jarvis inferiu, não que foi dito diretamente
)

# Palavras curtas demais para servirem de palavra-chave de relação
# (stopwords simples em português).
_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "é", "que",
    "um", "uma", "uns", "umas", "em", "no", "na", "nos", "nas", "para",
    "por", "com", "sem", "sobre", "como", "mais", "menos", "muito",
    "ele", "ela", "eles", "elas", "eu", "tu", "voce", "você", "nos", "nós",
    "se", "ou", "mas", "ja", "já", "ainda", "tambem", "também", "isso",
    "isto", "aquilo", "este", "esta", "esse", "essa", "meu", "minha",
    "seu", "sua", "ser", "estar", "ter", "foi", "era", "são", "sao",
}


def _now() -> str:
    return datetime.now().isoformat()


def _extract_keywords(text: str) -> set:
    """Extrai palavras-chave simples (sem stopwords, len >= 3) de um texto.
    Usado para relacionar automaticamente itens de conhecimento entre si."""
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


class Knowledge:
    """
    Camada de aprendizado / base de conhecimento do Ultron.

    Uso típico:
        k = Knowledge()
        item = k.learn("Ultron usa SQLite para persistência",
                        source="usuário", category="fact")
        k.observe_topic("sqlite")          # registra menção a um assunto
        k.detect_frequent_topics()         # quais assuntos voltam sempre?
        k.relate(item_a_id, item_b_id, "relaciona-se com")
    """

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
            -- Cada linha = uma informação aprendida, com seus 4 metadados
            -- obrigatórios: data (created_at), fonte (source), categoria
            -- (category) e confiança (confidence).
            CREATE TABLE IF NOT EXISTS knowledge_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,             -- a informação em si
                category TEXT NOT NULL,            -- fact | concept | topic | ...
                source TEXT NOT NULL,              -- de onde veio a informação
                confidence INTEGER NOT NULL,        -- nível fixo (core/confidence.py)
                mention_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,           -- quando foi aprendida (1ª vez)
                updated_at TEXT NOT NULL            -- última vez que foi reforçada
            );

            CREATE INDEX IF NOT EXISTS idx_knowledge_user
                ON knowledge_items(user_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_category
                ON knowledge_items(user_id, category);

            -- Contagem de menções por "assunto" (tópico curto, normalizado)
            -- ao longo das conversas. É a base da detecção de assuntos
            -- frequentes.
            CREATE TABLE IF NOT EXISTS topic_mentions (
                user_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                PRIMARY KEY (user_id, topic)
            );

            -- Relações entre dois itens de conhecimento (grafo simples).
            -- "relation" é um rótulo livre, ex: "relaciona-se com",
            -- "é parte de", "contradiz", "exemplo de".
            CREATE TABLE IF NOT EXISTS knowledge_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                from_id INTEGER NOT NULL,
                to_id INTEGER NOT NULL,
                relation TEXT NOT NULL DEFAULT 'relaciona-se com',
                created_at TEXT NOT NULL,
                UNIQUE(user_id, from_id, to_id, relation),
                FOREIGN KEY (from_id) REFERENCES knowledge_items(id),
                FOREIGN KEY (to_id) REFERENCES knowledge_items(id)
            );
            """)

    # ====================================================================
    # 1) Salvar novas informações
    # ====================================================================

    def learn(self, user_id: str, content: str, source: str,
              category: str = "fact", confidence: int = Confidence.SINGLE_SOURCE,
              auto_relate: bool = True) -> dict:
        """
        Salva uma nova informação aprendida, com data, fonte, categoria
        e confiança. Se a MESMA informação (conteúdo idêntico, mesma
        categoria) já existir para esse usuário, em vez de duplicar,
        reforça o item existente: soma 1 menção e eleva a confiança
        (reaproveitando o conceito "confirmado várias vezes" ->
        ver _confidence_for_mentions).

        Parâmetros:
            user_id:    dono do conhecimento
            content:    a informação em si, em texto
            source:     de onde veio ("usuário", "wikipedia", "inferência"...)
            category:   uma de KNOWLEDGE_CATEGORIES
            confidence: nível inicial (será normalizado para o mais próximo
                        nível fixo de core/confidence.py)
            auto_relate: se True, tenta relacionar automaticamente este
                        item a itens existentes que compartilhem
                        palavras-chave (requisito "relacionar informações")
        """
        if category not in KNOWLEDGE_CATEGORIES:
            raise ValueError(
                f"Categoria de conhecimento inválida: '{category}'. "
                f"Use uma de: {', '.join(KNOWLEDGE_CATEGORIES)}"
            )
        content = content.strip()
        if not content:
            raise ValueError("Conteúdo do conhecimento não pode ser vazio.")

        confidence = Confidence.normalize(confidence)
        existing = self._find_existing(user_id, content, category)
        now = _now()

        if existing:
            new_count = existing["mention_count"] + 1
            new_confidence = max(confidence, self._confidence_for_mentions(new_count))
            with self._conn() as conn:
                conn.execute("""
                    UPDATE knowledge_items
                    SET mention_count = ?, confidence = ?, updated_at = ?,
                        source = ?
                    WHERE id = ?
                """, (new_count, new_confidence, now, source, existing["id"]))
            item = self.get(existing["id"])
        else:
            with self._conn() as conn:
                cur = conn.execute("""
                    INSERT INTO knowledge_items
                        (user_id, content, category, source, confidence,
                         mention_count, created_at, updated_at)
                    VALUES (?,?,?,?,?,1,?,?)
                """, (user_id, content, category, source, confidence, now, now))
                new_id = cur.lastrowid
            item = self.get(new_id)

        if auto_relate:
            self.auto_relate_by_keywords(user_id, item["id"])

        return item

    def _find_existing(self, user_id: str, content: str, category: str):
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM knowledge_items
                WHERE user_id=? AND category=? AND content=?
            """, (user_id, category, content)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _confidence_for_mentions(mention_count: int) -> int:
        """
        Quanto mais vezes uma mesma informação é aprendida/reconfirmada,
        maior a confiança -- isso espelha o nível CONFIRMED ('informação
        confirmada várias vezes') de core/confidence.py.
        """
        if mention_count >= 3:
            return Confidence.CONFIRMED        # 100: confirmada várias vezes
        if mention_count == 2:
            return Confidence.RELIABLE_SOURCE   # 90: reforçada uma vez
        return Confidence.SINGLE_SOURCE         # 70: vista uma única vez

    def get(self, item_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
            ).fetchone()
        return dict(row) if row else None

    def forget(self, item_id: int) -> bool:
        """Remove um item de conhecimento (e suas relações)."""
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM knowledge_relations WHERE from_id=? OR to_id=?",
                (item_id, item_id)
            )
            cur = conn.execute("DELETE FROM knowledge_items WHERE id=?", (item_id,))
        return cur.rowcount > 0

    def list_knowledge(self, user_id: str, category: str = None, limit: int = 50):
        sql = "SELECT * FROM knowledge_items WHERE user_id=?"
        params = [user_id]
        if category:
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY confidence DESC, mention_count DESC, updated_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def search_knowledge(self, user_id: str, query: str, limit: int = 20):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM knowledge_items
                WHERE user_id=? AND content LIKE ?
                ORDER BY confidence DESC, mention_count DESC LIMIT ?
            """, (user_id, f"%{query}%", limit)).fetchall()
        return [dict(r) for r in rows]

    # ====================================================================
    # 2) Detectar assuntos frequentes
    # ====================================================================

    def observe_topic(self, user_id: str, topic: str):
        """
        Registra uma menção a um assunto/tópico (palavra ou expressão
        curta normalizada). Chamado a cada mensagem processada pelo
        Ultron (aprendizado passivo) e também quando o usuário ensina
        algo explicitamente, para alimentar a detecção de frequência.
        """
        topic = topic.strip().lower()
        if not topic:
            return
        now = _now()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO topic_mentions (user_id, topic, count, first_seen, last_seen)
                VALUES (?,?,1,?,?)
                ON CONFLICT(user_id, topic) DO UPDATE SET
                    count = count + 1,
                    last_seen = excluded.last_seen
            """, (user_id, topic, now, now))

    def observe_text(self, user_id: str, text: str):
        """
        Extrai palavras-chave de um texto livre (ex.: uma mensagem do
        usuário) e registra menção a cada uma. É o que permite detectar
        assuntos frequentes sem o usuário precisar marcar nada
        explicitamente -- o aprendizado acontece em segundo plano, a
        cada interação.
        """
        for kw in _extract_keywords(text):
            self.observe_topic(user_id, kw)

    def topic_mention_count(self, user_id: str, topic: str) -> int:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT count FROM topic_mentions WHERE user_id=? AND topic=?
            """, (user_id, topic.strip().lower())).fetchone()
        return row["count"] if row else 0

    def detect_frequent_topics(self, user_id: str, min_mentions: int = 3, limit: int = 10):
        """
        Retorna os assuntos mencionados com frequência (>= min_mentions
        vezes), ordenados do mais para o menos frequente. Esta é a base
        para decidir o que vale a pena "consolidar" em conhecimento
        próprio (ver consolidate()).
        """
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT topic, count, first_seen, last_seen FROM topic_mentions
                WHERE user_id=? AND count >= ?
                ORDER BY count DESC, last_seen DESC LIMIT ?
            """, (user_id, min_mentions, limit)).fetchall()
        return [dict(r) for r in rows]

    # ====================================================================
    # 3) Construir conhecimento próprio
    # ====================================================================

    def consolidate(self, user_id: str, min_mentions: int = 3) -> list:
        """
        Examina os assuntos frequentes (mencionados >= min_mentions
        vezes) e, para cada um que ainda não tem um item de conhecimento
        próprio na categoria 'concept', cria um. Isso é o Ultron
        "construindo conhecimento por conta própria": ele não esperou
        um comando "lembre que..." -- ele percebeu, pela repetição, que
        aquele assunto importa, e sintetizou isso em conhecimento
        consolidado.

        A confiança do conceito consolidado reflete o número de menções
        (mais menções = mais confiança), via _confidence_for_mentions.

        Retorna a lista de itens de conhecimento criados/reforçados
        nesta chamada.
        """
        created_or_reinforced = []
        for t in self.detect_frequent_topics(user_id, min_mentions=min_mentions, limit=50):
            content = f"'{t['topic']}' é um assunto recorrente nas suas conversas"
            confidence = self._confidence_for_mentions(t["count"])
            item = self.learn(
                user_id, content,
                source=f"observação de {t['count']} menções em conversa",
                category="concept",
                confidence=confidence,
                auto_relate=True,
            )
            created_or_reinforced.append(item)
        return created_or_reinforced

    # ====================================================================
    # 4) Relacionar informações
    # ====================================================================

    def relate(self, user_id: str, from_id: int, to_id: int,
               relation: str = "relaciona-se com") -> dict:
        """Cria (ou ignora se já existir) uma relação nomeada entre dois itens."""
        if from_id == to_id:
            raise ValueError("Um item não pode se relacionar consigo mesmo.")
        now = _now()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO knowledge_relations (user_id, from_id, to_id, relation, created_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(user_id, from_id, to_id, relation) DO NOTHING
            """, (user_id, from_id, to_id, relation, now))
        return {"from_id": from_id, "to_id": to_id, "relation": relation}

    def auto_relate_by_keywords(self, user_id: str, item_id: int,
                                 max_relations: int = 3, min_shared_keywords: int = 2):
        """
        Relaciona automaticamente um item novo a itens existentes que
        compartilhem >= min_shared_keywords palavras-chave relevantes.
        É isso que faz a base de conhecimento crescer como uma REDE
        (e não como uma lista solta de fatos desconexos) sem que o
        usuário precise relacionar nada manualmente.
        """
        item = self.get(item_id)
        if not item:
            return []
        item_keywords = _extract_keywords(item["content"])
        if not item_keywords:
            return []

        candidates = [
            row for row in self.list_knowledge(user_id, limit=500)
            if row["id"] != item_id
        ]

        scored = []
        for cand in candidates:
            cand_keywords = _extract_keywords(cand["content"])
            shared = item_keywords & cand_keywords
            if len(shared) >= min_shared_keywords:
                scored.append((len(shared), cand, shared))

        scored.sort(key=lambda x: -x[0])
        relations_made = []
        for _, cand, shared in scored[:max_relations]:
            rel = self.relate(
                user_id, item_id, cand["id"],
                relation=f"compartilha o(s) tema(s): {', '.join(sorted(shared))}"
            )
            relations_made.append(rel)
        return relations_made

    def related_to(self, item_id: int) -> list:
        """Lista todos os itens relacionados (em qualquer direção) a um item dado."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT r.relation, r.from_id, r.to_id,
                       ki.id as other_id, ki.content as other_content,
                       ki.category as other_category
                FROM knowledge_relations r
                JOIN knowledge_items ki
                  ON ki.id = CASE WHEN r.from_id = ? THEN r.to_id ELSE r.from_id END
                WHERE r.from_id = ? OR r.to_id = ?
            """, (item_id, item_id, item_id)).fetchall()
        return [dict(r) for r in rows]

    def knowledge_graph(self, user_id: str, limit: int = 100) -> dict:
        """Retorna {"items": [...], "relations": [...]} -- o grafo completo
        de conhecimento de um usuário, útil para inspeção ou visualização."""
        items = self.list_knowledge(user_id, limit=limit)
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT from_id, to_id, relation FROM knowledge_relations
                WHERE user_id=? LIMIT ?
            """, (user_id, limit * 3)).fetchall()
        return {"items": items, "relations": [dict(r) for r in rows]}

    # ====================================================================
    # Resumo / relatório de aprendizado
    # ====================================================================

    def learning_summary(self, user_id: str) -> str:
        """Resumo legível do que o Ultron aprendeu, pronto para exibir
        no chat ou injetar como contexto."""
        items = self.list_knowledge(user_id, limit=10)
        topics = self.detect_frequent_topics(user_id, min_mentions=2, limit=5)

        lines = []
        if items:
            lines.append("Conhecimento com maior confiança:")
            for i in items[:10]:
                lines.append(
                    f"- [{i['category']}] {i['content']} "
                    f"(confiança {i['confidence']}%, fonte: {i['source']}, "
                    f"mencionado {i['mention_count']}x, desde {i['created_at'][:10]})"
                )
        if topics:
            lines.append("\nAssuntos frequentes detectados:")
            for t in topics:
                lines.append(f"- '{t['topic']}' ({t['count']} menções)")

        if not lines:
            return "Ainda não construí nenhum conhecimento próprio. Continue conversando comigo!"
        return "\n".join(lines)
