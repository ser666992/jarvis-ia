"""
plugins/knowledge_base.py
============================
Expõe a base de conhecimento curada (core/knowledge_base.py) via
linguagem natural no chat: adicionar entradas, listar por categoria,
buscar manualmente.

IMPORTANTE: a consulta automática "pesquisar na base antes de
responder" NÃO depende deste plugin -- ela acontece em
core/jarvis.py:process(), antes do dispatch normal de plugins. Este
plugin aqui é só para o usuário GERENCIAR a base (adicionar/listar
itens) e para buscas explícitas nela.

Categorias fixas (ver core/knowledge_base.py:KB_CATEGORIES):
  Programação, História, Geografia, Ciências, Matemática, Jogos, Tecnologia

Exemplos de frases:
  "adicione na base de programação: O que é um loop | Uma estrutura
   que repete um bloco de código várias vezes"
  "liste a base de história"
  "busque na base sobre fotossíntese"
  "remova da base de jogos: O que é FPS em jogos"
  "estatísticas da base de conhecimento"

Confiança:
- Adicionar/remover -> CONFIRMED (100): escrita confirmada no sistema.
- Buscar/listar -> usa a confiança própria de cada entrada (definida
  na criação, RELIABLE_SOURCE=90 por padrão para curadoria interna).
- Nada encontrado -> GUESS (10).
"""

import re

from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence
from core.knowledge_base import KB_CATEGORY_LABELS, KnowledgeBase

# Cada regex aceita tanto o imperativo formal ("adicione"/"remova"/
# "liste") quanto a forma presente-indicativo/casual ("adiciona"/
# "remove"/"lista"), que é como boa parte das pessoas realmente fala
# -- sem isso, "adiciona na base de X: ..." ficava silenciosamente sem
# resposta (nem o `matches()` default por substring nem o regex do
# handle() reconheciam essa conjugação).
_ADICIONAR_RE = re.compile(r"adicion(?:e|ar|a)\s+(?:na|à)\s+base\s+de\s+(.+?):\s*(.+)", re.IGNORECASE)
_REMOVER_RE = re.compile(r"remov(?:a|er|e)\s+da\s+base\s+de\s+(.+?):\s*(.+)", re.IGNORECASE)
_LISTAR_RE = re.compile(r"list(?:e|ar|a)\s+a\s+(?:base|categoria)\s+de\s+(.+)", re.IGNORECASE)
_BUSCAR_RE = re.compile(r"(?:busque|buscar|busca|pesquise|pesquisa)\s+na\s+base\s+(?:sobre\s+)?(.+)", re.IGNORECASE)


class KnowledgeBasePlugin(BasePlugin):
    name = "knowledge_base"
    description = "Gerencia a base de conhecimento curada por categorias (Programação, História, Geografia, Ciências, Matemática, Jogos, Tecnologia)"
    triggers = [
        "adicione na base", "adicionar na base", "adicione à base",
        "liste a base", "listar a base", "liste a categoria",
        "busque na base", "buscar na base", "pesquise na base",
        "remova da base", "remover da base",
        "estatísticas da base", "estatisticas da base", "resumo da base",
        "categorias da base", "quais categorias",
    ]

    def _format_entry(self, e: dict) -> str:
        return (
            f"#{e['id']} [{KB_CATEGORY_LABELS[e['category']]}] {e['title']}: {e['content']} "
            f"(confiança {e['confidence']}%, fonte: {e['source']})"
        )

    def matches(self, text: str) -> bool:
        t_low = text.lower().strip()
        if "categorias da base" in t_low or "quais categorias" in t_low:
            return True
        if "estatísticas da base" in t_low or "estatisticas da base" in t_low or "resumo da base" in t_low:
            return True
        return bool(
            _ADICIONAR_RE.search(text) or _REMOVER_RE.search(text)
            or _LISTAR_RE.search(t_low) or _BUSCAR_RE.search(t_low)
        )

    def handle(self, text: str, context: dict):
        kb: KnowledgeBase = context.get("knowledge_base")
        t = text.strip()
        t_low = t.lower()

        if kb is None:
            return Answer("A base de conhecimento não está disponível neste contexto.", Confidence.GUESS)

        # --- Categorias disponíveis ---
        if "categorias da base" in t_low or "quais categorias" in t_low:
            labels = ", ".join(KB_CATEGORY_LABELS.values())
            return Answer(f"Categorias da base de conhecimento: {labels}.", Confidence.CONFIRMED)

        # --- Estatísticas ---
        if "estatísticas da base" in t_low or "estatisticas da base" in t_low or "resumo da base" in t_low:
            stats = kb.stats()
            lines = [f"- {KB_CATEGORY_LABELS[cat]}: {n} entrada(s)" for cat, n in stats.items()]
            total = sum(stats.values())
            return Answer(
                f"Base de conhecimento: {total} entrada(s) no total.\n" + "\n".join(lines),
                Confidence.CONFIRMED
            )

        # --- Adicionar: "adicione/adiciona na base de <categoria>: <título> | <conteúdo>" ---
        m = _ADICIONAR_RE.search(t)
        if m:
            cat_word, rest = m.group(1).strip(), m.group(2).strip()
            category = kb.resolve_category(cat_word)
            if not category:
                return Answer(
                    f"Não reconheci a categoria '{cat_word}'. Categorias válidas: "
                    f"{', '.join(KB_CATEGORY_LABELS.values())}.",
                    Confidence.GUESS
                )
            if "|" not in rest:
                return Answer(
                    "Para adicionar, use o formato: "
                    "'adicione na base de <categoria>: <título> | <conteúdo>'.",
                    Confidence.GUESS
                )
            title, content = [p.strip() for p in rest.split("|", 1)]
            if not title or not content:
                return Answer("O título e o conteúdo não podem ficar vazios.", Confidence.GUESS)

            entry = kb.add_entry(category, title, content, source="usuário")
            return Answer(
                f"Adicionei à base de {KB_CATEGORY_LABELS[category]} (#{entry['id']}): "
                f"\"{entry['title']}\".",
                Confidence.CONFIRMED
            )

        # --- Remover: "remova/remove da base de <categoria>: <título>" ---
        m = _REMOVER_RE.search(t)
        if m:
            cat_word, title = m.group(1).strip(), m.group(2).strip(" .!")
            category = kb.resolve_category(cat_word)
            if not category:
                return Answer(f"Não reconheci a categoria '{cat_word}'.", Confidence.GUESS)
            removed = kb.remove_entry(category, title)
            if removed:
                return Answer(
                    f"Removi '{title}' da base de {KB_CATEGORY_LABELS[category]}.",
                    Confidence.CONFIRMED
                )
            return Answer(
                f"Não encontrei '{title}' na base de {KB_CATEGORY_LABELS[category]}.",
                Confidence.GUESS
            )

        # --- Listar por categoria: "liste/lista a base de <categoria>" ---
        m = _LISTAR_RE.search(t_low)
        if m:
            cat_word = m.group(1).strip(" ?.!")
            category = kb.resolve_category(cat_word)
            if not category:
                return Answer(
                    f"Não reconheci a categoria '{cat_word}'. Categorias válidas: "
                    f"{', '.join(KB_CATEGORY_LABELS.values())}.",
                    Confidence.GUESS
                )
            entries = kb.list_by_category(category)
            if not entries:
                return Answer(f"A base de {KB_CATEGORY_LABELS[category]} ainda está vazia.", Confidence.GUESS)
            lines = [self._format_entry(e) for e in entries]
            return Answer(
                f"Entradas em {KB_CATEGORY_LABELS[category]}:\n" + "\n".join(lines),
                Confidence.CONFIRMED
            )

        # --- Buscar explicitamente na base: "busque/busca na base sobre <termo>" ---
        m = _BUSCAR_RE.search(t_low)
        if m:
            query = m.group(1).strip(" ?.!")
            results = kb.search(query)
            if not results:
                return Answer(f"Não encontrei nada sobre '{query}' na base de conhecimento.", Confidence.GUESS)
            lines = [self._format_entry(e) for e in results]
            top_confidence = max(e["confidence"] for e in results)
            return Answer(
                f"Encontrei na base de conhecimento sobre '{query}':\n" + "\n".join(lines),
                top_confidence
            )

        return None
