"""
dispositivos/mqtt.py
=======================
IoT / casa inteligente via MQTT (`paho-mqtt`, opcional). Cobre
integração com ESP32/sensores/automação residencial via broker MQTT
(Mosquitto, HiveMQ, broker próprio, etc.).
"""

from logs.logger import get_logger

log = get_logger("dispositivos")

try:
    import paho.mqtt.client as mqtt
    HAS_PAHO = True
except ImportError:
    HAS_PAHO = False


def available() -> bool:
    return HAS_PAHO


class MQTTClient:
    def __init__(self, broker_host: str, broker_port: int = 1883, client_id: str = "jarvis"):
        if not HAS_PAHO:
            raise RuntimeError("Instale 'paho-mqtt' para MQTT (pip install paho-mqtt).")
        self.broker_host = broker_host
        self.broker_port = broker_port
        self._client = mqtt.Client(client_id=client_id)
        self._subscriptions = {}
        self._client.on_message = self._on_message

    def _on_message(self, client, userdata, msg):
        callback = self._subscriptions.get(msg.topic)
        if callback:
            callback(msg.topic, msg.payload.decode("utf-8", errors="replace"))

    def connect(self):
        self._client.connect(self.broker_host, self.broker_port)
        self._client.loop_start()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: str):
        self._client.publish(topic, payload)

    def subscribe(self, topic: str, callback):
        self._subscriptions[topic] = callback
        self._client.subscribe(topic)
