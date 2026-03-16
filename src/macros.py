import json
import os
import threading
import time
import uuid
from typing import Callable, Dict, Iterable, List, Optional


TRIGGER_CANONICAL = {
    "player_login": "player_join",
    "player_join": "player_join",
    "player_leave": "player_leave",
    "player_death": "player_death",
}

class MacroStore:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._lock = threading.RLock()
        self._macros: List[dict] = []
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self._macros = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            data = []
        if not isinstance(data, list):
            data = []
        with self._lock:
            self._macros = [dict(m) for m in data]

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fp:
            json.dump(self._macros, fp, indent=2)

    def list(self) -> List[dict]:
        with self._lock:
            return [dict(m) for m in self._macros]

    def add_macro(
        self,
        title: str,
        icon: str,
        commands: Iterable[str],
        interval_seconds: int = 0,
        trigger: str = "manual",
    ) -> dict:
        cleaned_commands = [cmd for cmd in (str(c).strip() for c in commands) if cmd]
        trigger = str(trigger or "manual").strip().lower()
        if trigger not in {"manual", "interval", "player_join", "player_leave", "player_death"}:
            trigger = "manual"
        if trigger != "interval":
            interval_seconds = 0
        trigger = TRIGGER_CANONICAL.get(trigger, trigger)
        trigger = TRIGGER_CANONICAL.get(trigger, trigger)
        macro = {
            "id": str(uuid.uuid4()),
            "title": title.strip(),
            "icon": icon or "bi-gear-fill",
            "commands": cleaned_commands,
            "interval_seconds": max(0, int(interval_seconds)) if interval_seconds is not None else 0,
            "times_ran": 0,
            "trigger": trigger,
            "created_at": time.time(),
        }
        with self._lock:
            self._macros.insert(0, macro)
            self._persist()
        return dict(macro)

    def update_macro(
        self,
        macro_id: str,
        title: str,
        icon: str,
        commands: Iterable[str],
        interval_seconds: int = 0,
        trigger: str = "manual",
    ) -> Optional[dict]:
        cleaned_commands = [cmd for cmd in (str(c).strip() for c in commands) if cmd]
        trigger = str(trigger or "manual").strip().lower()
        if trigger not in {"manual", "interval", "player_join", "player_leave", "player_death"}:
            trigger = "manual"
        if trigger != "interval":
            interval_seconds = 0
        trigger = TRIGGER_CANONICAL.get(trigger, trigger)
        with self._lock:
            for idx, existing in enumerate(self._macros):
                if existing.get("id") == macro_id:
                    updated = {
                        "id": macro_id,
                        "title": title.strip(),
                        "icon": icon or "bi-gear-fill",
                        "commands": cleaned_commands,
                        "interval_seconds": max(0, int(interval_seconds)) if interval_seconds is not None else 0,
                        "trigger": trigger,
                        "times_ran": existing.get("times_ran", 0),
                        "created_at": existing.get("created_at", time.time()),
                    }
                    self._macros[idx] = updated
                    self._persist()
                    return dict(updated)
        return None

    def delete_macro(self, macro_id: str) -> bool:
        macro_id = str(macro_id or "").strip()
        if not macro_id:
            return False
        with self._lock:
            for idx, existing in enumerate(self._macros):
                if existing.get("id") == macro_id:
                    del self._macros[idx]
                    self._persist()
                    return True
        return False

    def replace_all(self, macros: list) -> int:
        if not isinstance(macros, list):
            raise ValueError("Macros payload must be a list.")
        cleaned = []
        seen_ids = set()
        for raw in macros:
            if not isinstance(raw, dict):
                continue
            macro_id = str(raw.get("id") or "").strip() or str(uuid.uuid4())
            while macro_id in seen_ids:
                macro_id = str(uuid.uuid4())
            seen_ids.add(macro_id)
            title = str(raw.get("title") or "").strip()
            if not title:
                continue
            icon = str(raw.get("icon") or "bi-gear-fill").strip() or "bi-gear-fill"
            commands_raw = raw.get("commands") or []
            if isinstance(commands_raw, str):
                commands_raw = commands_raw.splitlines()
            if not isinstance(commands_raw, list):
                commands_raw = []
            commands = [cmd for cmd in (str(c).strip() for c in commands_raw) if cmd]
            interval_seconds = raw.get("interval_seconds") or 0
            try:
                interval_seconds = max(0, int(interval_seconds))
            except Exception:
                interval_seconds = 0
            trigger = str(raw.get("trigger") or "manual").strip().lower()
            if trigger not in {"manual", "interval", "player_join", "player_leave", "player_death"}:
                trigger = "manual"
            if trigger != "interval":
                interval_seconds = 0
            trigger = TRIGGER_CANONICAL.get(trigger, trigger)
            existing_times = raw.get("times_ran") or 0
            try:
                existing_times = max(0, int(existing_times))
            except Exception:
                existing_times = 0
            created_at = raw.get("created_at")
            try:
                created_at = float(created_at) if created_at is not None else time.time()
            except Exception:
                created_at = time.time()
            cleaned.append(
                {
                    "id": macro_id,
                    "title": title,
                    "icon": icon,
                    "commands": commands,
                    "interval_seconds": interval_seconds,
                    "times_ran": existing_times,
                    "trigger": trigger,
                    "created_at": created_at,
                }
            )
        with self._lock:
            self._macros = cleaned
            self._persist()
        return len(cleaned)

    def increment_times_ran(self, macro_id: str) -> None:
        if not macro_id:
            return
        macro_id = str(macro_id).strip()
        if not macro_id:
            return
        with self._lock:
            for idx, existing in enumerate(self._macros):
                if existing.get("id") == macro_id:
                    existing_times = existing.get("times_ran", 0) or 0
                    try:
                        existing_times = max(0, int(existing_times))
                    except Exception:
                        existing_times = 0
                    existing["times_ran"] = existing_times + 1
                    self._persist()
                    return


class MacroScheduler:
    def __init__(self, store: MacroStore, command_runner: Callable[[List[str]], None]):
        self.store = store
        self.command_runner = command_runner
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_runs: Dict[str, float] = {}
        self._intervals: Dict[str, int] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        self._thread = None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            macros = self.store.list()
            for macro in macros:
                interval = macro.get("interval_seconds") or 0
                last_interval = self._intervals.get(macro["id"])
                if last_interval != interval:
                    self._next_runs.pop(macro["id"], None)
                    self._intervals[macro["id"]] = interval
                if interval <= 0 or not macro.get("commands"):
                    continue
                next_run = self._next_runs.get(macro["id"])
                if next_run is None:
                    self._next_runs[macro["id"]] = now + interval
                    continue
                if now >= next_run:
                    try:
                        self.command_runner(macro["commands"])
                    except Exception:
                        pass
                    self._next_runs[macro["id"]] = now + interval
            self._stop_event.wait(1)
