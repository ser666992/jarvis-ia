from sistema import display
from sistema.hardware import (
    detect_gpu, detect_cpu, detect_nvidia_stack, full_report, device_for_ml,
)
from sistema.monitor import snapshot, save_snapshot, history, MonitorLoop
from sistema.processes import list_processes, find_process, list_windows_services

__all__ = [
    "detect_gpu", "detect_cpu", "detect_nvidia_stack", "full_report", "device_for_ml",
    "snapshot", "save_snapshot", "history", "MonitorLoop",
    "list_processes", "find_process", "list_windows_services",
    "display", "status",
]


def status() -> dict:
    gpu = detect_gpu()
    motivo = f"GPU: {gpu['nome']} (via {gpu['backend']})" if gpu["disponivel"] else \
        "nenhuma GPU NVIDIA detectada, usando CPU"
    return {"disponivel": True, "motivo": motivo, "detalhes": gpu}
