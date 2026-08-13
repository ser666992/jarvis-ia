"""
automacao/auto_melhoria.py
==============================
Auto-melhoria: de tempos em tempos, enquanto o Ultron estiver aberto,
verifica se o mesmo pedido caiu no fallback ("não sei fazer isso")
repetidas vezes -- e se sim, gera sozinho um rascunho de habilidade
pra aquele pedido (core/skill_forge.py) e avisa você, por notificação,
que pode aprovar ou rejeitar.

Nunca ativa nada sozinho: só gera o rascunho e notifica -- a mesma
regra de aprovação humana de plugins/skill_forge.py.

Controlado por config.json:
    personalidade.auto_melhoria (bool, default true)
    personalidade.auto_melhoria_intervalo_horas (int, default 4)

Fonte dos dados: core/jarvis.py grava um evento "message_processed" a
cada resposta, incluindo um trecho do texto original quando a resposta
veio do fallback (plugin=fallback). Esta rotina lê os últimos eventos,
conta quantas vezes o MESMO texto (normalizado) apareceu sem resposta,
e só considera candidato quem se repetiu pelo menos MINIMO_REPETICOES
vezes -- evita gerar rascunho pra uma pergunta feita uma vez só.

Cada pedido só é sugerido uma vez -- fica marcado com um evento próprio
("auto_melhoria_sugestao") pra não insistir no mesmo pedido a cada
rodada. Se a geração falhar (ex.: IA temporariamente indisponível),
NÃO marca como sugerido, pra tentar de novo na próxima rodada.
"""

import ast
import re
from collections import Counter

from automacao import tasks
from automacao.notify import notify
from core import skill_forge
from logs.logger import get_logger

log = get_logger("automacao")

MINIMO_REPETICOES = 3
EVENTOS_ANALISADOS = 500

_FALLBACK_TEXTO_RE = re.compile(r"plugin=fallback.*texto=(.+)$")


def _candidatos_de_fallback(memory):
    # events_by_type() filtra por tipo direto no SQL -- recent_events(limit=N)
    # pega os últimos N eventos de QUALQUER tipo (todos os módulos escrevem
    # na mesma tabela), então "message_processed" podia ficar diluído/fora
    # da janela em dias movimentados de visao_continua/habitos/macros.
    eventos = memory.events_by_type("message_processed", limit=EVENTOS_ANALISADOS)
    contagem = Counter()
    originais = {}
    for ev in eventos:
        if ev.get("event_type") != "message_processed":
            continue
        m = _FALLBACK_TEXTO_RE.search(ev.get("description") or "")
        if not m:
            continue
        try:
            texto = ast.literal_eval(m.group(1))
        except (ValueError, SyntaxError):
            continue
        chave = texto.strip().lower()
        if not chave:
            continue
        contagem[chave] += 1
        originais.setdefault(chave, texto)
    return contagem, originais


def _ja_sugerido(memory, chave: str) -> bool:
    # Mesmo motivo de _candidatos_de_fallback: filtrar por tipo direto no
    # SQL evita que a marca "já sugerido" fique invisível atrás de eventos
    # de outros módulos -- sem isso, o mesmo pedido podia ser "descoberto"
    # de novo e gerar um rascunho de habilidade DUPLICADO, notificando o
    # usuário repetidamente sobre a mesma coisa.
    eventos = memory.events_by_type("auto_melhoria_sugestao", limit=EVENTOS_ANALISADOS)
    return any(ev.get("description") == chave for ev in eventos)


def _tick(jarvis):
    if jarvis.ia_manager is None:
        return
    memory = jarvis.memory
    contagem, originais = _candidatos_de_fallback(memory)
    if not contagem:
        return

    for chave, vezes in contagem.most_common():
        if vezes < MINIMO_REPETICOES:
            break
        if _ja_sugerido(memory, chave):
            continue

        texto_original = originais[chave]
        try:
            resultado = skill_forge.gerar_habilidade(jarvis.ia_manager, texto_original)
        except skill_forge.SkillForgeError as e:
            log.warning("auto_melhoria: falha ao gerar habilidade para '%s': %s", chave, e)
            return

        memory.log_event("auto_melhoria_sugestao", chave)
        notify(
            "Ultron aprendeu algo novo (sozinho)",
            f'Notei que "{texto_original}" apareceu {vezes}x sem eu saber responder. '
            f'Criei um rascunho de habilidade pra isso: "{resultado["slug"]}". Diga '
            f'"aprova a habilidade {resultado["slug"]}" pra ativar, ou "rejeita a '
            f'habilidade {resultado["slug"]}" pra descartar.',
        )
        return  # só um rascunho por rodada, pra não gerar vários de uma vez


def iniciar(jarvis):
    """Chamado uma vez no startup do Ultron (core/jarvis.py) -- agenda
    a checagem periódica enquanto o processo estiver vivo. Sem efeito
    (no-op) se o módulo automacao estiver desligado, ou se
    personalidade.auto_melhoria estiver false em config.json."""
    settings = jarvis.settings
    if not settings.is_module_enabled("automacao"):
        return
    if not settings.get("personalidade.auto_melhoria", True):
        return
    horas = settings.get("personalidade.auto_melhoria_intervalo_horas", 4)
    try:
        horas = float(horas)
    except (TypeError, ValueError):
        horas = 4
    intervalo_segundos = max(600, horas * 3600)
    tasks.schedule_recurring("auto_melhoria", intervalo_segundos, _tick, jarvis)
