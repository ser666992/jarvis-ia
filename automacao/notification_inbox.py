"""
automacao/notification_inbox.py
===================================
Caixa de entrada em memória de notificações -- originalmente
alimentada pelo app companion do celular (removido do projeto; ver
histórico de commits) via um endpoint HTTP que também foi removido.
Ninguém chama `registrar()` neste momento, então
`todas()`/`mensagens_de()` sempre devolvem vazio -- `plugins/instagram.py`
e `automacao/instagram_auto.py` já tratam isso como esperado e caem
pro fallback via ADB sem fio (`dispositivos/adb.py:list_notifications()`),
que é a fonte real de notificações hoje. Módulo mantido (não removido)
porque `core/diagnostico.py` ainda faz a checagem cruzada das duas
fontes possíveis -- se `registrar()` ganhar um chamador de novo no
futuro (outro app companion, outra integração), a caixa volta a
funcionar sem mudança nenhuma aqui.
"""

import threading
import time

_lock = threading.Lock()
_inbox = []  # [{"pacote": str, "titulo": str, "texto": str, "quando": float}, ...]
_MAX_ITEMS = 200


def registrar(pacote: str, titulo: str, texto: str):
    with _lock:
        _inbox.append({"pacote": pacote, "titulo": titulo, "texto": texto, "quando": time.time()})
        del _inbox[:-_MAX_ITEMS]


def mensagens_de(pacote: str) -> list:
    with _lock:
        return [n for n in _inbox if n.get("pacote") == pacote]


def todas() -> list:
    with _lock:
        return list(_inbox)


def limpar():
    with _lock:
        _inbox.clear()
