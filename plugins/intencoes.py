"""
plugins/intencoes.py
=======================
Lado de chat do Sistema de Intenção (automacao/intencoes.py): você
declara um objetivo grande e o Ultron quebra sozinho num checklist e
acompanha o progresso.

O Ultron PLANEJA e ACOMPANHA -- ele não executa "criar trailer"/
"preparar marketing" sozinho (não tem essas capacidades, e fazer sem
revisão seria arriscado). O valor é transformar um objetivo vago numa
lista clara e rastreável.

Comandos:
    "meta: lançar meu jogo esse mês" / "meu objetivo é abrir uma loja online"
    "quero lançar/criar/desenvolver/terminar <coisa>"
    "minhas metas" / "meus objetivos" / "minhas intenções"
    "conclui o passo 2 da meta 1" / "marca o passo 3 da meta 1 como feito"
    "desmarca o passo 2 da meta 1"
    "apaga a meta 1"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

# Criar: prefixo explícito "meta:/objetivo:/minha intenção" OU
# "quero <verbo de projeto>". Evita roubar "quero dormir"/"quero café"
# exigindo um verbo de projeto depois de "quero".
_CRIAR_RE = re.compile(
    r"\b(?:meta|objetivo|inten[çc][ãa]o)\s*:\s*(.+)|"
    r"\b(?:minha\s+meta|meu\s+objetivo|minha\s+inten[çc][ãa]o)\s+(?:é|e|:)\s*(.+)|"
    r"\bquero\s+((?:lan[çc]ar|publicar|criar|desenvolver|construir|terminar|finalizar|montar|abrir|fazer\s+um|fazer\s+uma)\s+.+)",
    re.IGNORECASE,
)
_LISTAR_RE = re.compile(
    # (?!\s+aut[ôo]nomo|\s+pendentes?) -- "meus objetivos AUTÔNOMOS"/
    # "objetivos PENDENTES" são do plugins/modo_autonomo.py (fila do
    # Modo Autônomo), não das metas deste plugin; sem essa exclusão,
    # "meus objetivos" batia primeiro (ordem alfabética de carregamento:
    # intencoes.py vem antes de modo_autonomo.py) e sequestrava o
    # comando errado -- achado numa auditoria sistemática de colisão de
    # triggers (a primeira exclusão só cobria "autônomos", "pendentes"
    # ainda vazava).
    r"\bminhas\s+(?:metas|inten[çc][õo]es)\b|\bmeus\s+objetivos\b(?!\s+(?:aut[ôo]nomos?|pendentes?))|"
    r"\blist[ae]\w*\s+(?:as\s+)?(?:metas|inten[çc][õo]es)\b",
    re.IGNORECASE,
)
_MARCAR_RE = re.compile(
    r"\b(conclui\w*|marc[ae]\w*|termin[ae]\w*|finaliz\w*)\b.*?\bpasso\s+(\d+)\b.*?\bmeta\s+(\d+)\b|"
    r"\b(conclui\w*|marc[ae]\w*)\b.*?\bpasso\s+(\d+)\b(?!.*\bmeta\b)",
    re.IGNORECASE,
)
_DESMARCAR_RE = re.compile(
    r"\bdesmarc\w*\b.*?\bpasso\s+(\d+)\b.*?\bmeta\s+(\d+)\b", re.IGNORECASE
)
_REMOVER_RE = re.compile(r"\b(apag[ae]\w*|remov[ae]\w*|deleta\w*)\s+a\s+meta\s+(\d+)\b", re.IGNORECASE)


class IntencoesPlugin(BasePlugin):
    name = "intencoes"
    description = "Sistema de Intenção: declara um objetivo grande e o Ultron quebra num checklist e acompanha o progresso"
    triggers = ["meta:", "objetivo:", "minhas metas", "meus objetivos", "minhas intenções", "quero lançar", "quero criar"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _DESMARCAR_RE.search(t) or _MARCAR_RE.search(t) or _REMOVER_RE.search(t)
            or _LISTAR_RE.search(t) or _CRIAR_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()
        user_id = context["user_id"]

        m = _DESMARCAR_RE.search(t)
        if m:
            return self._marcar(user_id, int(m.group(2)), int(m.group(1)), feito=False)

        m = _MARCAR_RE.search(t)
        if m:
            if m.group(2) and m.group(3):  # "passo N da meta M"
                return self._marcar(user_id, int(m.group(3)), int(m.group(2)), feito=True)
            if m.group(5):  # "passo N" sem meta -> só funciona se houver 1 meta ativa
                return self._marcar_sem_meta(user_id, int(m.group(5)))

        m = _REMOVER_RE.search(t)
        if m:
            return self._remover(user_id, int(m.group(2)))

        if _LISTAR_RE.search(t):
            return self._listar(user_id)

        m = _CRIAR_RE.search(t)
        if m:
            objetivo = next((g for g in m.groups() if g), "").strip(" .!?")
            return self._criar(context, objetivo)

        return None

    def _criar(self, context: dict, objetivo: str):
        if not objetivo:
            return Answer("Qual é o objetivo? Ex.: 'meta: lançar meu jogo esse mês'.", Confidence.GUESS)
        from automacao import intencoes
        try:
            intencao = intencoes.criar_intencao(context.get("ia_manager"), context["user_id"], objetivo)
        except ValueError as e:
            return Answer(str(e), Confidence.GUESS)
        linhas = [f"{i+1}. {p['descricao']}" for i, p in enumerate(intencao["passos"])]
        return Answer(
            f'Entendi. Pra "{intencao["objetivo"]}", montei este plano (meta #{intencao["id"]}):\n'
            + "\n".join(linhas)
            + f'\n\nEu PLANEJO e ACOMPANHO -- os passos são pra você (ou comandos meus quando '
            f'existirem). Diga "conclui o passo 1 da meta {intencao["id"]}" conforme for '
            f'avançando, ou "minhas metas" pra ver o progresso.',
            Confidence.CONFIRMED,
        )

    def _listar(self, user_id: str):
        from automacao import intencoes
        lista = intencoes.listar_intencoes(user_id)
        if not lista:
            return Answer(
                "Você ainda não tem nenhuma meta. Crie uma com 'meta: <seu objetivo>' "
                "(ex.: 'meta: lançar meu jogo esse mês').",
                Confidence.CONFIRMED,
            )
        blocos = []
        for i in lista:
            feitos, total = intencoes.progresso(i)
            marca = " ✓ concluída" if i["status"] == "concluido" else ""
            passos = "\n".join(
                f"   [{'x' if p['feito'] else ' '}] {j+1}. {p['descricao']}"
                for j, p in enumerate(i["passos"])
            )
            blocos.append(f"Meta #{i['id']} ({feitos}/{total}){marca}: {i['objetivo']}\n{passos}")
        return Answer("Suas metas:\n\n" + "\n\n".join(blocos), Confidence.CONFIRMED)

    def _marcar(self, user_id: str, intencao_id: int, indice: int, feito: bool):
        from automacao import intencoes
        intencao = intencoes.marcar_passo(user_id, intencao_id, indice, feito=feito)
        if not intencao:
            return Answer(
                f"Não achei o passo {indice} da meta {intencao_id}. Diga 'minhas metas' pra ver os números certos.",
                Confidence.GUESS,
            )
        feitos, total = intencoes.progresso(intencao)
        verbo = "Concluí" if feito else "Desmarquei"
        extra = ""
        if intencao["status"] == "concluido":
            extra = f'\n\n🎉 Meta "{intencao["objetivo"]}" 100% concluída! Parabéns.'
        return Answer(
            f'{verbo} o passo {indice} da meta #{intencao_id} ({feitos}/{total} feitos).{extra}',
            Confidence.CONFIRMED,
        )

    def _marcar_sem_meta(self, user_id: str, indice: int):
        from automacao import intencoes
        ativas = [i for i in intencoes.listar_intencoes(user_id) if i["status"] != "concluido"]
        if len(ativas) != 1:
            return Answer(
                "Você tem mais de uma meta -- diga qual, ex.: 'conclui o passo "
                f"{indice} da meta 1'. Veja os números com 'minhas metas'.",
                Confidence.GUESS,
            )
        return self._marcar(user_id, ativas[0]["id"], indice, feito=True)

    def _remover(self, user_id: str, intencao_id: int):
        from automacao import intencoes
        if intencoes.remover_intencao(user_id, intencao_id):
            return Answer(f"Removi a meta #{intencao_id}.", Confidence.CONFIRMED)
        return Answer(f"Não achei nenhuma meta #{intencao_id}.", Confidence.GUESS)
