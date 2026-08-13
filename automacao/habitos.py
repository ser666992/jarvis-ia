"""
automacao/habitos.py
=======================
Análise de hábitos: amostra periodicamente qual app/janela está em
primeiro plano no PC (visao/observe.py, leve, sem OCR) -- e acumula
isso numa tabela própria (data/jarvis.db) pra poder responder "quais
são meus hábitos" com uma contagem de verdade, não um palpite.

Amostragem intencionalmente ESPAÇADA (5 min) -- não precisa de
granularidade fina pra detectar hábito, e assim o custo (CPU) fica
desprezível.
"""

from collections import Counter
from datetime import datetime, timedelta

from automacao import tasks
from core.database import get_database
from logs.logger import get_logger
from visao.observe import active_process_name, active_window_title

log = get_logger("automacao")

_INTERVALO_PC = 300       # 5 minutos

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automacao_habitos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origem TEXT NOT NULL,     -- 'pc'
    app TEXT,
    janela TEXT,
    timestamp TEXT NOT NULL
);
"""


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def _tick_pc():
    _ensure_schema()
    processo = active_process_name()
    janela = active_window_title()
    if not processo and not janela:
        return
    get_database().execute(
        "INSERT INTO automacao_habitos (origem, app, janela, timestamp) VALUES ('pc', ?, ?, ?)",
        (processo, janela, datetime.now().isoformat()),
    )


def iniciar(jarvis):
    """Chamado uma vez no startup do Jarvis -- agenda a amostragem
    periódica enquanto o processo estiver vivo. No-op se o módulo
    automacao estiver desligado, ou se personalidade.analisar_habitos
    estiver false."""
    settings = jarvis.settings
    if not settings.is_module_enabled("automacao"):
        return
    if not settings.get("personalidade.analisar_habitos", True):
        return
    tasks.schedule_recurring("habitos_pc", _INTERVALO_PC, _tick_pc)


def resumo(origem: str, dias: int = 7, top_n: int = 8) -> str:
    _ensure_schema()
    desde = (datetime.now() - timedelta(days=dias)).isoformat()
    linhas = get_database().query(
        "SELECT app, janela FROM automacao_habitos WHERE origem=? AND timestamp >= ? ORDER BY id",
        (origem, desde),
    )
    if not linhas:
        return f"Ainda não tenho amostras suficientes de hábitos no {origem} (últimos {dias} dia(s))."

    contagem = Counter()
    for r in linhas:
        chave = r["app"] or r["janela"] or "desconhecido"
        contagem[chave] += 1
    total = sum(contagem.values())

    partes = []
    for nome, vezes in contagem.most_common(top_n):
        pct = 100 * vezes / total
        partes.append(f"- {nome}: {vezes} amostra(s) ({pct:.0f}%)")
    return f"Hábitos no {origem} (últimos {dias} dia(s), {total} amostras):\n" + "\n".join(partes)
