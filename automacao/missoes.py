"""Motor persistente de missões autônomas do Neutron."""

import json
import re
from datetime import datetime

from core.confidence import Confidence
from core.database import get_database
from core.timeline import registrar

MAX_TENTATIVAS = 2
_executando = False
_RISCO_ALTO = re.compile(
    r"\b(apag|delet|remov|format|desinstal|compr|pag|transfer|public|post|"
    r"envi|mand|senha|credencial|encerr|deslig|reinici)\w*", re.IGNORECASE)
_RISCO_MEDIO = re.compile(
    r"\b(instal|baix|alter|edit|mov|renome|login|conect)\w*", re.IGNORECASE)
_RECURSAO = re.compile(r"\b(miss[aã]o|modo\s+autom[aá]tico|ativa\s+auto)\b", re.IGNORECASE)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automacao_missoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    objetivo TEXT NOT NULL,
    passos TEXT NOT NULL,
    status TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    limite_tentativas INTEGER NOT NULL DEFAULT 2
);
"""


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def classificar_risco(comando: str) -> str:
    if _RISCO_ALTO.search(comando):
        return "alto"
    if _RISCO_MEDIO.search(comando):
        return "medio"
    return "baixo"


def _decode(row):
    if not row:
        return None
    row["passos"] = json.loads(row["passos"])
    return row


def obter(user_id: str, mission_id: int):
    _ensure_schema()
    return _decode(get_database().query_one(
        "SELECT * FROM automacao_missoes WHERE user_id=? AND id=?",
        (user_id, mission_id)))


def listar(user_id: str, incluir_finalizadas=False):
    _ensure_schema()
    sql = "SELECT * FROM automacao_missoes WHERE user_id=?"
    params = [user_id]
    if not incluir_finalizadas:
        sql += " AND status NOT IN ('concluida','cancelada')"
    sql += " ORDER BY id DESC"
    return [_decode(row) for row in get_database().query(sql, tuple(params))]


def criar(jarvis, objetivo: str) -> dict:
    from automacao.modo_automatico import planejar
    _ensure_schema()
    objetivo = objetivo.strip()
    if not objetivo:
        raise ValueError("A missão precisa de um objetivo.")
    plano = planejar(jarvis, objetivo)
    if plano.get("recusa") or not plano.get("passos"):
        raise ValueError(plano.get("recusa") or "Não consegui criar um plano executável.")
    passos = []
    for comando in plano["passos"]:
        risco = classificar_risco(comando)
        passos.append({
            "comando": comando, "risco": risco, "status": "aguardando",
            "aprovado": risco != "alto", "tentativas": 0, "evidencia": "",
        })
    agora = datetime.now().isoformat()
    cursor = get_database().execute(
        "INSERT INTO automacao_missoes "
        "(user_id,objetivo,passos,status,criado_em,atualizado_em,limite_tentativas) "
        "VALUES (?,?,?,'pronta',?,?,?)",
        (jarvis.user_id, objetivo, json.dumps(passos, ensure_ascii=False),
         agora, agora, MAX_TENTATIVAS))
    registrar("missao_criada", objetivo[:100])
    return obter(jarvis.user_id, cursor.lastrowid)


def _save(mission):
    get_database().execute(
        "UPDATE automacao_missoes SET passos=?,status=?,atualizado_em=? WHERE id=? AND user_id=?",
        (json.dumps(mission["passos"], ensure_ascii=False), mission["status"],
         datetime.now().isoformat(), mission["id"], mission["user_id"]))
    return mission


def aprovar_passo(user_id: str, mission_id: int, indice: int):
    mission = obter(user_id, mission_id)
    if not mission or not 1 <= indice <= len(mission["passos"]):
        return None
    mission["passos"][indice - 1]["aprovado"] = True
    if mission["status"] == "aguardando_aprovacao":
        mission["status"] = "pronta"
    return _save(mission)


def pausar(user_id: str, mission_id: int, pausada=True):
    mission = obter(user_id, mission_id)
    if not mission:
        return None
    mission["status"] = "pausada" if pausada else "pronta"
    return _save(mission)


def cancelar(user_id: str, mission_id: int):
    mission = obter(user_id, mission_id)
    if not mission:
        return None
    mission["status"] = "cancelada"
    return _save(mission)


def executar_proximo(jarvis, mission_id: int) -> dict:
    mission = obter(jarvis.user_id, mission_id)
    if not mission:
        return {"executado": False, "motivo": "missão não encontrada"}
    if mission["status"] in ("pausada", "cancelada", "concluida"):
        return {"executado": False, "motivo": f"missão {mission['status']}"}
    pendentes = [
        (i, step) for i, step in enumerate(mission["passos"])
        if step["status"] not in ("concluido", "ignorado")]
    if not pendentes:
        mission["status"] = "concluida"
        _save(mission)
        return {"executado": False, "motivo": "missão concluída", "missao": mission}
    index, step = pendentes[0]
    if step["risco"] == "alto" and not step["aprovado"]:
        mission["status"] = "aguardando_aprovacao"
        _save(mission)
        return {"executado": False, "motivo": "aguardando aprovação",
                "passo": index + 1, "comando": step["comando"]}
    if _RECURSAO.search(step["comando"]):
        step.update(status="bloqueado", evidencia="Recursão autônoma não permitida.")
        mission["status"] = "bloqueada"
        _save(mission)
        return {"executado": False, "motivo": step["evidencia"], "passo": index + 1}

    step["tentativas"] += 1
    execution_command = step["comando"]
    if step["risco"] == "alto" and step["aprovado"]:
        # A aprovação pertence a este passo específico e equivale à
        # confirmação explícita exigida pelos plugins destrutivos.
        execution_command += ", confirmo"
    try:
        _, answer = jarvis.plugins.dispatch(execution_command, jarvis._context())
    except Exception as error:
        answer = None
        evidence = f"erro: {error}"
    else:
        evidence = answer.text if answer else "nenhuma capacidade reconheceu o comando"
    success = bool(answer and answer.confidence > Confidence.GUESS)
    step["evidencia"] = evidence[:2000]
    if success:
        step["status"] = "concluido"
        mission["status"] = (
            "concluida" if all(p["status"] == "concluido" for p in mission["passos"])
            else "pronta")
    elif step["tentativas"] >= mission["limite_tentativas"]:
        step["status"] = "bloqueado"
        mission["status"] = "bloqueada"
    else:
        step["status"] = "aguardando"
        mission["status"] = "pronta"
    _save(mission)
    registrar("missao_passo", f"#{mission_id}.{index + 1} -- {step['status']}")
    return {"executado": success, "passo": index + 1, "evidencia": evidence,
            "missao": mission}


def executar_ate_parar(jarvis, mission_id: int, max_passos=8):
    resultados = []
    for _ in range(max(1, min(int(max_passos), 20))):
        result = executar_proximo(jarvis, mission_id)
        resultados.append(result)
        mission = obter(jarvis.user_id, mission_id)
        if not result.get("executado") or mission["status"] != "pronta":
            break
    return {"missao": obter(jarvis.user_id, mission_id), "resultados": resultados}


def _tick(jarvis):
    """Executa um passo por ciclo, somente quando o computador está ocioso."""
    global _executando
    if _executando or not jarvis.settings.get("missoes.executar_automaticamente", True):
        return
    from sistema import ociosidade
    minutos = float(jarvis.settings.get("missoes.ociosidade_minutos", 3))
    if not ociosidade.esta_ocioso(minutos):
        return
    candidates = [m for m in listar(jarvis.user_id) if m["status"] == "pronta"]
    if not candidates:
        return
    _executando = True
    try:
        executar_proximo(jarvis, candidates[-1]["id"])
    finally:
        _executando = False


def iniciar(jarvis):
    if not jarvis.settings.is_module_enabled("automacao"):
        return
    from automacao import tasks
    interval = max(30, int(jarvis.settings.get("missoes.intervalo_segundos", 60)))
    tasks.schedule_recurring("missoes", interval, _tick, jarvis)
