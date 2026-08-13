"""
automacao/auto_consolidacao.py
==================================
"Ficar mais inteligente sozinho", parte 2: core/knowledge.py já sabia
detectar assuntos recorrentes e consolidá-los em conhecimento próprio
(`Knowledge.consolidate()`), mas isso só acontecia se o usuário pedisse
explicitamente ("consolide o que aprendeu" / `/consolidar`) -- ou seja,
o Ultron só "aprendia por conta própria" se alguém lembrasse de mandar
ele fazer isso. Este módulo roda essa mesma consolidação sozinho, em
segundo plano, de tempos em tempos, igual automacao/aprendizado_autonomo.py
já faz pra pesquisar tópicos novos.

Sempre idempotente e nunca destrutivo: consolidate() só cria/reforça
itens de conhecimento (nunca apaga nada), então rodar automaticamente
não tem risco -- é a mesma ação segura que o usuário já podia disparar
manualmente, só que sem precisar lembrar de pedir.
"""

from automacao import tasks
from automacao.notify import notify
from logs.logger import get_logger

log = get_logger("automacao")


def consolidar_agora(jarvis) -> list:
    """Roda a consolidação uma vez e retorna só os itens GENUINAMENTE
    novos criados nesta chamada (não os que já existiam e só foram
    reforçados de novo) -- comparado por IDs antes/depois, pra não
    notificar repetidamente sobre o mesmo assunto a cada ciclo."""
    antes = {i["id"] for i in jarvis.knowledge.list_knowledge(jarvis.user_id, limit=2000)}
    criados = jarvis.knowledge.consolidate(jarvis.user_id, min_mentions=3)
    return [c for c in criados if c["id"] not in antes]


def _tick(jarvis):
    try:
        novos = consolidar_agora(jarvis)
    except Exception as e:
        log.warning("auto_consolidacao: falha ao consolidar (%s)", e)
        return
    if not novos:
        return
    notify(
        "Ultron consolidou conhecimento (sozinho)",
        f"Percebi {len(novos)} assunto(s) recorrente(s) nas nossas conversas e "
        "guardei como conhecimento próprio, sem você precisar pedir. "
        "Pergunte 'o que você aprendeu' pra ver.",
    )


def iniciar(jarvis):
    """Chamado uma vez no startup do Ultron (core/jarvis.py), mesmo
    padrão de automacao/aprendizado_autonomo.py. No-op se o módulo
    automacao estiver desligado, ou se personalidade.auto_consolidar
    for false."""
    settings = jarvis.settings
    if not settings.is_module_enabled("automacao"):
        return
    if not settings.get("personalidade.auto_consolidar", True):
        return
    horas = settings.get("personalidade.auto_consolidar_intervalo_horas", 3)
    try:
        horas = float(horas)
    except (TypeError, ValueError):
        horas = 3
    intervalo_segundos = max(600, horas * 3600)
    # Primeira consolidação ~10 min depois de abrir (não horas depois) --
    # mesmo raciocínio de aprendizado_autonomo: visível numa sessão normal,
    # não só depois de horas de uso.
    tasks.schedule_recurring(
        "auto_consolidacao", intervalo_segundos, _tick, jarvis, primeiro_delay_segundos=600
    )
