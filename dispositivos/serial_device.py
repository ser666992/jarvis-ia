"""
dispositivos/serial_device.py
================================
Comunicação serial com Arduino/ESP32/microcontroladores em geral, via
`pyserial` (opcional). Listar portas disponíveis funciona mesmo sem
nenhum dispositivo conectado -- útil para diagnosticar o que está
plugado na máquina.
"""

from logs.logger import get_logger

log = get_logger("dispositivos")

try:
    import serial
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False


def available() -> bool:
    return HAS_PYSERIAL


def list_ports() -> list:
    if not HAS_PYSERIAL:
        raise RuntimeError("Instale 'pyserial' para listar portas seriais (pip install pyserial).")
    return [
        {"porta": p.device, "descricao": p.description, "hwid": p.hwid}
        for p in serial.tools.list_ports.comports()
    ]


class SerialDevice:
    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 2.0):
        if not HAS_PYSERIAL:
            raise RuntimeError("Instale 'pyserial' para comunicação serial.")
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._conn = None

    def open(self):
        if self._conn is None or not self._conn.is_open:
            self._conn = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def write_line(self, text: str):
        self.open().write((text + "\n").encode("utf-8"))

    def read_line(self) -> str:
        line = self.open().readline()
        return line.decode("utf-8", errors="replace").strip()
