import json
import threading
from typing import Iterable


class RealtimeHub:
    def __init__(self) -> None:
        self._clients = set()
        self._lock = threading.Lock()

    def register(self, ws) -> None:
        with self._lock:
            self._clients.add(ws)

    def unregister(self, ws) -> None:
        with self._lock:
            self._clients.discard(ws)

    def send(self, ws, message: dict) -> None:
        ws.send(json.dumps(message))

    def broadcast(self, message: dict) -> None:
        payload = json.dumps(message)
        dead = []
        with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                ws.send(payload)
            except Exception:
                dead.append(ws)
        if dead:
            with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def broadcast_logs(self, lines: Iterable[str]) -> None:
        entries = [str(line) for line in lines if line is not None]
        if not entries:
            return
        self.broadcast({"type": "logs", "lines": entries})
