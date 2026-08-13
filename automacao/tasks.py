"""
automacao/tasks.py
=====================
Rotinas e agendamento: rodar uma função a cada N segundos, ou uma vez
em um horário específico. Implementado com `threading.Timer` (stdlib,
zero dependência) -- não substitui um agendador de nível de sistema
operacional (cron / Agendador de Tarefas do Windows) para tarefas que
precisam sobreviver ao processo do Ultron ser encerrado, mas cobre bem
rotinas "enquanto o Ultron estiver rodando".

Rotinas registradas via `register_routine()` ficam persistidas em
SQLite (`core/database.py`) como histórico/registro -- reagendar de
verdade após reiniciar o processo é feito chamando `schedule_recurring()`
novamente (ex.: no startup do Ultron, para as rotinas que devem
sobreviver a um reinício).
"""

import threading
from datetime import datetime

from core.database import get_database
from logs.logger import get_logger

log = get_logger("automacao")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automacao_rotinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    intervalo_segundos INTEGER,
    criada_em TEXT NOT NULL,
    ativa INTEGER NOT NULL DEFAULT 1
);
"""

_active_timers = {}


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def register_routine(nome: str, interval_seconds: int) -> dict:
    _ensure_schema()
    # last_insert_rowid() é por CONEXÃO -- get_database().execute() abre e
    # fecha sua própria conexão (core/database.py), então uma query
    # SEPARADA com "id = last_insert_rowid()" via query_one() via outra
    # conexão nova sempre retornava 0/nenhuma linha (bug real: esta função
    # sempre devolvia None). cursor.lastrowid já vem preenchido pelo
    # sqlite3 no momento do INSERT, independente da conexão seguir aberta
    # ou não -- mesmo padrão já usado corretamente em
    # automacao/reminders.py e automacao/macros.py.
    cursor = get_database().execute(
        "INSERT INTO automacao_rotinas (nome, intervalo_segundos, criada_em, ativa) VALUES (?,?,?,1)",
        (nome, interval_seconds, datetime.now().isoformat()),
    )
    return get_database().query_one("SELECT * FROM automacao_rotinas WHERE id = ?", (cursor.lastrowid,))


def list_routines() -> list:
    _ensure_schema()
    return get_database().query("SELECT * FROM automacao_rotinas ORDER BY id DESC")


def schedule_recurring(name: str, interval_seconds, func, *args, primeiro_delay_segundos=None, **kwargs) -> str:
    """Agenda `func(*args, **kwargs)` para rodar repetidamente, em uma
    thread de fundo, enquanto o processo do Ultron estiver vivo.

    `interval_seconds` pode ser um número fixo, ou uma função `() ->
    float` chamada a cada rodada pra sortear um intervalo diferente a
    cada vez (ex.: `lambda: random.uniform(180, 420)` pra rotinas com
    timing mais orgânico/imprevisível, tipo comentários espontâneos em
    vez de um tique-taque robótico).

    `primeiro_delay_segundos` (keyword-only): quando dado, o PRIMEIRO
    disparo acontece depois desse tempo, e só as rodadas seguintes usam
    `interval_seconds`. Serve pras rotinas autônomas de intervalo longo
    (aprender tecnologia = 24h, sonhos = 2h): sem isso, o primeiro
    aprendizado/ideia só aconteceria HORAS depois de abrir o Ultron, e
    numa sessão normal (minutos) nada autônomo jamais fazia efeito
    visível -- exatamente o "ele não cria/aprende nada sozinho" que o
    usuário notou. Com um delay inicial curto (ex.: 5 min), o Ultron
    faz algo sozinho já no começo da sessão, e depois segue no ritmo
    configurado.

    Chamar de novo com o MESMO `name` (ex.: usuário re-agenda a mesma
    macro/observação com outro intervalo) cancela qualquer timer
    pendente anterior sob esse nome antes de criar o novo -- sem isso,
    a cadeia antiga continuava rodando em PARALELO à nova (a checagem
    original só via se o NOME ainda estava no dicionário de timers
    ativos, não se era o MESMO timer que tinha acabado de disparar,
    então a cadeia antiga se via "ainda ativa" e continuava se
    reagendando sozinha), duplicando execuções indefinidamente. Bug
    real reproduzido: reagendar o mesmo nome antes do primeiro disparo
    resultava em ~2x mais execuções que o esperado."""
    def _next_interval():
        return interval_seconds() if callable(interval_seconds) else interval_seconds

    def _run():
        try:
            func(*args, **kwargs)
        except Exception as e:
            log.warning("erro na rotina '%s': %s", name, e)
        # threading.current_thread() aqui dentro É o próprio Timer que
        # está rodando (Timer herda de Thread) -- comparar IDENTIDADE
        # contra o timer atualmente registrado (não só se o nome existe
        # no dict) garante que só a cadeia MAIS RECENTE sob este nome
        # continua se reagendando, mesmo se uma cadeia antiga (já
        # substituída) ainda estiver com uma execução em andamento.
        if _active_timers.get(name) is threading.current_thread():
            timer = threading.Timer(_next_interval(), _run)
            timer.daemon = True
            _active_timers[name] = timer
            timer.start()

    cancel_routine(name)
    primeiro = primeiro_delay_segundos if primeiro_delay_segundos is not None else _next_interval()
    timer = threading.Timer(primeiro, _run)
    timer.daemon = True
    _active_timers[name] = timer
    timer.start()
    return name


def schedule_once_at(name: str, when: datetime, func, *args, **kwargs) -> str:
    delay = max(0, (when - datetime.now()).total_seconds())
    timer = threading.Timer(delay, func, args=args, kwargs=kwargs)
    timer.daemon = True
    _active_timers[name] = timer
    timer.start()
    return name


def cancel_routine(name: str) -> bool:
    timer = _active_timers.pop(name, None)
    if timer:
        timer.cancel()
        return True
    return False


def cancel_all() -> int:
    """Para todas as rotinas desta sessão; usado pela emergência."""
    names = list(_active_timers)
    for name in names:
        cancel_routine(name)
    return len(names)
