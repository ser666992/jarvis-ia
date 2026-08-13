"""
plugins/categorized_memory.py
================================
Expõe a memória categorizada e priorizada (core/memory.py:
save_memory/update_memory/search_memory/remove_memory/list_memory)
via linguagem natural simples.

Categorias suportadas: preferência, projeto, conversa importante, hábito.
("Nome" já é tratado pelo plugin memory_commands.py via perfil, mas
também é replicado aqui como categoria 'name' para quem quiser listar
tudo de forma unificada com /memoria.)

Exemplos de frases:
  "salve a preferência tema escuro: prefiro interface escura"
  "salve o projeto Ultron: assistente pessoal em Python com plugins"
  "salve o hábito acordar cedo: desperto às 6h todos os dias"
  "salve a conversa importante decisao final: vamos usar SQLite"
  "atualize a preferência tema escuro: ativar por padrão sempre"
  "busque sobre Ultron"
  "remova o hábito acordar cedo"
  "liste meus projetos" / "liste minhas preferências" / "liste meus hábitos"
  "minha memória" -> mostra resumo priorizado de tudo

Confiança:
- Salvar/atualizar/remover -> CONFIRMED (100): é uma operação de
  escrita confirmada no próprio sistema.
- Buscar/listar -> SINGLE_SOURCE (70): o conteúdo retornado foi
  informado uma única vez pelo usuário e nunca reconfirmado de
  forma independente.
- Quando nada é encontrado -> GUESS (10).
"""

import re

from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence
from core.memory import MEMORY_CATEGORIES

# Mapeia palavras em português para as categorias internas
CATEGORY_WORDS = {
    "preferência": "preference",
    "preferencia": "preference",
    "projeto": "project",
    "conversa importante": "important_conversation",
    "hábito": "habit",
    "habito": "habit",
    "nome": "name",
}

# Para listar/plural
CATEGORY_PLURAL_WORDS = {
    "preferências": "preference",
    "preferencias": "preference",
    "projetos": "project",
    "conversas importantes": "important_conversation",
    "hábitos": "habit",
    "habitos": "habit",
}

# Os dicionários acima são mantidos à mão, em paralelo à lista oficial
# em core/memory.py -- essa checagem falha alto e cedo (na hora de
# importar o plugin) se algum dia divergirem (categoria renomeada/
# removida lá sem atualizar aqui), em vez de só estourar depois, tarde,
# na hora de salvar_memory() rejeitar uma categoria que não existe mais.
assert set(CATEGORY_WORDS.values()) <= set(MEMORY_CATEGORIES), (
    f"CATEGORY_WORDS tem categoria(s) fora de MEMORY_CATEGORIES: "
    f"{set(CATEGORY_WORDS.values()) - set(MEMORY_CATEGORIES)}"
)
assert set(CATEGORY_PLURAL_WORDS.values()) <= set(MEMORY_CATEGORIES), (
    f"CATEGORY_PLURAL_WORDS tem categoria(s) fora de MEMORY_CATEGORIES: "
    f"{set(CATEGORY_PLURAL_WORDS.values()) - set(MEMORY_CATEGORIES)}"
)

LABELS = {
    "name": "nome",
    "preference": "preferência",
    "project": "projeto",
    "important_conversation": "conversa importante",
    "habit": "hábito",
}


def _find_category(text: str):
    """Procura por uma palavra de categoria (singular) no início do
    texto -- precisa ser um PREFIXO de verdade (não só 'in text'),
    senão uma categoria mais longa que aparece no meio do título
    (ex.: "projeto" dentro de "nome do projeto: ...") ganharia da
    categoria certa, e o corte `head[len(word):]` produziria um
    título com o offset errado."""
    for word, cat in sorted(CATEGORY_WORDS.items(), key=lambda kv: -len(kv[0])):
        if text.startswith(word):
            return cat, word
    return None, None


def _find_plural_category(text: str):
    for word, cat in sorted(CATEGORY_PLURAL_WORDS.items(), key=lambda kv: -len(kv[0])):
        if word in text:
            return cat
    return None


# Aceita tanto a forma imperativa formal ("salve"/"atualize"/"remova"/
# "busque"/"liste") quanto a presente-indicativo/casual ("salva"/
# "atualiza"/"remove"/"busca"/"lista"), que é como a maioria das
# pessoas realmente fala no dia a dia -- sem isso, frases como "salva
# a preferência ..." ou "lista meus projetos" eram silenciosamente
# ignoradas (nem o `matches()` default por substring, nem os regexes
# do handle() reconheciam essa conjugação).
_SALVAR_RE = re.compile(r"\bsalv[ae]\w*\s+(?:a|o)\s+(.+?):\s*(.+)")
_ATUALIZAR_RE = re.compile(r"\batualiz[ae]\w*\s+(?:a|o)\s+(.+?):\s*(.+)")
_REMOVER_RE = re.compile(r"\bremov[ae]\w*\s+(?:a|o)\s+(.+)")
_BUSCAR_RE = re.compile(r"\bbusc[ae]\w*\s+sobre\s+(.+)")
_RESUMO_RE = re.compile(r"\bminha\s+mem[oó]ria\b|\bresumo\s+da\s+mem[oó]ria\b")
_LISTAR_RE = re.compile(r"\blist[ae]\w*\s+(?:meus|minhas)\b")


class CategorizedMemoryPlugin(BasePlugin):
    name = "categorized_memory"
    description = "Memória permanente categorizada: preferências, projetos, conversas importantes, hábitos"
    triggers = [
        "salve a", "salve o", "atualize a", "atualize o",
        "busque sobre", "remova a", "remova o", "esqueca a memoria",
        "liste meus", "liste minhas", "minha memória", "minha memoria",
        "resumo da memória", "resumo da memoria",
    ]

    def matches(self, text: str) -> bool:
        t = text.lower().strip()
        if _RESUMO_RE.search(t) or _LISTAR_RE.search(t) or _BUSCAR_RE.search(t):
            return True
        if _SALVAR_RE.search(t) or _ATUALIZAR_RE.search(t):
            return True
        # _REMOVER_RE sozinho era genérico demais ("remov[ae]\w*\s+(?:a|o)\s+(.+)"
        # bate com QUALQUER "remove a/o X") -- sequestrava comandos de outros
        # plugins tipo "remove o login do gmail" (logins_web.py), respondendo
        # "não reconheci a categoria" em vez de deixar o plugin certo agir.
        # Bug real, achado numa auditoria sistemática de colisão de triggers.
        # Só reivindica a frase se o alvo bater com uma categoria de verdade.
        m = _REMOVER_RE.search(t)
        if m:
            categoria, _palavra = _find_category(m.group(1).strip())
            return categoria is not None
        return False

    def handle(self, text: str, context: dict):
        memory = context["memory"]
        user_id = context["user_id"]
        t = text.lower().strip()

        # --- Resumo geral priorizado ---
        if _RESUMO_RE.search(t):
            summary = memory.get_context_summary(user_id)
            return Answer(summary, Confidence.CONFIRMED)

        _categorias_validas = ", ".join(sorted(set(LABELS.values())))

        # --- Salvar: "salve/salva a/o <categoria> <titulo>: <conteudo>" ---
        m = _SALVAR_RE.search(t)
        if m and ":" in t:
            head, content = m.group(1).strip(), m.group(2).strip()
            category, word = _find_category(head)
            if not category:
                return Answer(
                    f"Não reconheci a categoria em '{head}'. Categorias válidas: {_categorias_validas}.",
                    Confidence.GUESS
                )
            title = head[len(word):].strip(" -")
            if not title:
                return Answer(
                    f"Preciso de um título para o(a) {LABELS[category]}. "
                    f"Ex: 'salve o {word} nome_curto: conteúdo'.",
                    Confidence.GUESS
                )
            memory.save_memory(user_id, category, title, content)
            return Answer(
                f"Salvei o(a) {LABELS[category]} '{title}'.",
                Confidence.CONFIRMED
            )

        # --- Atualizar: "atualize/atualiza a/o <categoria> <titulo>: <novo conteudo>" ---
        m = _ATUALIZAR_RE.search(t)
        if m and ":" in t:
            head, content = m.group(1).strip(), m.group(2).strip()
            category, word = _find_category(head)
            if not category:
                return Answer(
                    f"Não reconheci a categoria em '{head}'. Categorias válidas: {_categorias_validas}.",
                    Confidence.GUESS
                )
            title = head[len(word):].strip(" -")
            updated = memory.update_memory(user_id, category, title, content=content)
            if updated:
                return Answer(
                    f"Atualizei o(a) {LABELS[category]} '{title}'.",
                    Confidence.CONFIRMED
                )
            return Answer(
                f"Não encontrei um(a) {LABELS[category]} chamado '{title}' para atualizar. "
                "Use 'salve' para criar um novo.",
                Confidence.GUESS
            )

        # --- Remover: "remova/remove a/o <categoria> <titulo>" ---
        m = _REMOVER_RE.search(t)
        if m:
            head = m.group(1).strip(" .!?")
            category, word = _find_category(head)
            if not category:
                return Answer(
                    f"Não reconheci a categoria em '{head}'. Categorias válidas: {_categorias_validas}.",
                    Confidence.GUESS
                )
            title = head[len(word):].strip(" -")
            removed = memory.remove_memory(user_id, category, title)
            if removed:
                return Answer(
                    f"Removi o(a) {LABELS[category]} '{title}' da memória.",
                    Confidence.CONFIRMED
                )
            return Answer(
                f"Não encontrei um(a) {LABELS[category]} chamado '{title}'.",
                Confidence.GUESS
            )

        # --- Buscar: "busque/busca sobre <termo>" ---
        m = _BUSCAR_RE.search(t)
        if m:
            query = m.group(1).strip(" .!?")
            results = memory.search_memory(user_id, query)
            if results:
                lines = [
                    f"[{LABELS[r['category']]}] {r['title']}: {r['content']} (prioridade {r['priority']})"
                    for r in results
                ]
                return Answer("Encontrei isto na memória:\n" + "\n".join(lines), Confidence.SINGLE_SOURCE)
            return Answer(f"Não encontrei nada sobre '{query}' na memória.", Confidence.GUESS)

        # --- Listar por categoria: "liste/lista meus projetos" / "...minhas preferências" ---
        if _LISTAR_RE.search(t):
            category = _find_plural_category(t)
            if category:
                items = memory.list_memory(user_id, category=category)
                if items:
                    lines = [f"- {i['title']}: {i['content']} (prioridade {i['priority']})" for i in items]
                    return Answer(
                        f"Aqui estão seus(as) {LABELS[category]}s, do mais para o menos prioritário:\n"
                        + "\n".join(lines),
                        Confidence.SINGLE_SOURCE
                    )
                return Answer(f"Você ainda não tem nenhum(a) {LABELS[category]} salvo(a).", Confidence.GUESS)

        return None
