import os
import queue
import re
import subprocess
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

from macros import MacroScheduler, MacroStore
from properties_file import PropertiesFile
from server_validation import server_launch_command
from settings_store import load_settings, macros_path, save_settings
from WebManager import WebManagerServer
from logger import debug


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

DEFAULT_MACROS_FILE_PATH = os.path.abspath(macros_path())


class ManagerCore:
    """
    UI-agnostic core manager.

    - Owns the server process, log parsing, macro execution, and the Flask WebManagerServer.
    - Exposes a `server_queue` of stdout lines and parsed events for UIs to consume.
    - Stores recent logs in `web_logs` for the Web UI.
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        macros_path: Optional[str] = None,
        log_sink: Optional[Callable[[str], None]] = None,
        web_manager: Optional[WebManagerServer] = None,
    ):
        self.settings = settings if isinstance(settings, dict) else load_settings()
        save_settings(self.settings)

        self.server_process: Optional[subprocess.Popen] = None
        self.server_backend: Optional[str] = None
        self.server_start_time: Optional[float] = None

        self.server_queue: "queue.Queue[object]" = queue.Queue()
        self.web_logs: Deque[str] = deque(maxlen=400)
        self.live_players: set[str] = set()
        self.properties: Optional[PropertiesFile] = None

        self._log_sink = log_sink or (lambda line: None)
        self._server_reader_thread: Optional[threading.Thread] = None
        self._log_tailer_thread: Optional[threading.Thread] = None
        self._log_tailer_stop: Optional[threading.Event] = None

        macros_file = macros_path or DEFAULT_MACROS_FILE_PATH
        self.macro_store = MacroStore(macros_file)
        self.macro_scheduler = MacroScheduler(self.macro_store, self._run_macro_commands)
        self.macro_scheduler.start()

        self.web_manager = web_manager or WebManagerServer(
            status_provider=self.status_payload,
            command_handler=self.web_command_handler,
            macros_provider=self.macro_payload,
            macro_creator=self.macro_creator_handler,
        )

    # ---- lifecycle ----

    def close(self) -> None:
        debug("ManagerCore.close()")
        self.stop_server()
        self.stop_web_manager()
        self.macro_scheduler.stop()

    # ---- web manager ----

    def start_web_manager(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        if self.web_manager.is_running():
            return
        debug("Starting web manager (core)")
        host = host or (self.settings.get("web_manager_host") or "127.0.0.1")
        port = int(port or self.settings.get("web_manager_port") or 5050)
        self.web_manager.start(host, port)
        self.settings["web_manager_host"] = host
        self.settings["web_manager_port"] = port
        save_settings(self.settings)
        debug("Web manager started (core) at {}", self.web_manager.url())
        self._log(f"[Web] Running at {self.web_manager.url()}\n")

    def stop_web_manager(self) -> None:
        debug("Stopping web manager (core)")
        self.web_manager.stop()
        debug("Web manager stopped (core)")

    # ---- server ----

    def start_server(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            return
        debug("Starting server (core)")
        server_dir = (self.settings.get("server_dir") or "").strip()
        if not server_dir or not os.path.isdir(server_dir):
            raise RuntimeError("Server directory is not set or does not exist.")
        backend_pref = (self.settings.get("server_backend") or "auto").lower()
        launch_cmd, backend = server_launch_command(server_dir, preferred_backend=backend_pref)
        if not launch_cmd:
            raise RuntimeError("Server executable not found.")

        self.server_process = subprocess.Popen(
            launch_cmd,
            cwd=server_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.server_backend = backend
        self.server_start_time = time.time()
        debug("Server started (core) backend={}", backend)
        self.web_logs.clear()
        self._append_web_log("Server started.\n")
        self._trigger_macros_for_event("server_started", None)
        self._refresh_properties()
        self.web_manager.push_status()

        self._server_reader_thread = threading.Thread(target=self._server_reader, daemon=True)
        self._server_reader_thread.start()
        self._start_log_tailer(server_dir, backend)

    def stop_server(self) -> None:
        proc = self.server_process
        if not proc or proc.poll() is not None:
            return
        debug("Stopping server (core)")
        try:
            if proc.stdin:
                proc.stdin.write("stop\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        self._stop_log_tailer()
        self.server_process = None
        self.server_backend = None
        self.server_start_time = None
        self.live_players.clear()
        self.properties = None
        self.web_manager.push_status()
        debug("Server stopped (core)")

    def send_command(self, cmd: str) -> None:
        cmd = (cmd or "").strip()
        if not cmd:
            return
        proc = self.server_process
        if not proc or proc.poll() is not None or not proc.stdin:
            return
        try:
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()
            self._append_web_log(f"> {cmd}\n")
        except Exception:
            pass

    # ---- queue draining (for UI consumers) ----

    def drain_queue(self) -> None:
        """Drain parsed events/log lines and update internal state."""
        status_changed = False
        try:
            while True:
                item = self.server_queue.get_nowait()
                if isinstance(item, tuple):
                    event, value = item
                    if event == "player_connected":
                        if value:
                            self.live_players.add(value)
                            self._trigger_macros_for_event("player_connected", value)
                            status_changed = True
                    elif event == "player_join":
                        if value:
                            self.live_players.add(value)
                            self._trigger_macros_for_event("player_join", value)
                            status_changed = True
                    elif event == "player_leave":
                        if value:
                            self.live_players.discard(value)
                            self._trigger_macros_for_event("player_leave", value)
                            status_changed = True
                    elif event == "player_death":
                        if value:
                            self._trigger_macros_for_event("player_death", value)
                    elif event == "server_stopped":
                        self.live_players.clear()
                        self._trigger_macros_for_event("server_stopped", None)
                        status_changed = True
                    elif event == "chat_message":
                        if isinstance(value, dict):
                            self._trigger_macros_for_chat_keyword(value.get("player"), value.get("message"))
                    continue
                self._append_web_log(str(item))
        except queue.Empty:
            return
        finally:
            if status_changed:
                self.web_manager.push_status()

    # ---- web UI providers/handlers ----

    def status_payload(self) -> dict:
        running = bool(self.server_process and self.server_process.poll() is None)
        self._refresh_properties()
        props = self.properties.data if self.properties and self.properties.data else {}
        backups = self._list_backups()
        return {
            "bedrock": {
                "running": running,
                "port": props.get("server-port", "-"),
                "gamemode": props.get("gamemode", "-"),
                "connected": len(self.live_players),
                "max_players": props.get("max-players", "-"),
                "backend": self.server_backend if running else "-",
                "backend_preference": (self.settings.get("server_backend", "auto") or "auto").lower(),
                "autostart_server": bool(self.settings.get("autostart_server", False)),
            },
            "web_manager": {
                "running": self.web_manager.is_running(),
                "host": self.web_manager.host,
                "port": self.web_manager.port,
                "url": self.web_manager.url(),
            },
            "players": sorted(self.live_players),
            "operators": [],
            "properties": props,
            "backups": backups,
            "logs": list(self.web_logs),
            "chat": {
                "use_chat_logger_plugin": bool(self.settings.get("use_chat_logger_plugin", False)),
            },
            "network": {"local_ip": "-", "public_ip": "-", "port": props.get("server-port", "19132")},
            "server_start_time": self.server_start_time if running else None,
            "server_uptime_seconds": (time.time() - self.server_start_time) if (running and self.server_start_time) else 0,
            "backup_in_progress": False,
            "backup_error": None,
        }

    def web_command_handler(self, action: str, data: dict = None):
        if action == "start_server":
            self.start_server()
            return {"success": True}
        if action == "stop_server":
            self.stop_server()
            return {"success": True}
        if action == "refresh_players":
            return {"success": True}
        if action == "send_command" and data:
            cmd = data.get("command")
            if cmd:
                self.send_command(str(cmd))
                return {"success": True}
            return {"error": "No command provided"}
        if action == "set_server_backend" and data:
            backend = (data.get("backend") or "").strip().lower()
            if backend not in {"auto", "endstone", "bedrock"}:
                return {"error": "Invalid backend. Use auto/endstone/bedrock."}
            self.settings["server_backend"] = backend
            save_settings(self.settings)
            return {"scheduled": True}
        if action == "set_autostart_server" and data is not None:
            self.settings["autostart_server"] = bool(data.get("enabled", False))
            save_settings(self.settings)
            return {"scheduled": True}
        if action == "set_use_chat_logger_plugin" and data is not None:
            self.settings["use_chat_logger_plugin"] = bool(data.get("enabled", False))
            save_settings(self.settings)
            self.web_manager.push_status()
            return {"scheduled": True}
        if action == "run_macro" and data:
            commands = data.get("commands") or []
            macro_id = data.get("macro_id")
            player_name = data.get("player_name", "")
            message = data.get("message", "")
            if commands:
                self._run_macro_commands(commands, macro_id=macro_id, player_name=player_name, message=message)
                return {"success": True}
            return {"error": "No commands provided"}
        return {"error": f"Unknown action {action}"}

    # ---- macros (web + core) ----

    def macro_payload(self):
        return {"macros": self.macro_store.list(), "presets": [], "variables": self.macro_store.list_variables()}

    def macro_creator_handler(self, payload: dict):
        if payload.get("set_variables"):
            variables = payload.get("variables")
            if variables is None:
                return {"error": "Variables payload is required"}
            try:
                cleaned = self.macro_store.set_variables(variables)
            except Exception as exc:
                return {"error": str(exc) or "Failed to save variables"}
            return {"variables_saved": True, "variables": cleaned}

        if payload.get("delete"):
            macro_id = str(payload.get("id") or "").strip()
            if not macro_id:
                return {"error": "Macro ID is required for delete"}
            deleted = self.macro_store.delete_macro(macro_id)
            if not deleted:
                return {"error": "Macro not found"}
            return {"deleted": True}

        title = str(payload.get("title") or "").strip()
        if not title:
            return {"error": "Macro title is required"}
        commands = payload.get("commands")
        if isinstance(commands, str):
            commands = [line.strip() for line in commands.splitlines() if line.strip()]
        elif isinstance(commands, list):
            commands = [str(c).strip() for c in commands if str(c).strip()]
        else:
            commands = []
        if not commands:
            return {"error": "At least one command is required"}
        icon = str(payload.get("icon") or "bi-gear-fill").strip()
        trigger = str(payload.get("trigger") or "manual").strip().lower()
        if trigger not in VALID_TRIGGERS:
            trigger = "manual"
        trigger = TRIGGER_CANONICAL.get(trigger, trigger)
        chat_keyword = str(payload.get("chat_keyword") or "").strip()
        if trigger != "chat_keyword":
            chat_keyword = ""
        time_of_day = str(payload.get("time_of_day") or "").strip()
        if trigger != "time":
            time_of_day = ""
        interval_seconds = 0
        try:
            interval_seconds = int(payload.get("interval_seconds", 0) or 0)
        except Exception:
            interval_seconds = 0
        macro_id = payload.get("id")
        if macro_id:
            updated = self.macro_store.update_macro(
                macro_id=macro_id,
                title=title,
                icon=icon or "bi-gear-fill",
                commands=commands,
                interval_seconds=interval_seconds,
                time_of_day=time_of_day,
                trigger=trigger,
                chat_keyword=chat_keyword,
            )
            if not updated:
                return {"error": "Macro not found"}
            return updated
        return self.macro_store.add_macro(
            title=title,
            icon=icon or "bi-gear-fill",
            commands=commands,
            interval_seconds=interval_seconds,
            time_of_day=time_of_day,
            trigger=trigger,
            chat_keyword=chat_keyword,
        )

    def _run_macro_commands(self, commands: List[str], macro_id: Optional[str] = None, player_name: str = "", message: str = "") -> None:
        if macro_id:
            self.macro_store.increment_times_ran(macro_id)
        resolved_vars = {}
        try:
            resolved_vars = self.macro_store.resolve_variables_for_run()
        except Exception:
            resolved_vars = {}
        msg = str(message or "")
        msg_text = msg
        msg_keyword = ""
        if msg:
            msg_keyword = msg.split()[0]
            msg_text = msg[len(msg_keyword):].lstrip() if msg.lower().startswith(msg_keyword.lower()) else msg
        for cmd in commands:
            rendered = (
                str(cmd or "")
                .replace("{player}", player_name)
                .replace("{message}", msg)
                .replace("{message_keyword}", msg_keyword)
                .replace("{message_text}", msg_text)
            )
            if resolved_vars:
                def _repl(match):
                    key = match.group(1)
                    if key in {"player", "message", "message_keyword", "message_text"}:
                        return match.group(0)
                    return str(resolved_vars.get(key, match.group(0)))

                rendered = re.sub(r"\{([A-Za-z_][A-Za-z0-9_-]*)\}", _repl, rendered)
            self.send_command(rendered)

    def _trigger_macros_for_event(self, trigger_event: str, player_name: Optional[str] = None) -> None:
        if not trigger_event:
            return
        name = str(player_name or "").strip() if player_name else ""
        try:
            macros = self.macro_store.list()
        except Exception:
            return
        for macro in macros:
            if not isinstance(macro, dict):
                continue
            stored_trigger = TRIGGER_CANONICAL.get(
                str(macro.get("trigger") or "").strip().lower(),
                (macro.get("trigger") or "manual").strip().lower(),
            )
            if stored_trigger != trigger_event:
                continue
            commands = macro.get("commands") or []
            if not commands:
                continue
            self._run_macro_commands(commands, macro_id=macro.get("id"), player_name=name)

    def _trigger_macros_for_chat_keyword(self, player_name: Optional[str] = None, message: str = "") -> None:
        msg = str(message or "")
        if not msg:
            return
        name = str(player_name or "").strip() if player_name else ""
        try:
            macros = self.macro_store.list()
        except Exception:
            return
        for macro in macros:
            if not isinstance(macro, dict):
                continue
            stored_trigger = TRIGGER_CANONICAL.get(
                str(macro.get("trigger") or "").strip().lower(),
                (macro.get("trigger") or "manual").strip().lower(),
            )
            if stored_trigger != "chat_keyword":
                continue
            keyword = str(macro.get("chat_keyword") or "").strip()
            if not keyword:
                continue
            if keyword.lower() not in msg.lower():
                continue
            commands = macro.get("commands") or []
            if not commands:
                continue
            self._run_macro_commands(commands, macro_id=macro.get("id"), player_name=name, message=msg)

    # ---- properties/backups ----

    def _refresh_properties(self) -> None:
        server_dir = (self.settings.get("server_dir") or "").strip()
        if not server_dir or not os.path.isdir(server_dir):
            self.properties = None
            return
        props_path = os.path.join(server_dir, "server.properties")
        props = PropertiesFile(props_path)
        try:
            props.load()
        except Exception:
            props.data = {}
        self.properties = props

    def _list_backups(self) -> List[dict]:
        backups_dir = (self.settings.get("backups_dir") or "").strip()
        if not backups_dir or not os.path.isdir(backups_dir):
            return []
        backups: List[dict] = []
        for name in sorted(os.listdir(backups_dir)):
            path = os.path.join(backups_dir, name)
            try:
                mtime = os.path.getmtime(path)
                size = self._path_size(path)
                backups.append(
                    {
                        "name": name,
                        "size": self._format_size(size),
                        "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                        "timestamp": mtime,
                    }
                )
            except OSError:
                continue
        return backups

    def _path_size(self, path: str) -> int:
        if os.path.isfile(path):
            try:
                return os.path.getsize(path)
            except OSError:
                return 0
        total = 0
        for root, _dirs, files in os.walk(path):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    total += os.path.getsize(fpath)
                except OSError:
                    continue
        return total

    def _format_size(self, size_bytes: int) -> str:
        try:
            size = float(size_bytes)
        except Exception:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        while size >= 1024 and idx < len(units) - 1:
            size /= 1024
            idx += 1
        if idx == 0:
            return f"{int(size)} {units[idx]}"
        if idx == 1:
            return f"{int(round(size))} {units[idx]}"
        return f"{size:.1f} {units[idx]}"

    # ---- log/event parsing ----

    def _log(self, line: str) -> None:
        try:
            self._log_sink(line)
        except Exception:
            pass

    def _append_web_log(self, line: str) -> None:
        if line is None:
            return
        text = str(line)
        self.web_logs.append(text)
        self._log(text)
        self.web_manager.push_logs([text])

    def _server_reader(self) -> None:
        proc = self.server_process
        if not proc or not proc.stdout:
            return
        try:
            for line in proc.stdout:
                if not line:
                    continue
                self.server_queue.put(line)
                parsed = self._parse_player_event(line)
                if parsed:
                    self.server_queue.put(parsed)
                chat = self._parse_chat_message(line)
                if chat:
                    self.server_queue.put(("chat_message", chat))
        except Exception as exc:
            self.server_queue.put(f"[Console error] {exc}\n")
        finally:
            self.server_queue.put("[Server stopped]\n")
            self.server_queue.put(("server_stopped", None))

    def _clean_player_name(self, raw_name: str) -> str:
        name = str(raw_name or "").strip()
        if not name:
            return ""
        name = re.sub(r"\s+xuid:.*$", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\s+pfid:.*$", "", name, flags=re.IGNORECASE).strip()
        if "," in name:
            name = name.split(",", 1)[0].strip()
        return name

    def _parse_player_event(self, line: str) -> Optional[Tuple[str, str]]:
        joined_patterns = [
            r"\]:\s*(?P<name>.+?)\s+joined the game\b",
            r"\]:\s*Player\s+(?P<name>.+?)\s+joined\b",
        ]
        for pattern in joined_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                name = self._clean_player_name(match.group("name"))
                if name:
                    return ("player_join", name)

        connected = re.search(r"Player connected:\s*(?P<name>.+?)(?:,|\s+xuid:|$)", line, re.IGNORECASE)
        if connected:
            name = self._clean_player_name(connected.group("name"))
            if name:
                return ("player_connected", name)

        spawned = re.search(r"Player Spawned:\s*(?P<name>.+?)(?:,|\s+xuid:|$)", line, re.IGNORECASE)
        if spawned:
            name = self._clean_player_name(spawned.group("name"))
            if name:
                return ("player_connected", name)

        leave_patterns = [
            r"Player disconnected:\s*(?P<name>.+?)(?:,|\s+xuid:|$)",
            r"\]:\s*(?P<name>.+?)\s+left the game\b",
            r"\]:\s*Player\s+(?P<name>.+?)\s+left\b",
            r"Lost connection:\s*(?P<name>.+?)(?:,|\s+xuid:|$)",
        ]
        for pattern in leave_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                name = self._clean_player_name(match.group("name"))
                if name:
                    return ("player_leave", name)

        death = self._match_player_death(line)
        if death:
            return ("player_death", death)
        return None

    def _parse_chat_message(self, line: str) -> Optional[dict]:
        text = str(line or "").strip("\n")
        if not text:
            return None
        use_chat_logger_plugin = bool(self.settings.get("use_chat_logger_plugin", False))
        if (not use_chat_logger_plugin) and ("[CHAT]" in text):
            return None
        patterns = [
            r"\[CHAT\]\s*(?P<name>[^:]{1,32})\s*:\s*(?P<message>.+)$",
            r"\]:\s*<(?P<name>[^>]+)>\s*(?P<message>.+)$",
            r"\]:\s*(?P<name>[^:]{1,32})\s*:\s*(?P<message>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            name = self._clean_player_name(match.group("name"))
            message = (match.group("message") or "").strip()
            if not name or not message:
                continue
            if use_chat_logger_plugin and "[CHAT]" not in text and pattern != patterns[0]:
                continue
            return {"player": name, "message": message}
        return None

    def _match_player_death(self, line: str) -> Optional[str]:
        match = re.search(
            r"\b(?P<player>[A-Za-z0-9_]+)\b.*\b(?:slain|killed|died|fell|burned|shot|exploded|blew|hit)\b",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group("player").strip()
        return None

    # ---- endstone log tailer ----

    def _start_log_tailer(self, server_dir: str, backend: Optional[str]) -> None:
        self._stop_log_tailer()
        if (backend or "").lower() != "endstone":
            return
        stop_event = threading.Event()
        self._log_tailer_stop = stop_event
        self._log_tailer_thread = threading.Thread(
            target=self._log_tailer_loop, args=(server_dir, stop_event), daemon=True
        )
        self._log_tailer_thread.start()

    def _stop_log_tailer(self) -> None:
        stop_event = self._log_tailer_stop
        thread = self._log_tailer_thread
        if stop_event:
            stop_event.set()
        if thread and thread.is_alive():
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass
        self._log_tailer_stop = None
        self._log_tailer_thread = None

    def _pick_log_file(self, server_dir: str) -> Optional[str]:
        logs_dir = os.path.join(server_dir, "logs")
        if not os.path.isdir(logs_dir):
            return None
        candidates: List[Tuple[float, str]] = []
        try:
            for name in os.listdir(logs_dir):
                if not name.lower().endswith(".log"):
                    continue
                path = os.path.join(logs_dir, name)
                if os.path.isfile(path):
                    try:
                        candidates.append((os.path.getmtime(path), path))
                    except Exception:
                        continue
        except Exception:
            return None
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _log_tailer_loop(self, server_dir: str, stop_event: threading.Event) -> None:
        path = None
        fp = None
        pos = 0
        try:
            while not stop_event.is_set():
                picked = self._pick_log_file(server_dir)
                if picked and picked != path:
                    try:
                        if fp:
                            fp.close()
                    except Exception:
                        pass
                    path = picked
                    try:
                        fp = open(path, "r", encoding="utf-8", errors="replace")
                        fp.seek(0, os.SEEK_END)
                        pos = fp.tell()
                    except Exception:
                        fp = None
                        path = None

                if not fp:
                    stop_event.wait(1.0)
                    continue

                fp.seek(pos)
                line = fp.readline()
                if not line:
                    try:
                        pos = fp.tell()
                    except Exception:
                        pos = 0
                    stop_event.wait(0.25)
                    continue

                pos = fp.tell()
                self.server_queue.put(line)
                parsed = self._parse_player_event(line)
                if parsed:
                    self.server_queue.put(parsed)
        finally:
            try:
                if fp:
                    fp.close()
            except Exception:
                pass
