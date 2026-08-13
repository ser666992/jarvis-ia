"""
automacao/watcher.py
=======================
Observação de pastas: dispara um callback quando arquivos são
criados/modificados/removidos. Usa `watchdog` se instalado (mais
eficiente, baseado em eventos do SO); senão cai para polling simples
(stdlib, zero dependência, menos eficiente mas sempre funciona).
"""

import os
import threading

from logs.logger import get_logger

log = get_logger("automacao")

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


class FolderWatcher:
    def __init__(self, path: str, on_change=None, poll_interval: float = 2.0):
        self.path = path
        self.on_change = on_change or (lambda event_type, file_path: None)
        self.poll_interval = poll_interval
        self._observer = None
        self._stop = threading.Event()
        self._thread = None

    def backend(self) -> str:
        return "watchdog" if HAS_WATCHDOG else "polling"

    def start(self):
        if HAS_WATCHDOG:
            self._start_watchdog()
        else:
            self._start_polling()

    def _start_watchdog(self):
        on_change = self.on_change

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                on_change("criado", event.src_path)

            def on_modified(self, event):
                on_change("modificado", event.src_path)

            def on_deleted(self, event):
                on_change("removido", event.src_path)

        self._observer = Observer()
        self._observer.schedule(Handler(), self.path, recursive=False)
        self._observer.start()

    def _start_polling(self):
        self._stop.clear()

        def _snapshot():
            try:
                return {f: os.path.getmtime(os.path.join(self.path, f)) for f in os.listdir(self.path)}
            except OSError:
                return {}

        def _run():
            known = _snapshot()
            while not self._stop.is_set():
                self._stop.wait(self.poll_interval)
                current = _snapshot()
                for f in current:
                    if f not in known:
                        self.on_change("criado", os.path.join(self.path, f))
                    elif current[f] != known[f]:
                        self.on_change("modificado", os.path.join(self.path, f))
                for f in known:
                    if f not in current:
                        self.on_change("removido", os.path.join(self.path, f))
                known = current

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
        self._stop.set()
