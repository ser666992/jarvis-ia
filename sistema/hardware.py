"""
sistema/hardware.py
=====================
Detecção de hardware: CPU, GPU (com preferência por aceleração NVIDIA
CUDA quando disponível) e presença do stack de software da NVIDIA
(CUDA Toolkit, cuDNN, TensorRT, Triton, NeMo, Riva).

Cadeia de detecção de GPU (a primeira que funcionar decide):
  1. `torch.cuda.is_available()`   (se `torch` estiver instalado)
  2. `pynvml` (nvidia-ml-py)        (se estiver instalado)
  3. `nvidia-smi` via subprocess    (se estiver no PATH)
  4. nenhuma das anteriores -> CPU

Isto é só DETECÇÃO -- não tenta rodar inferência em nenhum desses
backends. Rodar de verdade em TensorRT/Triton/NeMo/Riva exige
instaladores próprios da NVIDIA (fora do pip) e hardware compatível;
os pontos de integração ficam documentados aqui e em `ia/local_model.py`.
"""

import platform
import shutil
import subprocess

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _try_torch():
    try:
        import torch
        if torch.cuda.is_available():
            return {
                "disponivel": True,
                "nome": torch.cuda.get_device_name(0),
                "backend": "torch.cuda",
                "quantidade": torch.cuda.device_count(),
            }
    except Exception:
        pass
    return None


def _try_pynvml():
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count > 0:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            return {"disponivel": True, "nome": name, "backend": "pynvml", "quantidade": count}
    except Exception:
        pass
    return None


def _try_nvidia_smi():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            names = [n.strip() for n in out.stdout.strip().splitlines() if n.strip()]
            return {"disponivel": True, "nome": names[0], "backend": "nvidia-smi", "quantidade": len(names)}
    except Exception:
        pass
    return None


def detect_gpu() -> dict:
    for probe in (_try_torch, _try_pynvml, _try_nvidia_smi):
        result = probe()
        if result:
            return result
    return {"disponivel": False, "nome": None, "backend": None, "quantidade": 0}


def detect_cpu() -> dict:
    info = {
        "processador": platform.processor() or platform.machine(),
        "arquitetura": platform.machine(),
        "sistema": f"{platform.system()} {platform.release()}",
        "nucleos_logicos": None,
        "nucleos_fisicos": None,
    }
    if HAS_PSUTIL:
        info["nucleos_logicos"] = psutil.cpu_count(logical=True)
        info["nucleos_fisicos"] = psutil.cpu_count(logical=False)
    return info


def _importable(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _cudnn_present() -> bool:
    try:
        import torch
        return bool(torch.backends.cudnn.is_available())
    except Exception:
        return False


def detect_nvidia_stack() -> dict:
    """Detecção honesta de presença (não uso) de cada peça do stack
    NVIDIA pedido: CUDA, cuDNN, TensorRT, Triton, NeMo, Riva, NIM."""
    return {
        "cuda_toolkit_nvcc": shutil.which("nvcc") is not None,
        "torch_cuda": _try_torch() is not None,
        "cudnn_via_torch": _cudnn_present(),
        "tensorrt": _importable("tensorrt"),
        "triton_client": _importable("tritonclient"),
        "nemo_toolkit": _importable("nemo"),
        "riva_client": _importable("riva.client") or _importable("riva"),
        # NIM / NVIDIA API Catalog não exigem SDK local: são endpoints
        # HTTP compatíveis com a API da OpenAI, cobertos por
        # ia/providers/openai_compatible.py -- sempre "disponível" no
        # sentido de que o código para usá-los já existe.
        "nim_via_api_http": True,
    }


def device_for_ml() -> str:
    """'cuda' se houver GPU NVIDIA utilizável por torch, senão 'cpu' --
    usado por ia/local_model.py para escolher onde rodar um modelo local."""
    gpu = detect_gpu()
    if gpu["disponivel"] and gpu["backend"] == "torch.cuda":
        return "cuda"
    return "cpu"


def full_report() -> dict:
    return {
        "cpu": detect_cpu(),
        "gpu": detect_gpu(),
        "nvidia_stack": detect_nvidia_stack(),
    }
