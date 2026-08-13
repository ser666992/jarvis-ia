"""
automacao/modo_autonomo.py
=============================
"Modo Autônomo": você cadastra objetivos ("organiza meus arquivos de
downloads", "pesquisa novas técnicas de IA") e o Jarvis os executa
SOZINHO quando percebe que o PC está ocioso (sem teclado/mouse por
alguns minutos, ver sistema/ociosidade.py) -- em vez de precisar dizer
"ativa auto: <objetivo>" você mesmo toda vez.

Desligado por padrão (`personalidade.modo_autonomo`, false) -- é um
INTERRUPTOR explícito (mesmo espírito do "botão" que o usuário descreveu:
"Modo Autônomo ⬤ Desativado"), nunca liga sozinho.

NÃO é um mecanismo de execução novo: cada objetivo pendente é entregue
pro MESMO automacao/modo_automatico.py (planeja com IA + executa via
PluginManager.dispatch, respeitando a política de confirmação de
seguranca/permissions.py) -- autonomia aqui é só SOBRE QUANDO disparar
("sozinho, no ócio"), nunca sobre relaxar o que já é seguro fazer.

Só um objetivo por vez, e só quando ocioso -- nunca dois rodando juntos,
nunca no meio do seu uso ativo. Se você voltar a usar o PC no meio de um
ciclo, o ciclo ATUAL termina (os passos já são curtos, ver
modo_automatico.MAX_PASSOS), mas o PRÓXIMO só começa no próximo período
de ócio.

Histórico completo (todo objetivo tentado, com resultado) fica na
timeline (core/timeline.py, eventos "modo_autonomo_*") -- nada roda
"escondido".
"""

from datetime import datetime

from core.database import get_database
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automacao_objetivos_autonomos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    objetivo TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',
    criado_em TEXT NOT NULL,
    executado_em TEXT,
    resultado_resumo TEXT
);
"""

_INTERVALO_TICK_SEGUNDOS = 60
_OCIOSIDADE_PADRAO_MINUTOS = 5
_executando = False  # trava simples -- nunca dois ciclos ao mesmo tempo


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def adicionar_objetivo(user_id: str, objetivo: str) -> dict:
    _ensure_schema()
    objetivo = objetivo.strip()
    if not objetivo:
        raise ValueError("Preciso de um objetivo real pra cadastrar.")
    cursor = get_database().execute(
        "INSERT INTO automacao_objetivos_autonomos (user_id, objetivo, status, criado_em) "
        "VALUES (?,?,'pendente',?)",
        (user_id, objetivo, datetime.now().isoformat()),
    )
    registrar("modo_autonomo_objetivo_cadastrado", objetivo[:100])
    return get_database().query_one(
        "SELECT * FROM automacao_objetivos_autonomos WHERE id=?", (cursor.lastrowid,)
    )


def listar_objetivos(user_id: str, incluir_concluidos: bool = False) -> list:
    _ensure_schema()
    if incluir_concluidos:
        return get_database().query(
            "SELECT * FROM automacao_objetivos_autonomos WHERE user_id=? ORDER BY id",
            (user_id,),
        )
    return get_database().query(
        "SELECT * FROM automacao_objetivos_autonomos WHERE user_id=? AND status='pendente' ORDER BY id",
        (user_id,),
    )


def remover_objetivo(user_id: str, objetivo_id: int) -> bool:
    _ensure_schema()
    existente = get_database().query_one(
        "SELECT id FROM automacao_objetivos_autonomos WHERE user_id=? AND id=?",
        (user_id, objetivo_id),
    )
    if not existente:
        return False
    get_database().execute(
        "DELETE FROM automacao_objetivos_autonomos WHERE user_id=? AND id=?",
        (user_id, objetivo_id),
    )
    return True


def _proximo_pendente(user_id: str):
    _ensure_schema()
    return get_database().query_one(
        "SELECT * FROM automacao_objetivos_autonomos WHERE user_id=? AND status='pendente' "
        "ORDER BY id LIMIT 1",
        (user_id,),
    )


def executar_proximo_objetivo(jarvis) -> dict:
    """Pega o objetivo pendente mais antigo e executa AGORA (mesmo
    motor de modo_automatico.py) -- usado tanto pelo ciclo automático
    (_tick) quanto pelo comando de chat "executa o próximo objetivo
    autônomo" (pra ver acontecer na hora, sem esperar o ócio). Retorna
    {"objetivo": None} se não havia nada pendente."""
    alvo = _proximo_pendente(jarvis.user_id)
    if not alvo:
        return {"objetivo": None}

    from automacao import modo_automatico
    context = jarvis._context()
    relatorio = modo_automatico.executar(jarvis, alvo["objetivo"], context)

    feitos = sum(1 for p in relatorio["passos"] if p["executado"])
    total = len(relatorio["passos"])
    if relatorio["recusa"]:
        status = "recusado"
        resumo = f"Recusado: {relatorio['recusa']}"
    elif total and feitos == total:
        status = "concluido"
        resumo = f"Concluído ({feitos}/{total} passos)."
    elif feitos:
        status = "parcial"
        resumo = f"Parcial ({feitos}/{total} passos) -- parou em: {relatorio['passos'][-1]['resposta']}"
    else:
        status = "falhou"
        resumo = "Nenhum passo executado."

    get_database().execute(
        "UPDATE automacao_objetivos_autonomos SET status=?, executado_em=?, resultado_resumo=? "
        "WHERE id=?",
        (status, datetime.now().isoformat(), resumo, alvo["id"]),
    )
    registrar("modo_autonomo_ciclo", f"{alvo['objetivo'][:80]} -- {status}")
    return {"objetivo": alvo["objetivo"], "status": status, "resumo": resumo, "relatorio": relatorio}


def _tick(jarvis):
    global _executando
    if _executando:
        return  # ciclo anterior ainda rodando (não deveria, mas por segurança)
    settings = jarvis.settings
    if not settings.get("personalidade.modo_autonomo", False):
        return

    from sistema import ociosidade
    limite = settings.get("personalidade.modo_autonomo_ociosidade_minutos", _OCIOSIDADE_PADRAO_MINUTOS)
    try:
        limite = float(limite)
    except (TypeError, ValueError):
        limite = _OCIOSIDADE_PADRAO_MINUTOS
    if not ociosidade.esta_ocioso(limite):
        return

    if not _proximo_pendente(jarvis.user_id):
        return

    _executando = True
    try:
        resultado = executar_proximo_objetivo(jarvis)
    except Exception as e:
        log.warning("modo_autonomo: falha no ciclo (%s)", e)
        return
    finally:
        _executando = False

    if resultado.get("objetivo"):
        from automacao.notify import notify
        from core.personality import NOME
        notify(
            f"{NOME} trabalhou sozinho (modo autônomo)",
            f'Objetivo: "{resultado["objetivo"]}" -- {resultado["resumo"]}',
        )


def iniciar(jarvis):
    """Chamado uma vez no startup, mesmo padrão das outras rotinas
    autônomas (automacao/sonhos.py etc.) -- mas o próprio `_tick` só faz
    alguma coisa se `personalidade.modo_autonomo` estiver ligado, então
    isso é seguro de sempre agendar (o interruptor real é o config/
    comando de chat, não isso aqui)."""
    if not jarvis.settings.is_module_enabled("automacao"):
        return
    from automacao import tasks
    tasks.schedule_recurring("modo_autonomo", _INTERVALO_TICK_SEGUNDOS, _tick, jarvis)
