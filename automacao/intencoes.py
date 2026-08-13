"""
automacao/intencoes.py
=========================
"Sistema de Intenção": em vez de dar um comando por vez, você declara
um OBJETIVO grande ("quero lançar esse jogo esse mês") e o Ultron
quebra isso sozinho num CHECKLIST de passos concretos (via IA), salva,
e acompanha o progresso conforme você marca cada passo como feito.

O que isto É (honesto): um decompositor de objetivo em passos + um
checklist persistente com acompanhamento de progresso. O Ultron
PLANEJA e ACOMPANHA -- ele não executa sozinho "criar trailer" ou
"preparar marketing" (isso exigiria capacidades que ele não tem, e
fazer sozinho sem revisão seria arriscado). Cada passo é algo pra VOCÊ
(ou um comando específico do Ultron, quando existir) fazer; o valor
está em transformar um objetivo vago numa lista clara e rastreável, e
te lembrar do que falta.

Persistido em SQLite (core/database.py) -- sobrevive a reinícios, igual
a macros/lembretes. Ver plugins/intencoes.py pros comandos de chat.
"""

import json
from datetime import datetime

from core.database import get_database
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

_MAX_PASSOS = 20  # teto contra um checklist gigante/inútil

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automacao_intencoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    objetivo TEXT NOT NULL,
    passos TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ativo'
);
"""

_SYSTEM_PROMPT_DECOMPOR = (
    "Você é um planejador de projetos. Recebe um OBJETIVO e devolve um plano concreto pra "
    "alcançá-lo, quebrado em passos acionáveis. Responda APENAS com um JSON (sem markdown, sem "
    "texto fora do JSON) neste formato:\n"
    '{"passos": ["passo 1 curto e concreto", "passo 2", "..."]}\n'
    "Entre 4 e 12 passos, na ordem lógica de execução, cada um começando com um verbo no "
    "infinitivo (ex.: \"Revisar bugs críticos\", \"Gerar página da loja\"). Sem explicações, "
    "só os passos."
)


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def _extrair_passos_json(resposta: str) -> list:
    import re
    texto = (resposta or "").strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", texto, re.DOTALL)
    if m:
        texto = m.group(1).strip()
    try:
        dados = json.loads(texto)
        passos = dados.get("passos") if isinstance(dados, dict) else dados
        if isinstance(passos, list):
            return [str(p).strip() for p in passos if str(p).strip()][:_MAX_PASSOS]
    except Exception:
        pass
    return []


def _decompor(ia_manager, objetivo: str) -> list:
    """Usa a IA pra quebrar `objetivo` numa lista de passos. Degrada pra
    um passo único genérico se a IA não estiver disponível ou não
    devolver um JSON válido -- assim criar uma intenção NUNCA falha por
    causa disso (só fica menos detalhada)."""
    if ia_manager is None:
        return [f"Planejar como {objetivo}"]
    try:
        _, resposta = ia_manager.chat(
            f"Objetivo: {objetivo}", history=[], system_prompt=_SYSTEM_PROMPT_DECOMPOR,
            max_tokens=500,
        )
    except Exception as e:
        log.warning("intencoes: falha ao decompor objetivo via IA: %s", e)
        return [f"Planejar como {objetivo}"]
    passos = _extrair_passos_json(resposta)
    return passos or [f"Planejar como {objetivo}"]


def criar_intencao(ia_manager, user_id: str, objetivo: str) -> dict:
    _ensure_schema()
    objetivo = objetivo.strip()
    if not objetivo:
        raise ValueError("Preciso de um objetivo pra planejar.")
    passos_texto = _decompor(ia_manager, objetivo)
    passos = [{"descricao": p, "feito": False} for p in passos_texto]
    cursor = get_database().execute(
        "INSERT INTO automacao_intencoes (user_id, objetivo, passos, criado_em, status) VALUES (?,?,?,?,'ativo')",
        (user_id, objetivo, json.dumps(passos, ensure_ascii=False), datetime.now().isoformat()),
    )
    registrar("intencao_criada", objetivo[:80])
    return obter_intencao(user_id, cursor.lastrowid)


def obter_intencao(user_id: str, intencao_id: int) -> dict:
    _ensure_schema()
    row = get_database().query_one(
        "SELECT * FROM automacao_intencoes WHERE user_id=? AND id=?", (user_id, intencao_id)
    )
    if not row:
        return None
    row["passos"] = json.loads(row["passos"])
    return row


def listar_intencoes(user_id: str, incluir_arquivadas: bool = False) -> list:
    _ensure_schema()
    if incluir_arquivadas:
        rows = get_database().query(
            "SELECT * FROM automacao_intencoes WHERE user_id=? ORDER BY id", (user_id,)
        )
    else:
        rows = get_database().query(
            "SELECT * FROM automacao_intencoes WHERE user_id=? AND status != 'arquivado' ORDER BY id",
            (user_id,),
        )
    for r in rows:
        r["passos"] = json.loads(r["passos"])
    return rows


def progresso(intencao: dict) -> tuple:
    """(feitos, total) de uma intenção."""
    passos = intencao.get("passos", [])
    feitos = sum(1 for p in passos if p.get("feito"))
    return feitos, len(passos)


def marcar_passo(user_id: str, intencao_id: int, indice_passo: int, feito: bool = True) -> dict:
    """Marca o passo `indice_passo` (base 1, como o usuário vê) como
    feito/não feito. Atualiza o status da intenção pra 'concluido' se
    todos os passos ficarem feitos. Retorna a intenção atualizada, ou
    None se a intenção/índice não existir."""
    intencao = obter_intencao(user_id, intencao_id)
    if not intencao:
        return None
    passos = intencao["passos"]
    if not (1 <= indice_passo <= len(passos)):
        return None
    passos[indice_passo - 1]["feito"] = bool(feito)
    novo_status = "concluido" if all(p["feito"] for p in passos) else "ativo"
    get_database().execute(
        "UPDATE automacao_intencoes SET passos=?, status=? WHERE user_id=? AND id=?",
        (json.dumps(passos, ensure_ascii=False), novo_status, user_id, intencao_id),
    )
    if novo_status == "concluido":
        registrar("intencao_concluida", intencao["objetivo"][:80])
    intencao["passos"] = passos
    intencao["status"] = novo_status
    return intencao


def adicionar_passo(user_id: str, intencao_id: int, descricao: str) -> dict:
    intencao = obter_intencao(user_id, intencao_id)
    if not intencao:
        return None
    if len(intencao["passos"]) >= _MAX_PASSOS:
        return intencao
    intencao["passos"].append({"descricao": descricao.strip(), "feito": False})
    get_database().execute(
        "UPDATE automacao_intencoes SET passos=?, status='ativo' WHERE user_id=? AND id=?",
        (json.dumps(intencao["passos"], ensure_ascii=False), user_id, intencao_id),
    )
    return intencao


def remover_intencao(user_id: str, intencao_id: int) -> bool:
    _ensure_schema()
    if not obter_intencao(user_id, intencao_id):
        return False
    get_database().execute(
        "DELETE FROM automacao_intencoes WHERE user_id=? AND id=?", (user_id, intencao_id)
    )
    return True


def resumo_para_prompt(user_id: str, max_chars: int = 300) -> str:
    """Resumo curto das intenções ATIVAS -- pra outras partes (ex.:
    sonhos.py) puxarem no que o usuário está tentando alcançar e
    personalizarem sugestões. String vazia se não houver nenhuma."""
    ativas = [i for i in listar_intencoes(user_id) if i["status"] == "ativo"]
    if not ativas:
        return ""
    partes = []
    for i in ativas[:5]:
        feitos, total = progresso(i)
        partes.append(f"{i['objetivo']} ({feitos}/{total} passos)")
    return "Objetivos atuais do usuário: " + "; ".join(partes)[:max_chars]
