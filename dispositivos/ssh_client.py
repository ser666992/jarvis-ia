"""
dispositivos/ssh_client.py
=============================
SSH para servidores/Raspberry Pi/etc. Usa `paramiko` se instalado
(puro Python); senão cai para o binário `ssh` do sistema via
subprocess (funciona sem nenhuma dependência pip, desde que o cliente
OpenSSH esteja instalado -- padrão no Windows 10+/Linux/macOS).
"""

import shutil
import subprocess

from logs.logger import get_logger

log = get_logger("dispositivos")

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


def backend() -> str:
    if HAS_PARAMIKO:
        return "paramiko"
    if shutil.which("ssh"):
        return "ssh_sistema"
    return ""


def available() -> bool:
    return bool(backend())


def run_command(host: str, command: str, user: str = "root", port: int = 22,
                 password: str = None, key_path: str = None, timeout: int = 15) -> str:
    be = backend()
    if not be:
        raise RuntimeError(
            "Nenhum backend SSH disponível: instale 'paramiko' (pip install paramiko) "
            "ou tenha o cliente OpenSSH ('ssh') no PATH."
        )

    if be == "paramiko":
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, port=port, username=user, password=password,
                        key_filename=key_path, timeout=timeout)
        try:
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            return (
                stdout.read().decode("utf-8", errors="replace")
                + stderr.read().decode("utf-8", errors="replace")
            )
        finally:
            client.close()

    # Fallback: ssh do sistema (não cobre senha interativa -- use chave).
    args = ["ssh", "-p", str(port)]
    if key_path:
        args += ["-i", key_path]
    args += [f"{user}@{host}", command]
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return result.stdout + result.stderr
