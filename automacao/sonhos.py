"""
automacao/sonhos.py
======================
"Sistema de sonhos": de tempos em tempos (config
personalidade.sonhos_intervalo_horas, 2h por padrão -- mais frequente
e livre de propósito que automacao/auto_melhoria.py, 4h, e
automacao/aprendizado_autonomo.py, 24h), Ultron inventa e TESTA sozinho
uma ideia pequena -- uma habilidade nova -- sem que você tenha pedido,
e só DEPOIS te apresenta. Nunca ativa nada sozinho: mesma regra de
aprovação humana de core/skill_forge.py.

"Testa sozinho" quer dizer: além da validação de sintaxe que
core/skill_forge.py já faz sempre, a habilidade gerada é carregada de
verdade e tem handle() chamado com uma mensagem de teste genérica
ANTES de ser apresentada, usando os objetos reais de memória/
conhecimento do Ultron (só com um user_id isolado, "_sonho_autoteste",
pra não misturar com os dados do usuário de verdade). Se quebrar no
teste, o sonho é descartado silenciosamente -- não incomoda você com
um rascunho que nem carrega direito.

Puxa contexto de memória/hábitos (o que o usuário anda fazendo,
hábitos observados em automacao/habitos.py) pra tentar inventar algo
relevante, não só aleatório.
"""

import importlib.util
import inspect
import os
import random

from automacao import tasks
from automacao.notify import notify
from core import skill_forge
from core.plugin_manager import BasePlugin
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

_INTERVALO_PADRAO_HORAS = 2

# Cada prompt é uma direção pra um SONHO -- uma FUNÇÃO/CAPACIDADE NOVA e
# concreta que o Ultron passa a ter (um plugin que FAZ algo por comando),
# não só um factoide. O reforço "capacidade que EXECUTA uma ação" é de
# propósito: sem isso, os sonhos tendiam a virar plugins que só respondem
# texto genérico (baixo valor). Cada um vira um rascunho pendente que só
# entra em uso depois da sua aprovação (core/skill_forge.py).
_PROMPTS_CRIATIVOS = [
    "Invente uma FUNÇÃO NOVA e concreta pro Ultron -- uma capacidade que EXECUTA uma ação "
    "útil por comando (calcular algo, converter, formatar, gerar, organizar, resumir), não "
    "só responder um texto fixo. Deve ser algo que ninguém pediu, mas que ajudaria no dia a dia.",
    "Pensando nos hábitos e projetos do usuário, invente uma FUNÇÃO que automatize uma "
    "tarefa repetitiva dele e economize tempo -- algo acionável por uma frase de comando.",
    "Invente uma FUNÇÃO utilitária que faça uma transformação concreta (ex.: gerar senha "
    "forte, converter unidades, calcular datas/prazos, formatar texto/JSON, criar um "
    "checklist a partir de um objetivo) -- algo que produz um resultado real, não conversa.",
    "Invente uma FERRAMENTA nova relacionada a algum interesse/projeto do usuário -- uma "
    "capacidade concreta que ele usaria de verdade, acionada por comando.",
    # Puxa dos OBJETIVOS ativos (Sistema de Intenção) e das CURIOSIDADES
    # detectadas -- ver _contexto_usuario(), que injeta esse contexto no
    # prompt. Assim o "sonho" tende a ser relevante ao que o usuário está
    # tentando alcançar agora, em vez de puramente aleatório.
    "Olhando os OBJETIVOS atuais do usuário, invente uma FUNÇÃO concreta que ajudaria a "
    "avançar em um deles -- uma capacidade acionável, não um conselho em texto.",
    "Se houver algum PADRÃO/ANOMALIA que o Ultron notou (erro recorrente, disco enchendo, "
    "etc.), invente uma FUNÇÃO que ajude a lidar com isso de forma prática e automatizável.",
]


def _contexto_usuario(jarvis) -> str:
    """Contexto pra 'sonhar' algo relevante: memória + hábitos + os
    OBJETIVOS ativos do usuário (Sistema de Intenção) + as CURIOSIDADES
    que o Ultron detectou (tendências/anomalias reais). Antes só puxava
    memória e hábitos -- a atualização pedida foi conectar os sonhos ao
    que o usuário está de fato tentando fazer e ao que o sistema andou
    percebendo, pra as ideias inventadas serem menos aleatórias e mais
    úteis. Cada fonte degrada graciosamente (try/except): uma indisponível
    nunca impede o sonho."""
    resumo = jarvis.memory.get_context_summary(jarvis.user_id)
    partes = [resumo]

    try:
        from automacao import habitos
        h = habitos.resumo("pc", dias=7, top_n=5)
        if h:
            partes.append(h)
    except Exception:
        pass

    try:
        from automacao import intencoes
        objetivos = intencoes.resumo_para_prompt(jarvis.user_id)
        if objetivos:
            partes.append(objetivos)
    except Exception:
        pass

    try:
        from sistema import curiosidade
        findings = curiosidade.analisar()
        if findings:
            partes.append("Padrões/anomalias que o Ultron notou: " + "; ".join(f["texto"] for f in findings[:3]))
    except Exception:
        pass

    return "\n\n".join(partes)


def _testar_habilidade_gerada(caminho: str, jarvis) -> bool:
    """Carrega a habilidade gerada de verdade e chama handle() com uma
    mensagem de teste genérica, usando os objetos REAIS de memória/
    conhecimento (user_id isolado) -- se lançar exceção, o sonho é
    descartado antes de incomodar o usuário com um rascunho quebrado."""
    try:
        nome_modulo = f"jarvis_sonho_{os.path.basename(caminho)[:-3]}"
        spec = importlib.util.spec_from_file_location(nome_modulo, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    except Exception as e:
        log.warning("sonho descartado -- falhou ao carregar pra teste: %s", e)
        return False

    contexto_teste = {
        "memory": jarvis.memory, "knowledge": jarvis.knowledge,
        "knowledge_base": jarvis.knowledge_base, "user_id": "_sonho_autoteste",
        "history": [], "ia_manager": jarvis.ia_manager,
        "reload_plugins": lambda: None, "jarvis": jarvis,
    }
    for _, obj in inspect.getmembers(modulo, inspect.isclass):
        if issubclass(obj, BasePlugin) and obj is not BasePlugin:
            try:
                obj().handle("teste genérico de funcionamento", contexto_teste)
            except Exception as e:
                log.warning("sonho descartado -- falhou no autoteste: %s", e)
                return False
            return True
    return False


def sonhar_uma_habilidade(jarvis) -> dict:
    """Inventa E TESTA uma habilidade nova agora, a partir do contexto
    do usuário. Retorna o resultado do skill_forge (slug/caminho/etc.)
    se a habilidade passou no autoteste e virou um rascunho pendente,
    ou None se não deu (sem IA configurada, falha ao gerar, ou o
    rascunho não passou no autoteste). Usado tanto pelo tick automático
    quanto pelo comando de chat "inventa uma habilidade"
    (plugins/autonomia.py) -- pra você ver isso acontecer na hora em
    vez de esperar o ciclo de 2h.

    NUNCA ativa nada sozinho: o resultado é sempre um RASCUNHO pendente
    esperando sua aprovação, mesma regra de core/skill_forge.py."""
    if jarvis.ia_manager is None:
        return None
    prompt_base = random.choice(_PROMPTS_CRIATIVOS)
    contexto = _contexto_usuario(jarvis)
    pedido = f"{prompt_base}\n\nContexto sobre o usuário (pra personalizar, se fizer sentido):\n{contexto}"

    try:
        resultado = skill_forge.gerar_habilidade(
            jarvis.ia_manager, pedido, nome_sugerido=f"sonho_{random.randint(1000, 9999)}"
        )
    except skill_forge.SkillForgeError as e:
        log.warning("sonhos: falha ao gerar ideia: %s", e)
        return None

    if not _testar_habilidade_gerada(resultado["caminho"], jarvis):
        skill_forge.rejeitar_habilidade(resultado["slug"])
        return None

    registrar("sonho_apresentado", resultado["slug"])
    return resultado


def _tick(jarvis):
    resultado = sonhar_uma_habilidade(jarvis)
    if not resultado:
        return
    notify(
        "Ultron sonhou com uma ideia (sozinho)",
        f'Inventei e já testei uma habilidade nova: "{resultado["slug"]}" -- passou no autoteste '
        f'e está esperando sua aprovação. Diga "aprova a habilidade {resultado["slug"]}" pra '
        f'ativar, ou "rejeita a habilidade {resultado["slug"]}" pra descartar.',
    )


def iniciar(jarvis):
    settings = jarvis.settings
    if not settings.is_module_enabled("automacao"):
        return
    if not settings.get("personalidade.sonhos", True):
        return
    horas = settings.get("personalidade.sonhos_intervalo_horas", _INTERVALO_PADRAO_HORAS)
    try:
        horas = float(horas)
    except (TypeError, ValueError):
        horas = _INTERVALO_PADRAO_HORAS
    intervalo_segundos = max(1800, horas * 3600)
    # Primeira "ideia sonhada" ~10 min depois de abrir (não 2h depois),
    # pra o Jarvis inventar algo sozinho já no começo da sessão. Um
    # pouco depois do aprendizado_autonomo (5 min) de propósito, pra não
    # disparar duas chamadas pesadas de IA exatamente ao mesmo tempo.
    tasks.schedule_recurring(
        "sonhos", intervalo_segundos, _tick, jarvis, primeiro_delay_segundos=600
    )
