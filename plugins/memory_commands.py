"""
plugins/memory_commands.py
=============================
Plugin que expõe comandos de memória/aprendizado/perfil para o usuário
via linguagem natural simples:

  "lembre que minha cor favorita é azul"   -> guarda fato
  "qual minha cor favorita"                -> recupera fato
  "esqueça minha cor favorita"             -> apaga fato
  "meu nome é Pedro"                       -> atualiza perfil
  "meus fatos" / "o que voce sabe sobre mim" -> lista tudo

Níveis de confiança:
- CONFIRMED (100): confirmar que um dado foi salvo/apagado é um fato
  sobre o próprio sistema (a escrita aconteceu), então é 100% certo.
- SINGLE_SOURCE (70): ao recuperar um fato, ele foi registrado uma
  única vez na memória (uma única "fonte" — a fala anterior do
  usuário) e nunca foi confirmado de novo, então fica em 70, não 100.
- GUESS (10): quando não sabe a resposta.
"""

import re
from core.plugin_manager import BasePlugin
from core.confidence import Answer, Confidence


class MemoryCommandsPlugin(BasePlugin):
    name = "memory_commands"
    description = "Aprende e recorda fatos sobre o usuário (memória contínua)"
    triggers = [
        "lembre que", "lembre-se que", "esqueça", "esqueca", "esquece",
        "qual minha", "qual meu", "meu nome é", "meu nome e",
        "meus fatos", "o que você sabe sobre mim", "o que voce sabe sobre mim",
    ]

    def handle(self, text: str, context: dict):
        memory = context["memory"]
        user_id = context["user_id"]
        t = text.lower().strip()

        # Atualizar nome do perfil
        m = re.search(r"meu nome (é|e)\s+(.+)", t)
        if m:
            name = m.group(2).strip(" .!")
            memory.create_or_update_profile(user_id, name=name.title())
            return Answer(f"Prazer, {name.title()}! Vou lembrar seu nome.", Confidence.CONFIRMED)

        # Lembrar fato: "lembre que X é Y"
        m = re.search(r"lembre(?:-se)? que (.+?) (é|e|=)\s*(.+)", t)
        if m:
            key = m.group(1).strip()
            value = m.group(3).strip(" .!")
            memory.remember_fact(user_id, key, value)
            return Answer(f"Anotado: {key} = {value}.", Confidence.CONFIRMED)

        # Esquecer fato: "esqueça X" / "esqueca X" / "esquece X" -- exceto
        # "minha navegação"/"histórico do redcore", que são do
        # plugins/redcore.py (limpar o histórico do navegador do Ultron,
        # não um fato genérico). Sem essa exclusão, "esquece minha
        # navegação" virava "Ok, esqueci sobre 'minha navegação'" (um
        # fato que nunca existiu) em vez de realmente limpar o
        # histórico -- achado numa auditoria de colisão de triggers.
        m = re.search(r"esque(?:ça|ca|ce) (?:que )?(.+)", t)
        if m and not re.search(r"\bnavega[çc][ãa]o\b|\bredcore\b", m.group(1)):
            key = m.group(1).strip(" .!")
            memory.forget_fact(user_id, key)
            return Answer(f"Ok, esqueci sobre '{key}'.", Confidence.CONFIRMED)

        # Perguntar fato: "qual minha X" / "qual meu X"
        m = re.search(r"qual (?:minha|meu) (.+)", t)
        if m:
            key_guess = "minha " + m.group(1).strip(" ?.!")
            value = memory.recall_fact(user_id, key_guess)
            if not value:
                key_guess2 = "meu " + m.group(1).strip(" ?.!")
                value = memory.recall_fact(user_id, key_guess2)
            if value:
                # Foi dito uma vez pelo usuário e guardado; não foi
                # reconfirmado, então fica em SINGLE_SOURCE.
                return Answer(value, Confidence.SINGLE_SOURCE)
            return Answer(
                "Eu ainda não sei disso. Você pode me dizer com 'lembre que minha X é Y'.",
                Confidence.GUESS
            )

        # Listar tudo que sabe
        if "meus fatos" in t or "o que você sabe sobre mim" in t or "o que voce sabe sobre mim" in t:
            profile = memory.get_profile(user_id)
            facts = memory.all_facts(user_id)
            lines = []
            if profile and profile.get("name"):
                lines.append(f"Nome: {profile['name']}")
            for f in facts:
                lines.append(f"{f['key']} = {f['value']}")
            if not lines:
                return Answer("Ainda não sei nada sobre você. Vamos mudar isso!", Confidence.CONFIRMED)
            return Answer("Aqui está o que sei sobre você:\n" + "\n".join(lines), Confidence.CONFIRMED)

        return None
