"""
sistema/processes.py
======================
Listagem de processos e serviços do sistema operacional. Complementa
o que `plugins/system_control.py` já faz com `psutil`, e adiciona
listagem de serviços do Windows (via `sc query`, sem dependência
extra) quando aplicável.
"""

import platform
import subprocess

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def list_processes(limit: int = 20) -> list:
    if not HAS_PSUTIL:
        return []
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda i: i.get("memory_percent") or 0, reverse=True)
    return procs[:limit]


def find_process(name_substring: str) -> list:
    if not HAS_PSUTIL:
        return []
    name_substring = name_substring.lower()
    return [
        p.info for p in psutil.process_iter(["pid", "name"])
        if p.info.get("name") and name_substring in p.info["name"].lower()
    ]


def list_windows_services(limit: int = 20) -> list:
    if platform.system() != "Windows":
        return []
    try:
        out = subprocess.run(
            ["sc", "query", "state=", "all"], capture_output=True, text=True, timeout=10
        )
    except Exception:
        return []
    services = []
    current = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("SERVICE_NAME:"):
            if current:
                services.append(current)
            current = {"nome": line.split(":", 1)[1].strip()}
        elif line.startswith("STATE"):
            parts = line.split()
            if len(parts) >= 4:
                current["estado"] = parts[3]
    if current:
        services.append(current)
    return services[:limit]
