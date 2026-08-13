"""
dispositivos/bluetooth_ble.py
================================
Bluetooth Low Energy via `bleak` (opcional, cross-platform, async).
"""

import asyncio

from logs.logger import get_logger

log = get_logger("dispositivos")

try:
    from bleak import BleakClient, BleakScanner
    HAS_BLEAK = True
except ImportError:
    HAS_BLEAK = False


def available() -> bool:
    return HAS_BLEAK


def scan(timeout: float = 5.0) -> list:
    """Escaneia dispositivos BLE próximos. Retorna [{"nome":..,"endereco":..}]."""
    if not HAS_BLEAK:
        raise RuntimeError("Instale 'bleak' para Bluetooth LE (pip install bleak).")

    async def _scan():
        devices = await BleakScanner.discover(timeout=timeout)
        return [{"nome": d.name or "desconhecido", "endereco": d.address} for d in devices]

    return asyncio.run(_scan())


async def _write_async(address: str, char_uuid: str, data: bytes):
    async with BleakClient(address) as client:
        await client.write_gatt_char(char_uuid, data)


def write_characteristic(address: str, char_uuid: str, data: bytes):
    if not HAS_BLEAK:
        raise RuntimeError("Instale 'bleak' para Bluetooth LE.")
    asyncio.run(_write_async(address, char_uuid, data))
