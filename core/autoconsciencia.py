"""
core/autoconsciencia.py
==========================
"Consciência interna": uma representação técnica que o Ultron tem DELE
MESMO, montada a partir de dados REAIS do processo -- não é
autoconsciência no sentido filosófico (isso não existe hoje), é
introspecção honesta: quantos plugins carregou, quais módulos estão
disponíveis, quanta memória o processo está usando, há quanto tempo
está rodando, quais rotinas de fundo estão ativas, quais provedores de
IA estão prontos, e quantos erros foram registrados no log hoje (por
módulo).

Assim, quando você pergunta "como você está (tecnicamente)?" ou pede um
"diagnóstico", ele responde com números que reflete a realidade do
processo -- e é HONESTO sobre o que cada número significa (ex.: a
memória é a RAM deste processo Python, não a soma de "13 agentes"; os
"agentes ativos" são as rotinas agendadas em segundo plano, cada uma um
timer real).

Ver plugins/consciencia.py pros comandos de chat.
"""

import os
import re
from datetime import datetime

from logs.logger import LOG_FILE

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Linha do log: "2026-07-04 22:04:37,830 [WARNING] jarvis.ocr: mensagem"
_LINHA_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s[\d:,]+\s\[(WARNING|ERROR|CRITICAL)\]\s+jarvis\.([\w.]+):"
)


def memoria_processo_mb() -> float:
    """RAM usada por ESTE processo (RSS), em MB. None se psutil ausente."""
    if not HAS_PSUTIL:
        return None
    try:
        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 ** 2), 1)
    except Exception:
        return None


def uptime_segundos() -> float:
    if not HAS_PSUTIL:
        return None
    try:
        return max(0.0, datetime.now().timestamp() - psutil.Process(os.getpid()).create_time())
    except Exception:
        return None


def _formatar_duracao(segundos: float) -> str:
    if segundos is None:
        return "desconhecido"
    segundos = int(segundos)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    if h:
        return f"{h}h{m:02d}min"
    if m:
        return f"{m}min{s:02d}s"
    return f"{s}s"


def erros_de_hoje() -> dict:
    """Conta WARNING/ERROR/CRITICAL registrados HOJE no log, agrupados
    por módulo. Retorna {} se o log não existe ou não teve nada hoje.
    Melhor-esforço: só lê o arquivo de log atual (o rotacionado antigo
    não conta), e é tolerante a linhas fora do formato."""
    if not os.path.isfile(LOG_FILE):
        return {}
    hoje = datetime.now().strftime("%Y-%m-%d")
    por_modulo = {}
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            for linha in f:
                m = _LINHA_LOG_RE.match(linha)
                if not m:
                    continue
                data, _nivel, modulo = m.group(1), m.group(2), m.group(3)
                if data != hoje:
                    continue
                por_modulo[modulo] = por_modulo.get(modulo, 0) + 1
    except Exception:
        return por_modulo
    return por_modulo


def rotinas_ativas() -> list:
    """Nomes das rotinas de fundo agendadas agora (os "agentes ativos"
    -- cada uma é um threading.Timer real de automacao/tasks.py)."""
    try:
        from automacao import tasks
        return sorted(tasks._active_timers.keys())
    except Exception:
        return []


def relatorio(jarvis) -> dict:
    """Retrato técnico estruturado do estado atual do Ultron."""
    dados = {
        "plugins_carregados": len(jarvis.plugins.plugins),
        "memoria_processo_mb": memoria_processo_mb(),
        "uptime_segundos": uptime_segundos(),
        "rotinas_ativas": rotinas_ativas(),
        "erros_hoje": erros_de_hoje(),
        "provedores_ia": [],
        "modulos": {},
        "estado_simulado": None,
    }

    try:
        if jarvis.ia_manager is not None:
            dados["provedores_ia"] = [p.name for p in jarvis.ia_manager.available_providers()]
    except Exception:
        pass

    try:
        for nome, st in jarvis.module_manager.status_all().items():
            dados["modulos"][nome] = bool(st.get("disponivel"))
    except Exception:
        pass

    try:
        from core import estado_interno
        dados["estado_simulado"] = estado_interno.estado_atual(jarvis.user_id)
    except Exception:
        pass

    return dados


def descrever(jarvis) -> str:
    """Versão legível/técnica do relatório, pra responder no chat."""
    r = relatorio(jarvis)
    linhas = []

    mem = f"{r['memoria_processo_mb']} MB" if r["memoria_processo_mb"] is not None else "desconhecida (instale psutil)"
    linhas.append(f"- Memória deste processo: {mem}")
    linhas.append(f"- No ar há: {_formatar_duracao(r['uptime_segundos'])}")
    linhas.append(f"- Plugins carregados: {r['plugins_carregados']}")

    if r["provedores_ia"]:
        linhas.append(f"- IA pronta: {', '.join(r['provedores_ia'])}")
    else:
        linhas.append("- IA pronta: nenhum provedor configurado")

    if r["rotinas_ativas"]:
        linhas.append(f"- Rotinas de fundo ativas ({len(r['rotinas_ativas'])}): {', '.join(r['rotinas_ativas'])}")
    else:
        linhas.append("- Rotinas de fundo ativas: nenhuma")

    modulos_on = [n for n, ok in r["modulos"].items() if ok]
    modulos_off = [n for n, ok in r["modulos"].items() if not ok]
    if modulos_on:
        linhas.append(f"- Módulos disponíveis: {', '.join(modulos_on)}")
    if modulos_off:
        linhas.append(f"- Módulos indisponíveis (falta dependência/config): {', '.join(modulos_off)}")

    if r["erros_hoje"]:
        total = sum(r["erros_hoje"].values())
        detalhe = ", ".join(f"{mod} ({n})" for mod, n in sorted(r["erros_hoje"].items(), key=lambda kv: -kv[1]))
        linhas.append(f"- Avisos/erros no log hoje: {total} -- {detalhe}")
    else:
        linhas.append("- Avisos/erros no log hoje: nenhum")

    if r["estado_simulado"]:
        e = r["estado_simulado"]
        linhas.append(
            f"- Estado interno SIMULADO: energia {e['energia']}/100, humor '{e['humor']}' "
            "(é só uma variável que evolui com o uso -- não sinto nada de verdade)"
        )

    return "\n".join(linhas)
