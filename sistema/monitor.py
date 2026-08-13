"""
sistema/monitor.py
====================
Monitoramento de recursos do sistema: CPU, RAM, disco, rede, bateria
(via `psutil`, opcional) e GPU (via `sistema.hardware`). Também grava
snapshots periódicos em SQLite (`core/database.py`) para estatísticas
históricas e "registrar atividades", pedidos no escopo original.
"""

import shutil
import threading
from datetime import datetime

from core.database import get_database
from sistema.hardware import detect_gpu

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sistema_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cpu_percent REAL,
    ram_percent REAL,
    disco_percent REAL,
    bateria_percent REAL,
    gpu_nome TEXT
);
"""


def _ensure_schema():
    get_database().executescript(_SCHEMA)


def snapshot() -> dict:
    """Uma leitura pontual do estado do sistema."""
    data = {"timestamp": datetime.now().isoformat()}

    if HAS_PSUTIL:
        data["cpu_percent"] = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        data["ram_percent"] = mem.percent
        data["ram_usado_mb"] = mem.used // (1024 ** 2)
        data["ram_total_mb"] = mem.total // (1024 ** 2)
        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        data["bateria_percent"] = battery.percent if battery else None
        net = psutil.net_io_counters()
        data["rede_enviado_mb"] = net.bytes_sent // (1024 ** 2)
        data["rede_recebido_mb"] = net.bytes_recv // (1024 ** 2)
    else:
        data.update({"cpu_percent": None, "ram_percent": None, "bateria_percent": None})

    total, used, free = shutil.disk_usage("/")
    data["disco_percent"] = round(used / total * 100, 1)
    data["disco_livre_gb"] = free // (1024 ** 3)
    data["disco_total_gb"] = total // (1024 ** 3)

    gpu = detect_gpu()
    data["gpu_nome"] = gpu["nome"]
    data["gpu_disponivel"] = gpu["disponivel"]

    return data


def save_snapshot(data: dict = None):
    _ensure_schema()
    data = data or snapshot()
    get_database().execute(
        """INSERT INTO sistema_snapshots
           (timestamp, cpu_percent, ram_percent, disco_percent, bateria_percent, gpu_nome)
           VALUES (?,?,?,?,?,?)""",
        (data["timestamp"], data.get("cpu_percent"), data.get("ram_percent"),
         data.get("disco_percent"), data.get("bateria_percent"), data.get("gpu_nome")),
    )


def history(limit: int = 50) -> list:
    _ensure_schema()
    return get_database().query(
        "SELECT * FROM sistema_snapshots ORDER BY id DESC LIMIT ?", (limit,)
    )


class MonitorLoop:
    """Thread de fundo que grava um snapshot a cada N segundos.
    Opt-in via config `sistema.monitorar_ao_iniciar` -- não roda
    sozinho sem essa flag."""

    def __init__(self, interval_seconds: int = 30):
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                save_snapshot()
            except Exception:
                pass
            self._stop.wait(self.interval_seconds)
