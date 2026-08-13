"""
dispositivos/__init__.py
===========================
Ponto de entrada de dispositivos externos: Android (adb), Bluetooth
LE, Serial (Arduino/ESP32), MQTT (IoT) e SSH.

`register_device()` é o ponto de extensão para plugins adicionarem um
novo tipo de dispositivo/sensor sem tocar neste pacote:

    from dispositivos import register_device
    register_device("meu_sensor", meu_handler)
"""

from dispositivos import adb, bluetooth_ble, mqtt, serial_device, ssh_client

__all__ = [
    "adb", "bluetooth_ble", "serial_device", "mqtt", "ssh_client",
    "register_device", "DEVICE_REGISTRY", "status",
]

DEVICE_REGISTRY = {}


def register_device(name: str, handler):
    DEVICE_REGISTRY[name] = handler


def status() -> dict:
    partes = {
        "adb": adb.available(),
        "bluetooth_ble": bluetooth_ble.available(),
        "serial": serial_device.available(),
        "mqtt": mqtt.available(),
        "ssh": ssh_client.available(),
    }
    ativos = [k for k, v in partes.items() if v]
    motivo = (
        f"disponíveis: {', '.join(ativos)}" if ativos else
        "nenhum backend de dispositivo disponível (adb no PATH, pyserial, bleak, paho-mqtt, paramiko/ssh)"
    )
    return {"disponivel": any(partes.values()), "motivo": motivo, "detalhes": partes}
