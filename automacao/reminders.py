"""
automacao/reminders.py
=========================
Lembretes com horário: "me lembre que tenho treino às 18h" agenda uma
notificação (som + mensagem) para aquele horário, reaproveitando
`automacao.tasks.schedule_once_at` (threading.Timer, zero dependência).

Também suporta lembretes RECORRENTES ("me lembra de beber água a cada
1 hora", ver plugins/reminders.py): em vez de marcar disparado=1 depois
de tocar, `_fire_reminder` reagenda a si mesmo pro próximo horário,
indefinidamente, até ser cancelado explicitamente (cancel_reminder).

Persistido em SQLite (`core/database.py`) para sobreviver a reinícios:
`reschedule_pending()` roda no startup do Ultron (core/jarvis.py) e
reagenda tudo que ainda não disparou -- o que já passou do horário
enquanto o processo estava desligado dispara na hora, imediatamente.

A notificação em si (som + mensagem, com ganchos para avisos visuais
extras como um toast na GUI) é compartilhada com outros módulos que
avisam o usuário proativamente -- ver automacao/notify.py.
"""

import re
from datetime import datetime, timedelta

from automacao import tasks
from automacao.notify import notify
from core.database import get_database
from core.timeline import registrar
from logs.logger import get_logger

log = get_logger("automacao")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automacao_lembretes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    quando TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    disparado INTEGER NOT NULL DEFAULT 0,
    intervalo_segundos INTEGER
);
"""

_CLOCK_RE = re.compile(r"\b(?:[àa]s?)\s*(\d{1,2})(?:[:h](\d{2}))?\s*h?\b", re.IGNORECASE)
_REL_MIN_RE = re.compile(r"\b(?:em|daqui a)\s+(\d+)\s*min(?:uto)?s?\b", re.IGNORECASE)
_REL_HOUR_RE = re.compile(r"\b(?:em|daqui a)\s+(\d+)\s*h(?:ora)?s?\b", re.IGNORECASE)
_TOMORROW_RE = re.compile(r"\bamanh[ãa]\b", re.IGNORECASE)
_TODAY_RE = re.compile(r"\bhoje\b", re.IGNORECASE)


def _ensure_schema():
    db = get_database()
    db.executescript(_SCHEMA)
    try:
        # Migração pra bancos criados antes de intervalo_segundos existir
        # -- CREATE TABLE IF NOT EXISTS não adiciona coluna em tabela já
        # existente, então isso cobre quem já tinha lembretes salvos.
        db.execute("ALTER TABLE automacao_lembretes ADD COLUMN intervalo_segundos INTEGER")
    except Exception:
        pass  # coluna já existe


def parse_datetime_from_text(text: str, now: datetime = None):
    """Extrai uma data/hora de uma frase em português e retorna
    (datetime, texto_sem_expressao_de_tempo) -- ou (None, text) se
    nenhuma expressão de tempo reconhecível foi encontrada.

    Reconhece tempo relativo ("em 10 minutos", "daqui a 2 horas") e
    horário do relógio ("às 18h", "às 18:30", "as 18h30"), combinado
    opcionalmente com "amanhã"/"hoje". Se o horário do relógio já
    passou hoje e nem "amanhã" nem "hoje" foram ditos, assume amanhã.
    """
    now = now or datetime.now()
    t = text.strip()

    m = _REL_MIN_RE.search(t)
    if m:
        when = now + timedelta(minutes=int(m.group(1)))
        cleaned = (t[:m.start()] + t[m.end():]).strip()
        return when, re.sub(r"\s{2,}", " ", cleaned).strip(" ,.")

    m = _REL_HOUR_RE.search(t)
    if m:
        when = now + timedelta(hours=int(m.group(1)))
        cleaned = (t[:m.start()] + t[m.end():]).strip()
        return when, re.sub(r"\s{2,}", " ", cleaned).strip(" ,.")

    m = _CLOCK_RE.search(t)
    if m:
        hora = int(m.group(1))
        minuto = int(m.group(2)) if m.group(2) else 0
        if not (0 <= hora <= 23 and 0 <= minuto <= 59):
            return None, text

        amanha = bool(_TOMORROW_RE.search(t))
        hoje = bool(_TODAY_RE.search(t))
        when = now.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if amanha or (not hoje and when <= now):
            when += timedelta(days=1)

        cleaned = t[:m.start()] + t[m.end():]
        cleaned = _TOMORROW_RE.sub("", cleaned)
        cleaned = _TODAY_RE.sub("", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.")
        return when, cleaned

    return None, text


def _fire_reminder(reminder_id: int, mensagem: str):
    _ensure_schema()
    row = get_database().query_one("SELECT * FROM automacao_lembretes WHERE id = ?", (reminder_id,))
    intervalo = row["intervalo_segundos"] if row else None
    if intervalo:
        # Lembrete recorrente: nunca marca disparado=1 -- só reagenda pro
        # próximo horário, indefinidamente, até ser cancelado.
        proximo = datetime.now() + timedelta(seconds=intervalo)
        get_database().execute(
            "UPDATE automacao_lembretes SET quando = ? WHERE id = ?", (proximo.isoformat(), reminder_id)
        )
        tasks.schedule_once_at(f"lembrete_{reminder_id}", proximo, _fire_reminder, reminder_id, mensagem)
    else:
        get_database().execute(
            "UPDATE automacao_lembretes SET disparado = 1 WHERE id = ?", (reminder_id,)
        )
    notify("Lembrete", mensagem)
    registrar("lembrete_disparado", mensagem)


def create_reminder(user_id: str, mensagem: str, when: datetime, intervalo_segundos: int = None) -> dict:
    _ensure_schema()
    cursor = get_database().execute(
        "INSERT INTO automacao_lembretes (user_id, mensagem, quando, criado_em, disparado, intervalo_segundos) "
        "VALUES (?,?,?,?,0,?)",
        (user_id, mensagem, when.isoformat(), datetime.now().isoformat(), intervalo_segundos),
    )
    # `execute()` abre/fecha sua própria conexão (core/database.py), então
    # `last_insert_rowid()` numa query separada veria outra conexão --
    # `cursor.lastrowid` já vem preenchido pelo sqlite3 no momento do
    # INSERT, independente da conexão seguir aberta ou não.
    row = get_database().query_one(
        "SELECT * FROM automacao_lembretes WHERE id = ?", (cursor.lastrowid,)
    )
    tasks.schedule_once_at(f"lembrete_{row['id']}", when, _fire_reminder, row["id"], mensagem)
    registrar("lembrete_criado", mensagem)
    return row


def cancel_reminder(user_id: str, mensagem_substring: str) -> int:
    """Cancela lembrete(s) pendentes (inclusive recorrentes) cuja
    mensagem contenha `mensagem_substring`. Retorna quantos foram
    cancelados.

    Uma substring vazia bateria (via LIKE '%%') com TODOS os lembretes
    pendentes do usuário -- recusada aqui na raiz (o chamador de chat
    em plugins/reminders.py já bloqueia isso, mas outros chamadores
    programáticos podem não repetir essa checagem)."""
    if not mensagem_substring or not mensagem_substring.strip():
        raise ValueError("Preciso de uma palavra da mensagem original pra saber qual lembrete cancelar.")
    _ensure_schema()
    candidatos = get_database().query(
        "SELECT * FROM automacao_lembretes WHERE user_id = ? AND disparado = 0 AND mensagem LIKE ?",
        (user_id, f"%{mensagem_substring}%"),
    )
    for r in candidatos:
        get_database().execute("UPDATE automacao_lembretes SET disparado = 1 WHERE id = ?", (r["id"],))
        tasks.cancel_routine(f"lembrete_{r['id']}")
    return len(candidatos)


def list_pending(user_id: str) -> list:
    _ensure_schema()
    return get_database().query(
        "SELECT * FROM automacao_lembretes WHERE user_id = ? AND disparado = 0 ORDER BY quando ASC",
        (user_id,),
    )


def reschedule_pending():
    """Roda uma vez por início do Ultron: reagenda todo lembrete que
    ainda não disparou. O que já passou do horário enquanto o processo
    estava desligado dispara imediatamente, em vez de ficar perdido."""
    _ensure_schema()
    now = datetime.now()
    for r in get_database().query("SELECT * FROM automacao_lembretes WHERE disparado = 0"):
        when = datetime.fromisoformat(r["quando"])
        tasks.schedule_once_at(
            f"lembrete_{r['id']}", when if when > now else now,
            _fire_reminder, r["id"], r["mensagem"],
        )
