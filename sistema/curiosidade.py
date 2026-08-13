"""
sistema/curiosidade.py
=========================
"Sistema de Curiosidade + Previsão": procura padrões e anomalias REAIS
nos dados que o Ultron já coleta -- snapshots de hardware
(sistema/monitor.py) e a linha do tempo de eventos (core/timeline.py) --
e reporta observações do tipo "disco vai encher em ~X dias no ritmo
atual", "a RAM está subindo", "esse erro apareceu N vezes", "esse tipo
de evento tende a cair às quintas".

Honestidade sobre o que isto É e o que NÃO É:
- É análise estatística simples de dados históricos reais (regressão de
  tendência linear pro disco, contagem/agrupamento pra eventos). Um
  "vai encher em X dias" é uma EXTRAPOLAÇÃO do ritmo observado, não uma
  certeza -- muda se o seu uso mudar.
- NÃO prevê bugs de software, travamentos ou superaquecimento "antes de
  acontecer" no sentido mágico -- só extrapola tendências mensuráveis
  (disco enchendo, RAM subindo) e destaca repetições factuais na
  timeline. Prometer prever um crash de programa específico seria
  invenção.
- Precisa de DADOS ACUMULADOS pra dizer algo útil: sem pelo menos
  alguns snapshots ao longo do tempo, não há tendência pra extrapolar.
  Por isso `iniciar()` agenda uma coleta leve de snapshot periódica
  (reusa sistema/monitor.py:save_snapshot) quando ligado.
"""

from datetime import datetime

from core.database import get_database
from logs.logger import get_logger

log = get_logger("sistema")

_PALAVRAS_ERRO = ("erro", "error", "falhou", "failed", "travado", "travou", "exception", "crash")
_DIAS_ANALISE = 7
_DISCO_ALERTA_PCT = 90.0
_RAM_ALERTA_PCT = 85.0
_MIN_SPAN_HORAS = 1.0  # sem pelo menos 1h entre o primeiro e o último snapshot, não extrapola tendência


def _snapshots_recentes(limite: int = 500) -> list:
    from sistema.monitor import _ensure_schema
    _ensure_schema()
    return get_database().query(
        "SELECT timestamp, cpu_percent, ram_percent, disco_percent FROM sistema_snapshots "
        "ORDER BY id DESC LIMIT ?",
        (limite,),
    )


def _prever_disco(snapshots: list) -> dict:
    """Extrapola linearmente o ritmo de enchimento do disco. Retorna um
    finding ou None. Conservador: só fala se o disco estiver SUBINDO de
    verdade e o span de tempo for razoável.

    `snapshots` vem ordenado por id DESC (mais recente primeiro) -- o
    valor ATUAL do disco é o do snapshot mais recente (validos[0]), não
    o "último por timestamp" (timestamps podem empatar quando dois
    snapshots caem no mesmo segundo, e aí a ordenação por timestamp fica
    ambígua -- foi um bug real pego em teste)."""
    validos = [s for s in snapshots if s.get("disco_percent") is not None]
    if not validos:
        return None
    disco_atual = validos[0]["disco_percent"]

    if disco_atual >= _DISCO_ALERTA_PCT:
        return {
            "tipo": "disco_cheio",
            "gravidade": "alta",
            "texto": f"O disco já está em {disco_atual:.0f}% de uso -- considere liberar espaço logo.",
        }

    if len(validos) < 2:
        return None
    pontos = sorted(
        ((datetime.fromisoformat(s["timestamp"]), s["disco_percent"]) for s in validos),
        key=lambda p: p[0],
    )
    (t0, d0), (t1, d1) = pontos[0], pontos[-1]
    horas = (t1 - t0).total_seconds() / 3600
    if horas < _MIN_SPAN_HORAS:
        return None
    taxa_por_dia = (d1 - d0) / (horas / 24)  # pontos percentuais por dia
    if taxa_por_dia <= 0.5:  # praticamente estável ou caindo -- nada a alarmar
        return None
    dias_ate_cheio = (100 - disco_atual) / taxa_por_dia
    if dias_ate_cheio > 60:  # muito longe, não vale alarmar
        return None
    return {
        "tipo": "disco_tendencia",
        "gravidade": "media" if dias_ate_cheio > 7 else "alta",
        "texto": (
            f"No ritmo atual (disco subiu ~{taxa_por_dia:.1f}%/dia), o disco encheria em "
            f"cerca de {dias_ate_cheio:.0f} dia(s). É uma extrapolação do uso recente, não uma certeza."
        ),
    }


def _analisar_ram(snapshots: list) -> dict:
    valores = [s["ram_percent"] for s in snapshots[:20] if s.get("ram_percent") is not None]
    if len(valores) < 3:
        return None
    media = sum(valores) / len(valores)
    if media >= _RAM_ALERTA_PCT:
        return {
            "tipo": "ram_alta",
            "gravidade": "media",
            "texto": f"A RAM ficou em média {media:.0f}% nos últimos registros -- uso de memória consistentemente alto.",
        }
    return None


def _eventos_recentes() -> list:
    from datetime import timedelta
    desde = (datetime.now() - timedelta(days=_DIAS_ANALISE)).isoformat()
    return get_database().query(
        "SELECT event_type, description, timestamp FROM events WHERE timestamp >= ? ORDER BY id DESC LIMIT 2000",
        (desde,),
    )


def _eh_erro(ev: dict) -> bool:
    texto = f"{ev.get('event_type','')} {ev.get('description','')}".lower()
    return any(p in texto for p in _PALAVRAS_ERRO)


def _analisar_eventos(eventos: list) -> list:
    from collections import Counter
    findings = []

    erros = [e for e in eventos if _eh_erro(e)]
    if len(erros) >= 3:
        # Descrição mais frequente entre os erros
        contagem = Counter((e.get("description") or e.get("event_type") or "erro") for e in erros)
        desc, vezes = contagem.most_common(1)[0]
        if vezes >= 3:
            findings.append({
                "tipo": "erro_recorrente",
                "gravidade": "media",
                "texto": f'Notei um problema recorrente: "{desc[:80]}" apareceu {vezes} vez(es) nos últimos {_DIAS_ANALISE} dias.',
            })

        # Padrão por dia da semana (ex.: "aparece toda quinta")
        dias_semana = Counter()
        nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        for e in erros:
            try:
                dias_semana[datetime.fromisoformat(e["timestamp"]).weekday()] += 1
            except (KeyError, ValueError, TypeError):
                continue
        if dias_semana:
            dia, qtd = dias_semana.most_common(1)[0]
            if qtd >= 3 and qtd >= 0.6 * len(erros):  # concentrado num dia só
                findings.append({
                    "tipo": "erro_padrao_semanal",
                    "gravidade": "baixa",
                    "texto": f"Curioso: a maioria desses problemas ({qtd} de {len(erros)}) aconteceu numa {nomes[dia]}-feira.",
                })
    return findings


def analisar() -> list:
    """Roda toda a análise e retorna a lista de findings (cada um
    {"tipo", "gravidade", "texto"}), do mais grave pro menos. Lista
    vazia se não há dados suficientes ou nada digno de nota."""
    findings = []
    try:
        snapshots = _snapshots_recentes()
        for f in (_prever_disco(snapshots), _analisar_ram(snapshots)):
            if f:
                findings.append(f)
    except Exception as e:
        log.warning("curiosidade: falha ao analisar hardware: %s", e)
    try:
        findings.extend(_analisar_eventos(_eventos_recentes()))
    except Exception as e:
        log.warning("curiosidade: falha ao analisar eventos: %s", e)

    ordem = {"alta": 0, "media": 1, "baixa": 2}
    findings.sort(key=lambda f: ordem.get(f["gravidade"], 3))
    return findings


_ultimos_avisos = set()  # texto dos findings já notificados, pra não repetir


def _tick(jarvis=None):
    """Coleta um snapshot leve e, de vez em quando, avisa sobre findings
    de gravidade ALTA que ainda não foram avisados (dedup por texto)."""
    try:
        from sistema.monitor import save_snapshot
        save_snapshot()
    except Exception as e:
        log.warning("curiosidade: falha ao coletar snapshot: %s", e)

    findings = [f for f in analisar() if f["gravidade"] == "alta"]
    novos = [f for f in findings if f["texto"] not in _ultimos_avisos]
    if not novos:
        return
    from automacao.notify import notify
    for f in novos[:2]:
        _ultimos_avisos.add(f["texto"])
        notify("Ultron notou algo", f["texto"])


def iniciar(jarvis):
    """Agenda a coleta de snapshot + análise periódica. No-op se o
    módulo 'sistema' estiver desligado ou `sistema.curiosidade` for
    false. Coleta a cada `sistema.curiosidade_intervalo_minutos`
    (10min por padrão) -- leve (uma leitura de psutil + um INSERT)."""
    settings = jarvis.settings
    if not settings.is_module_enabled("sistema"):
        return
    if not settings.get("sistema.curiosidade", True):
        return
    try:
        minutos = float(settings.get("sistema.curiosidade_intervalo_minutos", 10))
    except (TypeError, ValueError):
        minutos = 10
    intervalo = max(120, minutos * 60)
    from automacao import tasks
    # Primeira coleta ~1 min depois de abrir (pega um ponto inicial cedo),
    # depois no intervalo configurado.
    tasks.schedule_recurring("curiosidade", intervalo, _tick, jarvis, primeiro_delay_segundos=60)
