"""
automacao/aprendizado_autonomo.py
=====================================
"Aprender tecnologia nova sozinho" + "aprender linguagem de
programação sozinho": de tempos em tempos (config
personalidade.aprender_tecnologia_intervalo_horas, 24h por padrão),
Ultron escolhe um tópico -- prioridade pros "projetos" que você já
registrou na memória categorizada (memory_items, categoria "project"),
senão alterna entre uma lista de LINGUAGENS DE PROGRAMAÇÃO (com um
prompt mais aprofundado: sintaxe básica, "hello world", pra quando
você pedir pra ele programar em algo novo) e uma lista de tecnologias
gerais -- pesquisa sozinho (Wikipedia; a IA configurada como
alternativa se a Wikipedia não tiver nada), salvando o resultado na
base de CONHECIMENTO ORGÂNICO (core/knowledge.py, mesma tabela usada
por "aprenda que X..." em plugins/learning.py). Avisa por notificação
o que aprendeu.

Nunca repete o mesmo tópico -- cada um pesquisado fica marcado com um
evento próprio na timeline (core/timeline.py) pra não pesquisar de novo.
"""

import json
import urllib.parse
import urllib.request

from automacao import tasks
from automacao.notify import notify
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

_WIKI_API = "https://pt.wikipedia.org/api/rest_v1/page/summary/"

_LINGUAGENS_PROGRAMACAO = [
    "Rust (linguagem de programação)", "Go (linguagem de programação)", "Kotlin",
    "TypeScript", "Swift (linguagem de programação)", "Elixir (linguagem de programação)",
    "Zig (linguagem de programação)", "Julia (linguagem de programação)",
    "Haskell (linguagem de programação)", "Lua (linguagem de programação)",
]

_TOPICOS_PADRAO = [
    "WebAssembly", "Docker (software)", "Kubernetes",
    "GraphQL", "Inteligência artificial generativa", "Computação quântica",
    "Arquitetura de microsserviços", "Rede neural convolucional", "Blockchain",
    "Edge computing", "Computação sem servidor", "Banco de dados vetorial", "WebGPU",
]

_PROMPT_LINGUAGEM = (
    "Explique de forma prática e objetiva (8 a 12 frases) a linguagem de programação {topico}: "
    "pra que ela é mais usada, 2-3 características centrais da sintaxe, e um exemplo bem curto "
    "de código (\"hello world\" ou equivalente simples). O objetivo é eu conseguir escrever um "
    "programa básico nessa linguagem depois de ler isso."
)


def _topico_ja_aprendido(memory, topico: str) -> bool:
    # events_by_type() filtra por tipo direto no SQL -- recent_events(limit=N)
    # pega os últimos N eventos de QUALQUER tipo (mesma tabela compartilhada
    # com visao_continua/habitos/macros/etc.), então "tecnologia_aprendida"
    # podia ficar invisível em dias movimentados, fazendo o mesmo tópico ser
    # pesquisado e notificado de novo (bug real, mesmo padrão já encontrado
    # e corrigido em instagram_auto.py e auto_melhoria.py).
    chave = topico.strip().lower()
    eventos = memory.events_by_type("tecnologia_aprendida", limit=500)
    return any((ev.get("description") or "").strip().lower() == chave for ev in eventos)


def _candidatos_intercalados():
    """Intercala linguagens de programação com tecnologias gerais, em
    vez de esgotar uma lista inteira antes da outra -- assim
    'aprender linguagem de programação sozinho' também progride desde
    o início, não só depois que a lista geral acabar."""
    candidatos = []
    for a, b in zip(_LINGUAGENS_PROGRAMACAO, _TOPICOS_PADRAO):
        candidatos.append((a, True))
        candidatos.append((b, False))
    sobras_linguagem = _LINGUAGENS_PROGRAMACAO[len(_TOPICOS_PADRAO):]
    sobras_geral = _TOPICOS_PADRAO[len(_LINGUAGENS_PROGRAMACAO):]
    candidatos += [(t, True) for t in sobras_linguagem]
    candidatos += [(t, False) for t in sobras_geral]
    return candidatos


def _escolher_topico(jarvis):
    """Retorna (topico, eh_linguagem_de_programacao) ou (None, False)
    se não houver mais nada novo pra pesquisar por enquanto."""
    projetos = [(p["content"], False) for p in jarvis.memory.list_memory(jarvis.user_id, category="project", limit=10)]
    candidatos = projetos + _candidatos_intercalados()
    for topico, eh_linguagem in candidatos:
        if not _topico_ja_aprendido(jarvis.memory, topico):
            return topico, eh_linguagem
    return None, False  # já pesquisou tudo da lista por enquanto


def _buscar_wikipedia(topico: str):
    url = _WIKI_API + urllib.parse.quote(topico)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Ultron/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("extract")
    except Exception:
        return None


def _pesquisar(jarvis, topico: str, eh_linguagem: bool):
    # Linguagens de programação usam um prompt próprio (sintaxe +
    # exemplo de código) direto na IA -- a Wikipedia costuma ter só
    # história/paradigma, não o suficiente pra programar de verdade.
    if eh_linguagem and jarvis.ia_manager is not None:
        try:
            _, resumo = jarvis.ia_manager.chat(_PROMPT_LINGUAGEM.format(topico=topico), history=[])
            if resumo:
                return resumo, "ia"
        except Exception as e:
            log.warning("aprendizado_autonomo: falha ao consultar IA sobre '%s': %s", topico, e)

    resumo = _buscar_wikipedia(topico)
    if resumo:
        return resumo, "wikipedia"
    if jarvis.ia_manager is not None:
        try:
            _, resumo = jarvis.ia_manager.chat(
                f"Explique brevemente (3 a 5 frases) o que é: {topico}", history=[],
            )
            if resumo:
                return resumo, "ia"
        except Exception as e:
            log.warning("aprendizado_autonomo: falha ao consultar IA sobre '%s': %s", topico, e)
    return None, None


def aprender_um_topico(jarvis) -> dict:
    """Aprende UM tópico novo agora (Wikipedia, ou IA como alternativa)
    e salva na base de conhecimento orgânico. Retorna
    {"topico", "fonte", "resumo"} ou None se não havia nada novo pra
    aprender (já pesquisou tudo da lista) ou se a busca falhou (sem
    internet). Usado tanto pelo tick automático em segundo plano quanto
    pelo comando de chat "aprende algo novo" (plugins/autonomia.py),
    pra você conseguir VER isso acontecer na hora em vez de esperar o
    ciclo de 24h."""
    topico, eh_linguagem = _escolher_topico(jarvis)
    if not topico:
        return None
    resumo, fonte = _pesquisar(jarvis, topico, eh_linguagem)
    if not resumo:
        return None
    categoria = "concept" if eh_linguagem else "definition"
    jarvis.knowledge.learn(jarvis.user_id, resumo, source=fonte, category=categoria)
    registrar("tecnologia_aprendida", topico)
    return {"topico": topico, "fonte": fonte, "resumo": resumo}


def _tick(jarvis):
    resultado = aprender_um_topico(jarvis)
    if not resultado:
        return
    notify(
        "Ultron aprendeu algo novo (sozinho)",
        f'Pesquisei sozinho sobre "{resultado["topico"]}" e guardei na minha base de conhecimento. '
        f'Pergunte "o que você aprendeu sobre {resultado["topico"]}" se quiser ver.',
    )


def iniciar(jarvis):
    """Chamado uma vez no startup do Ultron (core/jarvis.py), igual
    automacao/auto_melhoria.py. No-op se o módulo automacao estiver
    desligado, ou se personalidade.aprender_tecnologia for false."""
    settings = jarvis.settings
    if not settings.is_module_enabled("automacao"):
        return
    if not settings.get("personalidade.aprender_tecnologia", True):
        return
    horas = settings.get("personalidade.aprender_tecnologia_intervalo_horas", 24)
    try:
        horas = float(horas)
    except (TypeError, ValueError):
        horas = 24
    intervalo_segundos = max(3600, horas * 3600)
    # Primeiro aprendizado ~5 min depois de abrir o Jarvis (não 24h
    # depois) -- assim ele aprende algo sozinho já no começo da sessão,
    # em vez de nunca fazer nada visível numa sessão normal de minutos.
    tasks.schedule_recurring(
        "aprendizado_autonomo", intervalo_segundos, _tick, jarvis, primeiro_delay_segundos=300
    )
