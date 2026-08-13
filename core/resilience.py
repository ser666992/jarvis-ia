"""Circuit breaker leve para impedir loops de falha em plugins e provedores."""

import threading
import time

_lock = threading.Lock()
_state = {}


def allowed(name: str, cooldown_seconds: int = 60) -> bool:
    with _lock:
        item = _state.get(name)
        if not item:
            return True
        if item["failures"] < 3:
            return True
        if time.monotonic() - item["last_failure"] >= cooldown_seconds:
            _state.pop(name, None)
            return True
        return False


def success(name: str):
    with _lock:
        _state.pop(name, None)


def failure(name: str):
    with _lock:
        item = _state.setdefault(name, {"failures": 0, "last_failure": 0.0})
        item["failures"] += 1
        item["last_failure"] = time.monotonic()


def status() -> dict:
    with _lock:
        return {key: dict(value) for key, value in _state.items()}


def reset(name: str = None):
    with _lock:
        if name:
            _state.pop(name, None)
        else:
            _state.clear()
