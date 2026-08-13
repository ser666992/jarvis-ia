"""
plugins/knowledge_search.py
=============================
Plugin de busca de conhecimento.

Usa a API pública da Wikipedia (pt) para buscar resumos sobre temas.
Não requer chave de API. Se não houver internet, avisa o usuário.

Níveis de confiança usados aqui:
- SINGLE_SOURCE (70): encontrou um resumo na Wikipedia. É uma fonte
  geralmente confiável, mas é só UMA fonte consultada — não confirmamos
  cruzando com outra, então não sobe para 90/100.
- GUESS (10): não encontrou nada, ou não conseguiu buscar (sem rede).
"""

import re
import urllib.request
import urllib.parse
import json

from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence

_ULTRONSCRIPT_RE = re.compile(r"\b(?:ultron|jarvis)\s*script\b", re.IGNORECASE)


class KnowledgeSearchPlugin(BasePlugin):
    name = "knowledge_search"
    description = "Busca resumos de conhecimento geral na Wikipedia"
    triggers = [
        "o que é", "o que e ", "o que foi", "quem foi", "quem é", "quem e ",
        "pesquise sobre", "pesquisar sobre",
    ]

    WIKI_API = "https://pt.wikipedia.org/api/rest_v1/page/summary/"

    def matches(self, text: str) -> bool:
        t = text.lower()
        # "o que é ultronscript" é do plugins/linguagem_propria.py (a
        # linguagem de programação própria do Ultron) -- sem essa
        # exclusão, o trigger genérico "o que é" sequestrava a pergunta
        # antes do plugin certo (knowledge_search carrega antes de
        # linguagem_propria em ordem alfabética). Achado numa auditoria
        # sistemática de colisão de triggers.
        if _ULTRONSCRIPT_RE.search(t):
            return False
        return any(trig in t for trig in self.triggers)

    def _extract_topic(self, text: str) -> str:
        t = text.lower()
        for trig in self.triggers:
            if trig in t:
                t = t.replace(trig, "")
        return t.strip(" ?.!").strip()

    def handle(self, text: str, context: dict):
        topic = self._extract_topic(text)
        if not topic:
            return Answer("Sobre o que você quer que eu pesquise?", Confidence.GUESS)

        url = self.WIKI_API + urllib.parse.quote(topic.title())
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Ultron/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            extract = data.get("extract")
            if extract:
                return Answer(extract, Confidence.SINGLE_SOURCE)
            # Não transforme uma busca sem resultado em resposta final.
            # Retornar None permite que o gerenciador tente os próximos
            # estágios (inclusive NVIDIA e pesquisa web automática).
            return None
        except Exception:
            # Wikipedia indisponível não significa que o Jarvis não sabe:
            # deixa a pergunta seguir para os provedores de IA e para o
            # fallback de internet do núcleo.
            return None
