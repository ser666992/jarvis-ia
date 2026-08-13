"""
seguranca/backup.py
======================
Backup automático de `data/jarvis.db` (cópia com timestamp), com
limpeza dos backups mais antigos além do limite configurado.

Duas camadas, de propósito:
1. `maybe_auto_backup()` -- checagem "já faz tempo?" no STARTUP (ver
   core/jarvis.py). Sozinha, isso só protege quem reinicia o Ultron com
   frequência -- numa sessão longa (dias sem reiniciar, bem plausível
   pra um assistente pessoal), nunca mais dispara depois do primeiro
   backup daquela sessão.
2. `iniciar()` -- rotina de fundo de verdade (mesmo padrão de
   automacao/sonhos.py etc.): agenda o PRÓXIMO backup pro horário
   configurado (`seguranca.backup_horario`, "02:00" por padrão -- de
   madrugada, quando o PC tende a estar ocioso) usando
   automacao/tasks.py:schedule_once_at, e se reagenda pro dia seguinte
   depois de cada disparo -- funciona independente de quanto tempo o
   processo fica de pé.
"""

import glob
import os
import shutil
from datetime import datetime, timedelta

from config.settings import get_settings
from core.database import DB_PATH
from logs.logger import get_logger

log = get_logger("seguranca")

BACKUP_DIR = os.path.join(os.path.dirname(DB_PATH), "backups")


def create_backup() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.isfile(DB_PATH):
        raise FileNotFoundError(f"Banco de dados não encontrado em {DB_PATH}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"jarvis_{timestamp}.db")
    shutil.copy2(DB_PATH, dest)
    _cleanup_old_backups()
    return dest


def list_backups() -> list:
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(glob.glob(os.path.join(BACKUP_DIR, "jarvis_*.db")), reverse=True)


def _cleanup_old_backups():
    max_files = int(get_settings().get("seguranca.backup_max_arquivos", 10))
    for old_file in list_backups()[max_files:]:
        try:
            os.remove(old_file)
        except OSError:
            pass


def maybe_auto_backup():
    """Chamado no startup do Ultron (core/jarvis.py). Só cria backup se
    `seguranca.backup_automatico=true` E já se passou
    `seguranca.backup_intervalo_horas` desde o último backup. Retorna o
    caminho do novo backup, ou None se nenhum foi necessário."""
    settings = get_settings()
    if not settings.get("seguranca.backup_automatico", True):
        return None

    interval_hours = float(settings.get("seguranca.backup_intervalo_horas", 24))
    backups = list_backups()
    if backups:
        last_mtime = datetime.fromtimestamp(os.path.getmtime(backups[0]))
        elapsed_hours = (datetime.now() - last_mtime).total_seconds() / 3600
        if elapsed_hours < interval_hours:
            return None

    return create_backup()


def _proximo_horario(hora_str: str) -> datetime:
    """Próximo datetime em que o relógio bate 'HH:MM' -- hoje se ainda
    não passou, amanhã se já passou. Degrada pra 02:00 se o valor
    configurado estiver mal formado, em vez de travar o agendamento."""
    agora = datetime.now()
    try:
        hh, mm = hora_str.strip().split(":")
        alvo = agora.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except (ValueError, AttributeError, TypeError):
        alvo = agora.replace(hour=2, minute=0, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return alvo


def _agendar_proximo(jarvis):
    from automacao import tasks
    horario = get_settings().get("seguranca.backup_horario", "02:00")
    proximo = _proximo_horario(horario)
    # cancel_routine antes: schedule_once_at (diferente de
    # schedule_recurring) não cancela sozinho um timer pendente anterior
    # sob o mesmo nome -- sem isso, cada re-chamada (uma por dia, pra
    # sempre) deixaria o timer velho ainda vivo em paralelo, mesmo já
    # substituído no dicionário (mesma classe de bug já corrigida em
    # schedule_recurring).
    tasks.cancel_routine("backup_diario")
    tasks.schedule_once_at("backup_diario", proximo, _tick_diario, jarvis)


def _tick_diario(jarvis):
    try:
        caminho = create_backup()
        log.info("backup diário automático criado: %s", caminho)
    except Exception as e:
        log.warning("backup diário: falha ao criar (%s)", e)
    # Sempre reagenda pro dia seguinte, mesmo se este backup falhou --
    # uma falha pontual (disco cheio, arquivo travado) não deve
    # interromper a rotina permanentemente.
    _agendar_proximo(jarvis)


def iniciar(jarvis):
    """Agenda o backup diário no horário configurado (mesmo padrão de
    início das outras rotinas autônomas). No-op se o módulo 'seguranca'
    estiver desligado ou `seguranca.backup_automatico` for false."""
    settings = jarvis.settings
    if not settings.is_module_enabled("seguranca"):
        return
    if not settings.get("seguranca.backup_automatico", True):
        return
    _agendar_proximo(jarvis)
