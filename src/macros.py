import json
import os
import re
import threading
import time
import uuid
import random
from typing import Callable, Dict, Iterable, List, Optional


TRIGGER_CANONICAL = {
    "player_login": "player_join",
    "player_connected": "player_connected",
    "player_join": "player_join",
    "player_leave": "player_leave",
    "player_death": "player_death",
    "server_started": "server_started",
    "server_stopped": "server_stopped",
    "chat_keyword": "chat_keyword",
}

VALID_TRIGGERS = {
    "manual",
    "interval",
    "time",
    "player_connected",
    "player_join",
    "player_leave",
    "player_death",
    "server_started",
    "server_stopped",
    "chat_keyword",
}

class MacroStore:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._lock = threading.RLock()
        self._macros: List[dict] = []
        self._variables: List[dict] = []
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self._macros = []
            self._variables = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            data = []
        macros = []
        variables = []
        if isinstance(data, list):
            macros = data
        elif isinstance(data, dict):
            macros = data.get("macros") or []
            variables = data.get("variables") or []
        if not isinstance(macros, list):
            macros = []
        if not isinstance(variables, list):
            variables = []
        with self._lock:
            self._macros = [dict(m) for m in macros if isinstance(m, dict)]
            self._variables = [dict(v) for v in variables if isinstance(v, dict)]

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fp:
            json.dump({"macros": self._macros, "variables": self._variables}, fp, indent=2)

    def list(self) -> List[dict]:
        with self._lock:
            return [dict(m) for m in self._macros]

    def list_variables(self) -> List[dict]:
        with self._lock:
            return [dict(v) for v in self._variables]

    @staticmethod
    def _normalize_variable_name(name: str) -> str:
        raw = str(name or "").strip()
        if not raw:
            return ""
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", raw):
            return ""
        return raw

    def set_variables(self, variables: list) -> List[dict]:
        if not isinstance(variables, list):
            raise ValueError("Variables payload must be a list.")
        cleaned = []
        seen = set()
        for raw in variables:
            if not isinstance(raw, dict):
                continue
            name = self._normalize_variable_name(raw.get("name"))
            if not name or name in seen:
                continue
            seen.add(name)
            vtype = str(raw.get("type") or "static").strip().lower()
            if vtype not in {"static", "random"}:
                vtype = "static"
            value = str(raw.get("value") or "").strip()
            items_raw = raw.get("items") or []
            if isinstance(items_raw, str):
                items_raw = [s.strip() for s in items_raw.splitlines()]
            if not isinstance(items_raw, list):
                items_raw = []
            items = [str(x).strip() for x in items_raw if str(x).strip()]
            cleaned.append({"name": name, "type": vtype, "value": value, "items": items})
        with self._lock:
            self._variables = cleaned
            self._persist()
        return [dict(v) for v in cleaned]

    def resolve_variables_for_run(self) -> Dict[str, str]:
        resolved: Dict[str, str] = {}
        with self._lock:
            vars_snapshot = [dict(v) for v in self._variables]
        for v in vars_snapshot:
            name = self._normalize_variable_name(v.get("name"))
            if not name:
                continue
            vtype = str(v.get("type") or "static").strip().lower()
            if vtype == "random":
                items = v.get("items") or []
                if isinstance(items, list):
                    items = [str(x).strip() for x in items if str(x).strip()]
                else:
                    items = []
                resolved[name] = random.choice(items) if items else ""
            else:
                resolved[name] = str(v.get("value") or "")
        return resolved

    def add_macro(
        self,
        title: str,
        icon: str,
        commands: Iterable[str],
        interval_seconds: int = 0,
        time_of_day: str = "",
        trigger: str = "manual",
        chat_keyword: str = "",
    ) -> dict:
        cleaned_commands = [cmd for cmd in (str(c).strip() for c in commands) if cmd]
        trigger = str(trigger or "manual").strip().lower()
        if trigger not in VALID_TRIGGERS:
            trigger = "manual"
        tod = str(time_of_day or "").strip()
        if trigger not in {"interval"}:
            interval_seconds = 0
        if trigger != "time":
            tod = ""
        trigger = TRIGGER_CANONICAL.get(trigger, trigger)
        keyword = str(chat_keyword or "").strip()
        if trigger != "chat_keyword":
            keyword = ""
        tod = self._normalize_time_of_day(tod)
        macro = {
            "id": str(uuid.uuid4()),
            "title": title.strip(),
            "icon": icon or "bi-gear-fill",
            "commands": cleaned_commands,
            "interval_seconds": max(0, int(interval_seconds)) if interval_seconds is not None else 0,
            "time_of_day": tod,
            "times_ran": 0,
            "trigger": trigger,
            "chat_keyword": keyword,
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
        time_of_day: str = "",
        trigger: str = "manual",
        chat_keyword: str = "",
    ) -> Optional[dict]:
        cleaned_commands = [cmd for cmd in (str(c).strip() for c in commands) if cmd]
        trigger = str(trigger or "manual").strip().lower()
        if trigger not in VALID_TRIGGERS:
            trigger = "manual"
        tod = str(time_of_day or "").strip()
        if trigger not in {"interval"}:
            interval_seconds = 0
        if trigger != "time":
            tod = ""
        trigger = TRIGGER_CANONICAL.get(trigger, trigger)
        keyword = str(chat_keyword or "").strip()
        if trigger != "chat_keyword":
            keyword = ""
        tod = self._normalize_time_of_day(tod)
        with self._lock:
            for idx, existing in enumerate(self._macros):
                if existing.get("id") == macro_id:
                    updated = {
                        "id": macro_id,
                        "title": title.strip(),
                        "icon": icon or "bi-gear-fill",
                        "commands": cleaned_commands,
                        "interval_seconds": max(0, int(interval_seconds)) if interval_seconds is not None else 0,
                        "time_of_day": tod,
                        "trigger": trigger,
                        "chat_keyword": keyword,
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
            if trigger not in VALID_TRIGGERS:
                trigger = "manual"
            time_of_day = str(raw.get("time_of_day") or "").strip()
            if trigger not in {"interval"}:
                interval_seconds = 0
            if trigger != "time":
                time_of_day = ""
            trigger = TRIGGER_CANONICAL.get(trigger, trigger)
            keyword = str(raw.get("chat_keyword") or "").strip()
            if trigger != "chat_keyword":
                keyword = ""
            time_of_day = self._normalize_time_of_day(time_of_day)
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
                    "time_of_day": time_of_day,
                    "times_ran": existing_times,
                    "trigger": trigger,
                    "chat_keyword": keyword,
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

    @staticmethod
    def _normalize_time_of_day(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        m = re.match(r"^(\d{1,2}):(\d{2})$", raw)
        if not m:
            return ""
        h = int(m.group(1))
        minute = int(m.group(2))
        if h < 0 or h > 23 or minute < 0 or minute > 59:
            return ""
        return f"{h:02d}:{minute:02d}"


class MacroScheduler:
    def __init__(self, store: MacroStore, command_runner: Callable[[List[str]], None]):
        self.store = store
        self.command_runner = command_runner
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_runs: Dict[str, float] = {}
        self._intervals: Dict[str, int] = {}
        self._times_of_day: Dict[str, str] = {}

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
                trigger = str(macro.get("trigger") or "manual").strip().lower()
                interval = macro.get("interval_seconds") or 0
                last_interval = self._intervals.get(macro["id"])
                if last_interval != interval:
                    self._next_runs.pop(macro["id"], None)
                    self._intervals[macro["id"]] = interval
                time_of_day = str(macro.get("time_of_day") or "").strip()
                last_tod = self._times_of_day.get(macro["id"])
                if last_tod != time_of_day:
                    self._next_runs.pop(macro["id"], None)
                    self._times_of_day[macro["id"]] = time_of_day

                if not macro.get("commands"):
                    continue

                if trigger == "interval":
                    if interval <= 0:
                        continue
                    next_run = self._next_runs.get(macro["id"])
                    if next_run is None:
                        self._next_runs[macro["id"]] = now + interval
                        continue
                    if now >= next_run:
                        try:
                            self.command_runner(macro["commands"], macro_id=macro["id"])
                        except Exception:
                            pass
                        self._next_runs[macro["id"]] = now + interval
                    continue

                if trigger == "time":
                    next_run = self._next_runs.get(macro["id"])
                    if next_run is None:
                        next_ts = self._next_time_of_day_run(now, time_of_day)
                        if next_ts is not None:
                            self._next_runs[macro["id"]] = next_ts
                        continue
                    if now >= next_run:
                        try:
                            self.command_runner(macro["commands"], macro_id=macro["id"])
                        except Exception:
                            pass
                        next_ts = self._next_time_of_day_run(now + 1, time_of_day)
                        if next_ts is not None:
                            self._next_runs[macro["id"]] = next_ts
                        else:
                            self._next_runs.pop(macro["id"], None)
                    continue
            self._stop_event.wait(1)

    @staticmethod
    def _next_time_of_day_run(now_ts: float, time_of_day: str) -> Optional[float]:
        raw = str(time_of_day or "").strip()
        if not raw:
            return None
        m = re.match(r"^(\d{2}):(\d{2})$", raw)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2))
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None

        now = time.localtime(now_ts)
        today_target = time.mktime(
            (now.tm_year, now.tm_mon, now.tm_mday, hour, minute, 0, now.tm_wday, now.tm_yday, now.tm_isdst)
        )
        if today_target > now_ts:
            return float(today_target)

        # Schedule next day.
        tomorrow = time.localtime(now_ts + 86400)
        tomorrow_target = time.mktime(
            (tomorrow.tm_year, tomorrow.tm_mon, tomorrow.tm_mday, hour, minute, 0, tomorrow.tm_wday, tomorrow.tm_yday, tomorrow.tm_isdst)
        )
        return float(tomorrow_target)
