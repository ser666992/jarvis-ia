"""
plugins/skill_forge.py
=========================
Comandos de chat pra pedir ao Ultron que crie uma habilidade nova
(plugin) ou um programa (script autocontido) sozinho, usando a IA
configurada -- ver core/skill_forge.py pro motor de geração em si.

Habilidades geradas NUNCA entram em uso sozinhas: ficam como rascunho
em plugins/pendentes/ até você dizer "aprova a habilidade <nome>" (ou
"rejeita a habilidade <nome>" pra descartar). Programas gerados também
nunca rodam sozinhos: precisam de "roda o programa <nome>, confirmo".

Comandos:
    "aprenda a converter moedas" / "cria uma habilidade que me diz o
    clima" -> gera um rascunho de plugin, pede aprovação
    "aprova a habilidade <nome>" / "rejeita a habilidade <nome>"
    "quais habilidades estão pendentes"
    "cria um programa que organiza meus arquivos por data" -> gera um
    script, pede confirmação pra rodar
    "roda o programa <nome>, confirmo" / "quais programas você criou"
"""

import os
import re

from core import skill_forge
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from seguranca.permissions import PermissionDenied, confirmado_pela_frase_ou_config

_LEARN_RE = re.compile(r"\baprend[ae]\w*\s+a\s+(.+)", re.IGNORECASE)
_CREATE_SKILL_RE = re.compile(
    r"\bcri[ae]\w*\s+(?:uma\s+)?(?:nova\s+)?habilidade\s+(?:que|pra|para)\s+(.+)|"
    r"\bcri[ae]\w*\s+um\s+plugin\s+(?:que|pra|para)\s+(.+)",
    re.IGNORECASE,
)
_CREATE_PROGRAM_RE = re.compile(
    r"\bcri[ae]\w*\s+um[a]?\s+(?:programa|app|aplicativo|script)\s+(?:que|pra|para)\s+(.+)",
    re.IGNORECASE,
)
_CREATE_GAME_RE = re.compile(
    r"\bcri[ae]\w*\s+um\s+jogo\s+(?:que\s+seja\s+|que\s+|de\s+|sobre\s+|tipo\s+)?(.+)",
    re.IGNORECASE,
)
_PASSADO_CRIACAO_RE = r"(criou|criei|criados?|gerou|gerei|gerados?)"
_LIST_GAMES_RE = re.compile(
    rf"\bjogo\w*\b.*\b{_PASSADO_CRIACAO_RE}\b|\b{_PASSADO_CRIACAO_RE}\b.*\bjogo\w*\b|"
    r"\blist[ae]\w*\b.*\bjogo\w*\b",
    re.IGNORECASE,
)
_APPROVE_RE = re.compile(r"\b(aprov[ae]|ativ[ae])\w*\b.*?\bhabilidade\b\s*(.*)", re.IGNORECASE)
_REJECT_RE = re.compile(r"\b(rejeit[ae]|descart[ae]|apag[ae])\w*\b.*?\bhabilidade\b\s*(.*)", re.IGNORECASE)
_LIST_PENDING_RE = re.compile(
    r"\bhabilidade\w*\b.*\bpendente\w*\b|\bpendente\w*\b.*\bhabilidade\w*\b", re.IGNORECASE
)
_RUN_PROGRAM_RE = re.compile(r"\b(rod[ae]|execut[ae])\w*\b.*?\bprograma\b\s*(.*)", re.IGNORECASE)
_LIST_PROGRAMS_RE = re.compile(
    rf"\bprograma\w*\b.*\b{_PASSADO_CRIACAO_RE}\b|\b{_PASSADO_CRIACAO_RE}\b.*\bprograma\w*\b|"
    r"\blist[ae]\w*\b.*\bprograma\w*\b",
    re.IGNORECASE,
)
_CONFIRM_WORD_RE = re.compile(r"\bconfirmo\b|\btenho certeza\b|\bpode rodar\b|\bpode executar\b", re.IGNORECASE)


def _extrair_alvo(resto: str) -> str:
    alvo = resto.strip(" ,.!?")
    alvo = re.sub(r"^(a|o|chamada|chamado|de nome|nome)\s+", "", alvo, flags=re.IGNORECASE).strip()
    alvo = _CONFIRM_WORD_RE.sub("", alvo).strip(" ,.!?")
    return skill_forge.slugify(alvo) if alvo else ""


class SkillForgePlugin(BasePlugin):
    name = "skill_forge"
    description = "Cria habilidades (plugins) e programas novos sozinho, sob aprovação/confirmação"
    triggers = [
        "aprenda a", "cria uma habilidade", "cria um plugin", "cria uma nova habilidade",
        "cria um programa", "cria um app", "cria um script", "cria um jogo",
        "aprova a habilidade", "ativa a habilidade", "rejeita a habilidade",
        "descarta a habilidade", "habilidades pendentes",
        "roda o programa", "executa o programa", "programas criados", "programas gerados",
        "jogos criados", "jogos gerados",
    ]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _APPROVE_RE.search(t) or _REJECT_RE.search(t) or _LIST_PENDING_RE.search(t)
            or _RUN_PROGRAM_RE.search(t) or _LIST_PROGRAMS_RE.search(t) or _LIST_GAMES_RE.search(t)
            or _CREATE_GAME_RE.search(t) or _CREATE_PROGRAM_RE.search(t)
            or _CREATE_SKILL_RE.search(t) or _LEARN_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()
        ia_manager = context.get("ia_manager")

        m = _APPROVE_RE.search(t)
        if m:
            return self._aprovar(_extrair_alvo(m.group(2)), context)

        m = _REJECT_RE.search(t)
        if m:
            return self._rejeitar(_extrair_alvo(m.group(2)))

        if _LIST_PENDING_RE.search(t):
            return self._listar_pendentes()

        m = _RUN_PROGRAM_RE.search(t)
        if m:
            resto = m.group(2)
            confirmado = confirmado_pela_frase_ou_config(bool(_CONFIRM_WORD_RE.search(resto)))
            return self._rodar_programa(_extrair_alvo(resto), confirmado, ia_manager)

        if _LIST_PROGRAMS_RE.search(t) or _LIST_GAMES_RE.search(t):
            return self._listar_programas()

        m = _CREATE_GAME_RE.search(t)
        if m:
            return self._criar_jogo(m.group(1), ia_manager)

        m = _CREATE_PROGRAM_RE.search(t)
        if m:
            return self._criar_programa(m.group(1), ia_manager)

        m = _CREATE_SKILL_RE.search(t)
        if m:
            pedido = m.group(1) or m.group(2)
            return self._criar_habilidade(pedido, ia_manager)

        m = _LEARN_RE.search(t)
        if m:
            return self._criar_habilidade(m.group(1), ia_manager)

        return None

    def _criar_habilidade(self, pedido: str, ia_manager):
        try:
            resultado = skill_forge.gerar_habilidade(ia_manager, pedido)
        except skill_forge.SkillForgeError as e:
            return Answer(str(e), Confidence.GUESS)
        avisos = ""
        if resultado["avisos"]:
            avisos = "\n\nAtenção ao revisar -- o código usa: " + "; ".join(resultado["avisos"]) + "."
        return Answer(
            f'Criei um rascunho de habilidade chamado "{resultado["slug"]}" '
            f'({resultado["caminho"]}). Ela AINDA NÃO está ativa -- dê uma olhada '
            f'no arquivo e diga "aprova a habilidade {resultado["slug"]}" pra ativar, '
            f'ou "rejeita a habilidade {resultado["slug"]}" pra descartar.{avisos}',
            Confidence.GUESS,
        )

    def _criar_programa(self, pedido: str, ia_manager):
        try:
            resultado = skill_forge.gerar_programa(ia_manager, pedido)
        except skill_forge.SkillForgeError as e:
            return Answer(str(e), Confidence.GUESS)
        avisos = ""
        if resultado["avisos"]:
            avisos = "\n\nAtenção ao revisar -- o código usa: " + "; ".join(resultado["avisos"]) + "."
        return Answer(
            f'Criei o programa "{resultado["slug"]}" ({resultado["caminho"]}). '
            f'Dá uma olhada no código antes de rodar. Diga "roda o programa '
            f'{resultado["slug"]}, confirmo" quando quiser executar.{avisos}',
            Confidence.GUESS,
        )

    def _criar_jogo(self, pedido: str, ia_manager):
        try:
            resultado = skill_forge.gerar_jogo(ia_manager, pedido)
        except skill_forge.SkillForgeError as e:
            return Answer(str(e), Confidence.GUESS)
        avisos = ""
        if resultado["avisos"]:
            avisos = "\n\nAtenção ao revisar -- o código usa: " + "; ".join(resultado["avisos"]) + "."
        design = resultado.get("design") or {}
        titulo = design.get("titulo") or resultado["slug"]
        lore = design.get("lore") or ""
        niveis = design.get("niveis") or []
        modo_3d = resultado.get("modo") == "3d"
        motor = "ursina (3D)" if modo_3d else "Pygame"
        dependencia = "'ursina' (pip install ursina)" if modo_3d else "'pygame' (pip install pygame)"
        linhas = [f'Criei o jogo "{titulo}" ({resultado["caminho"]}), usando {motor}.']
        if lore:
            linhas.append(f"Lore: {lore}")
        if niveis:
            linhas.append(f"{len(niveis)} nível(is) com dificuldade crescente.")
        linhas.append(
            f'Diga "roda o programa {resultado["slug"]}, confirmo" quando quiser jogar '
            f"(precisa de {dependencia} instalado).{avisos}"
        )
        return Answer("\n".join(linhas), Confidence.GUESS)

    def _aprovar(self, slug: str, context: dict):
        if not slug:
            return Answer("Aprovar qual habilidade? Diga o nome do rascunho.", Confidence.GUESS)
        try:
            skill_forge.aprovar_habilidade(slug)
        except (FileNotFoundError, skill_forge.SkillForgeError) as e:
            return Answer(str(e), Confidence.GUESS)
        recarregar = context.get("reload_plugins")
        if recarregar:
            try:
                recarregar()
            except Exception as e:
                return Answer(
                    f'Habilidade "{slug}" aprovada, mas houve um erro ao recarregar: {e}. '
                    "Reinicie o Ultron pra ela entrar em uso.",
                    Confidence.GUESS,
                )
        return Answer(f'Habilidade "{slug}" aprovada e já está ativa.', Confidence.CONFIRMED)

    def _rejeitar(self, slug: str):
        if not slug:
            return Answer("Rejeitar qual habilidade? Diga o nome do rascunho.", Confidence.GUESS)
        if skill_forge.rejeitar_habilidade(slug):
            return Answer(f'Descartei o rascunho da habilidade "{slug}".', Confidence.CONFIRMED)
        return Answer(f'Não achei nenhum rascunho pendente chamado "{slug}".', Confidence.GUESS)

    def _listar_pendentes(self):
        pendentes = skill_forge.listar_habilidades_pendentes()
        if not pendentes:
            return Answer("Não há nenhuma habilidade pendente de aprovação no momento.", Confidence.CONFIRMED)
        lista = "\n".join(f"- {p}" for p in pendentes)
        return Answer(f"Habilidades pendentes de aprovação:\n{lista}", Confidence.CONFIRMED)

    def _listar_programas(self):
        programas = skill_forge.listar_programas()
        if not programas:
            return Answer("Ainda não criei nenhum programa.", Confidence.CONFIRMED)
        lista = "\n".join(f"- {p}" for p in programas)
        return Answer(f"Programas já criados:\n{lista}", Confidence.CONFIRMED)

    def _rodar_programa(self, slug: str, confirmado: bool, ia_manager=None):
        if not slug:
            return Answer("Rodar qual programa? Diga o nome.", Confidence.GUESS)
        if not confirmado:
            return Answer(
                f'Rodar código gerado automaticamente exige confirmação -- tem certeza '
                f'que quer rodar "{slug}"? Diga "roda o programa {slug}, confirmo".',
                Confidence.GUESS,
            )
        try:
            resultado = skill_forge.rodar_programa(slug, confirmed=True)
        except FileNotFoundError as e:
            return Answer(str(e), Confidence.GUESS)
        except PermissionDenied as e:
            return Answer(str(e), Confidence.GUESS)
        if resultado.get("timeout"):
            return Answer(
                f'O programa "{slug}" foi encerrado automaticamente por exceder o tempo '
                'limite de segurança sem terminar sozinho (isso mata o processo, não deixa '
                'rodando escondido). Se for um jogo, o limite já é bem maior (1h) -- se mesmo '
                'assim excedeu, ou se não é um jogo e devia ter terminado sozinho, revise o '
                'código gerado.',
                Confidence.GUESS,
            )
        saida = resultado["stdout"].strip() or "(sem saída)"
        if resultado["returncode"] != 0:
            erro = resultado["stderr"].strip() or saida
            mensagem = (
                f'O programa "{slug}" terminou com erro (código {resultado["returncode"]}):\n{erro}'
            )
            if ia_manager is not None:
                try:
                    caminho = os.path.join(skill_forge.PROGRAMS_DIR, f"{slug}.py")
                    correcao = skill_forge.gerar_correcao_programa(ia_manager, caminho, erro)
                    mensagem += (
                        f'\n\nJá corrigi o programa (sobrescrevi "{correcao["slug"]}.py" com a versão '
                        f'corrigida). Diga "roda o programa {slug}, confirmo" de novo pra tentar.'
                    )
                except skill_forge.SkillForgeError:
                    pass
            return Answer(mensagem, Confidence.GUESS)
        return Answer(f'Programa "{slug}" executado:\n{saida}', Confidence.CONFIRMED)
