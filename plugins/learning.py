"""
plugins/learning.py
======================
Expõe o sistema de APRENDIZADO (core/knowledge.py) via linguagem
natural simples no chat.

Diferença em relação aos outros plugins de memória:
- memory_commands.py / categorized_memory.py guardam informação SOBRE
  O USUÁRIO (nome, preferências, hábitos, projetos).
- learning.py guarda CONHECIMENTO GERAL aprendido nas conversas (fatos,
  conceitos, assuntos recorrentes) e constrói relações entre eles --
  é a camada de "a IA aprende e evolui o que sabe", não "a IA lembra
  dados do usuário".

Exemplos de frases:
  "aprenda que o sol é uma estrela"
  "aprenda que python é uma linguagem de programação, fonte: documentação oficial"
  "o que você aprendeu sobre python"
  "assuntos frequentes" / "sobre o que mais falamos"
  "construa conhecimento" / "consolide o que aprendeu"
  "relacione 3 com 7: ambos tratam de bancos de dados"
  "o que está relacionado a 3"
  "resumo do aprendizado" / "o que você já aprendeu"
  "esqueça o conhecimento 5"

Confiança:
- Ensinar algo explicitamente -> RELIABLE_SOURCE (90): foi o próprio
  usuário, uma fonte que o Ultron trata como confiável, quem afirmou.
  Reforçar (ensinar de novo) eleva automaticamente para CONFIRMED (100)
  via core/knowledge.py (mention_count).
- Resultado de busca de conhecimento (encadeado com knowledge_search)
  -> SINGLE_SOURCE (70), e fica marcado com source="wikipedia".
- Consolidação automática de assuntos frequentes -> confiança calculada
  a partir do número de menções (ver core/knowledge.py).
- Operações de escrita confirmadas pelo próprio sistema (relacionar,
  esquecer) -> CONFIRMED (100).
- Quando nada é encontrado -> GUESS (10).
"""

import re

from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence
from core.timeline import registrar

# Marcadores explícitos de CORREÇÃO -- deliberadamente restritos a frases
# que só fazem sentido como correção mesmo (não apenas "não", que também
# aparece em "não sei"/"não quero"/etc. e viraria falso positivo salvando
# lixo como "fato aprendido"). Cada marcador precisa vir seguido do fato
# certo pra valer a pena salvar.
_CORRECAO_RE = re.compile(
    r"(?:^|,\s*)(?:o certo é\b|o certo e\b|o correto é\b|o correto e\b|"
    r"na verdade é\b|na verdade e\b|corre[çc][ãa]o\s*:|corrigindo\s*:)\s*(.+)",
    re.IGNORECASE,
)


class LearningPlugin(BasePlugin):
    name = "learning"
    description = "Sistema de aprendizado: salva conhecimento, detecta assuntos frequentes, relaciona informações"
    triggers = [
        "aprenda que", "aprenda isso", "aprenda:",
        "o que você aprendeu", "o que voce aprendeu",
        "assuntos frequentes", "sobre o que mais falamos", "temas frequentes",
        "construa conhecimento", "consolide", "consolidar conhecimento",
        "relacione", "o que está relacionado", "o que esta relacionado",
        "resumo do aprendizado", "o que você já aprendeu", "o que voce ja aprendeu",
        "esqueça o conhecimento", "esqueca o conhecimento", "esquece o conhecimento",
        "grafo de conhecimento",
        "o certo é", "o certo e", "o correto é", "o correto e",
        "na verdade é", "na verdade e", "correção:", "correcao:", "corrigindo:",
    ]

    # ---------- helpers ----------

    def _format_item_line(self, item: dict) -> str:
        return (
            f"#{item['id']} [{item['category']}] {item['content']} "
            f"(confiança {item['confidence']}%, fonte: {item['source']}, "
            f"categoria: {item['category']}, aprendido em {item['created_at'][:10]})"
        )

    def handle(self, text: str, context: dict):
        knowledge = context.get("knowledge")
        user_id = context["user_id"]
        t = text.lower().strip()

        if knowledge is None:
            return Answer(
                "O sistema de aprendizado não está disponível neste contexto.",
                Confidence.GUESS
            )

        # --- Ensinar: "aprenda que X" / "aprenda isso: X" / "aprenda: X" ---
        m = re.search(r"aprenda\s*(?:que|isso)?\s*:?\s*(.+)", t, re.IGNORECASE)
        if m:
            body = m.group(1).strip(" .!")
            source = "usuário"
            # Permite indicar fonte explicitamente: "..., fonte: livro X"
            fm = re.search(r"(.+?),?\s*fonte:\s*(.+)", body)
            if fm:
                body, source = fm.group(1).strip(" ,."), fm.group(2).strip(" .!")
            if not body:
                return Answer("O que você quer que eu aprenda?", Confidence.GUESS)

            item = knowledge.learn(
                user_id, body, source=source,
                category="user_provided", confidence=Confidence.RELIABLE_SOURCE,
            )
            knowledge.observe_text(user_id, body)
            return Answer(
                f"Aprendido (#{item['id']}): \"{item['content']}\"\n"
                f"Categoria: {item['category']} | Fonte: {item['source']} | "
                f"Confiança: {item['confidence']}% | Data: {item['created_at'][:10]}",
                Confidence.CONFIRMED
            )

        # --- Correção do usuário: "não, o certo é X" / "na verdade é X" /
        # "correção: X" -- aprende com o próprio erro, sem precisar de
        # comando explícito "aprenda que". Confiança máxima: é o usuário
        # corrigindo o Jarvis na cara, a fonte mais confiável que existe.
        m = _CORRECAO_RE.search(t)
        if m:
            corrigido = m.group(1).strip(" .!?")
            if len(corrigido) < 4:
                return Answer("Entendido que errei -- qual é o certo, então?", Confidence.GUESS)
            item = knowledge.learn(
                user_id, corrigido, source="correção do usuário",
                category="user_provided", confidence=Confidence.CONFIRMED,
            )
            knowledge.observe_text(user_id, corrigido)
            registrar("correcao_usuario", corrigido[:200])
            return Answer(
                f"Entendido, corrigido (#{item['id']}): \"{item['content']}\". "
                "Vou lembrar disso daqui pra frente.",
                Confidence.CONFIRMED
            )

        # --- Assuntos frequentes ---
        if "assuntos frequentes" in t or "sobre o que mais falamos" in t or "temas frequentes" in t:
            topics = knowledge.detect_frequent_topics(user_id, min_mentions=2, limit=10)
            if not topics:
                return Answer(
                    "Ainda não detectei assuntos recorrentes nas nossas conversas. "
                    "Continue conversando comigo que eu vou notando os padrões.",
                    Confidence.GUESS
                )
            lines = [f"- '{tp['topic']}' ({tp['count']} menções, última em {tp['last_seen'][:10]})"
                      for tp in topics]
            return Answer(
                "Assuntos que aparecem com frequência nas suas conversas:\n" + "\n".join(lines),
                Confidence.CONFIRMED
            )

        # --- Construir/consolidar conhecimento a partir de assuntos frequentes ---
        if "construa conhecimento" in t or "consolide" in t or "consolidar conhecimento" in t:
            created = knowledge.consolidate(user_id, min_mentions=3)
            if not created:
                return Answer(
                    "Ainda não há assuntos mencionados o suficiente (3+ vezes) "
                    "para eu consolidar em conhecimento próprio. Continue conversando comigo.",
                    Confidence.GUESS
                )
            lines = [self._format_item_line(i) for i in created]
            return Answer(
                "Consolidei conhecimento próprio a partir dos assuntos recorrentes:\n"
                + "\n".join(lines),
                Confidence.CONFIRMED
            )

        # --- Relacionar dois itens: "relacione 3 com 7: motivo opcional" ---
        m = re.search(r"relacione\s+(\d+)\s+(?:com|a)\s+(\d+)(?:\s*[:\-]\s*(.+))?", t)
        if m:
            from_id, to_id = int(m.group(1)), int(m.group(2))
            relation = (m.group(3) or "relaciona-se com").strip(" .!")
            if not knowledge.get(from_id) or not knowledge.get(to_id):
                return Answer(
                    f"Não encontrei os itens #{from_id} e/ou #{to_id} na base de conhecimento. "
                    "Use 'o que você aprendeu' para ver os IDs.",
                    Confidence.GUESS
                )
            knowledge.relate(user_id, from_id, to_id, relation=relation)
            return Answer(
                f"Relacionei #{from_id} com #{to_id} ({relation}).",
                Confidence.CONFIRMED
            )

        # --- O que está relacionado a um item: "o que está relacionado a 3" ---
        m = re.search(r"o que est[áa] relacionado a\s+(\d+)", t)
        if m:
            item_id = int(m.group(1))
            item = knowledge.get(item_id)
            if not item:
                return Answer(f"Não encontrei o item #{item_id}.", Confidence.GUESS)
            related = knowledge.related_to(item_id)
            if not related:
                return Answer(
                    f"O item #{item_id} (\"{item['content']}\") ainda não tem "
                    "relações registradas com outros conhecimentos.",
                    Confidence.CONFIRMED
                )
            lines = [f"- #{r['other_id']} \"{r['other_content']}\" ({r['relation']})" for r in related]
            return Answer(
                f"Itens relacionados a #{item_id} (\"{item['content']}\"):\n" + "\n".join(lines),
                Confidence.CONFIRMED
            )

        # --- Grafo de conhecimento completo (resumo numérico) ---
        if "grafo de conhecimento" in t:
            graph = knowledge.knowledge_graph(user_id)
            n_items, n_rel = len(graph["items"]), len(graph["relations"])
            return Answer(
                f"Base de conhecimento atual: {n_items} item(ns) aprendido(s) "
                f"e {n_rel} relação(ões) entre eles.",
                Confidence.CONFIRMED
            )

        # --- Esquecer um item de conhecimento: "esqueça/esquece o conhecimento 5" ---
        m = re.search(r"esque(?:ça|ca|ce) o conhecimento\s+(\d+)", t)
        if m:
            item_id = int(m.group(1))
            removed = knowledge.forget(item_id)
            if removed:
                return Answer(f"Removi o conhecimento #{item_id} da base.", Confidence.CONFIRMED)
            return Answer(f"Não encontrei o conhecimento #{item_id}.", Confidence.GUESS)

        # --- O que você aprendeu (geral, ou sobre um tema específico) ---
        m = re.search(r"o que (?:você|voce) (?:já\s+|ja\s+)?aprendeu(?:\s+sobre\s+(.+))?", t)
        if m:
            topic = (m.group(1) or "").strip(" ?.!")
            if topic:
                results = knowledge.search_knowledge(user_id, topic)
                if not results:
                    return Answer(f"Ainda não aprendi nada sobre '{topic}'.", Confidence.GUESS)
                lines = [self._format_item_line(i) for i in results]
                return Answer(f"O que aprendi sobre '{topic}':\n" + "\n".join(lines), Confidence.SINGLE_SOURCE)

            items = knowledge.list_knowledge(user_id, limit=15)
            if not items:
                return Answer("Ainda não aprendi nada de forma explícita. Me ensine algo com 'aprenda que ...'.",
                              Confidence.GUESS)
            lines = [self._format_item_line(i) for i in items]
            return Answer("Aqui está o que aprendi, do mais confiável para o menos:\n" + "\n".join(lines),
                          Confidence.CONFIRMED)

        # --- Resumo geral do aprendizado ---
        if "resumo do aprendizado" in t:
            return Answer(knowledge.learning_summary(user_id), Confidence.CONFIRMED)

        return None
