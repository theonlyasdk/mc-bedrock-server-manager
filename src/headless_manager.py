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
from settings_store import load_settings, save_settings
from WebManager import WebManagerServer


TRIGGER_CANONICAL = {
    "player_login": "player_join",
    "player_join": "player_join",
    "player_leave": "player_leave",
    "player_death": "player_death",
}

MACROS_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "macros.json"))


class HeadlessManager:
    def __init__(
        self,
        server_dir: Optional[str] = None,
        backend_preference: Optional[str] = None,
        web_host: Optional[str] = None,
        web_port: Optional[int] = None,
        macros_path: Optional[str] = None,
        log_sink: Optional[Callable[[str], None]] = None,
    ):
        self.settings = load_settings()
        if server_dir is not None:
            self.settings["server_dir"] = server_dir
        if backend_preference is not None:
            self.settings["server_backend"] = backend_preference
        if web_host is not None:
            self.settings["web_manager_host"] = web_host
        if web_port is not None:
            self.settings["web_manager_port"] = int(web_port)
        save_settings(self.settings)

        self.server_process: Optional[subprocess.Popen] = None
        self.server_backend: Optional[str] = None
        self.server_start_time: Optional[float] = None

        self.server_queue: "queue.Queue[object]" = queue.Queue()
        self.web_logs: Deque[str] = deque(maxlen=400)
        self.live_players: set[str] = set()
        self.properties = None

        self._stop_event = threading.Event()
        self._server_reader_thread: Optional[threading.Thread] = None
        self._log_tailer_thread: Optional[threading.Thread] = None
        self._log_tailer_stop: Optional[threading.Event] = None

        self._log_sink = log_sink or (lambda line: None)

        macros_file = macros_path or MACROS_FILE_PATH
        self.macro_store = MacroStore(macros_file)
        self.macro_scheduler = MacroScheduler(self.macro_store, self._run_macro_commands)
        self.macro_scheduler.start()

        self.web_manager = WebManagerServer(
            status_provider=self._web_manager_status_payload,
            command_handler=self._web_manager_command_handler,
            macros_provider=self._macro_list_payload,
            macro_creator=self._macro_creator_handler,
        )

    def close(self) -> None:
        self._stop_event.set()
        self.stop_server()
        self.stop_web_manager()
        self.macro_scheduler.stop()

    def start_web_manager(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        if self.web_manager.is_running():
            return
        host = host or (self.settings.get("web_manager_host") or "127.0.0.1")
        port = int(port or self.settings.get("web_manager_port") or 5050)
        self.web_manager.start(host, port)
        self.settings["web_manager_host"] = host
        self.settings["web_manager_port"] = port
        save_settings(self.settings)
        self._log(f"[Web] Running at {self.web_manager.url()}\n")

    def stop_web_manager(self) -> None:
        self.web_manager.stop()

    def start_server(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            return
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
        self._refresh_properties()
        self.web_logs.clear()
        self.web_logs.append("Server started.\n")
        self._log("Server started.\n")
        self._server_reader_thread = threading.Thread(target=self._server_reader, daemon=True)
        self._server_reader_thread.start()
        self._start_log_tailer(server_dir, backend)

    def stop_server(self) -> None:
        proc = self.server_process
        if not proc or proc.poll() is not None:
            return
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

    def run_forever(self) -> None:
        try:
            while not self._stop_event.is_set():
                self._drain_server_queue()
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def _log(self, line: str) -> None:
        try:
            self._log_sink(line)
        except Exception:
            pass

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
        except Exception as exc:
            self.server_queue.put(f"[Console error] {exc}\n")
        finally:
            self.server_queue.put("[Server stopped]\n")
            self.server_queue.put(("server_stopped", None))

    def _drain_server_queue(self) -> None:
        try:
            while True:
                item = self.server_queue.get_nowait()
                if isinstance(item, tuple):
                    event, value = item
                    if event == "player_connected":
                        if value:
                            self.live_players.add(value)
                    elif event == "player_join":
                        if value:
                            self.live_players.add(value)
                            self._trigger_macros_for_event("player_join", value)
                    elif event == "player_leave":
                        if value:
                            self.live_players.discard(value)
                            self._trigger_macros_for_event("player_leave", value)
                    elif event == "player_death":
                        if value:
                            self._trigger_macros_for_event("player_death", value)
                    elif event == "server_stopped":
                        self.live_players.clear()
                    continue
                self.web_logs.append(str(item))
                self._log(str(item))
        except queue.Empty:
            return

    def _web_send_command(self, cmd: str) -> None:
        proc = self.server_process
        if not proc or proc.poll() is not None or not proc.stdin:
            return
        cmd = (cmd or "").strip()
        if not cmd:
            return
        try:
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()
            self.web_logs.append(f"> {cmd}\n")
            self._log(f"> {cmd}\n")
        except Exception:
            pass

    def _run_macro_commands(self, commands: List[str], macro_id: Optional[str] = None) -> None:
        if macro_id:
            self.macro_store.increment_times_ran(macro_id)
        for cmd in commands:
            self._web_send_command(cmd)

    def _trigger_macros_for_event(self, trigger_event: str, player_name: str) -> None:
        if not player_name or not trigger_event:
            return
        name = str(player_name or "").strip()
        if not name:
            return
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
            rendered = [str(cmd or "").replace("{player}", name) for cmd in commands]
            self._run_macro_commands(rendered, macro_id=macro.get("id"))

    def _macro_list_payload(self):
        return {"macros": self.macro_store.list(), "presets": []}

    def _macro_creator_handler(self, payload: dict):
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
        if trigger not in {"manual", "interval", "player_join", "player_leave", "player_death"}:
            trigger = "manual"
        trigger = TRIGGER_CANONICAL.get(trigger, trigger)
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
                trigger=trigger,
            )
            if not updated:
                return {"error": "Macro not found"}
            return updated
        return self.macro_store.add_macro(
            title=title,
            icon=icon or "bi-gear-fill",
            commands=commands,
            interval_seconds=interval_seconds,
            trigger=trigger,
        )

    def _web_manager_command_handler(self, action: str, data: dict = None):
        if action == "start_server":
            self.start_server()
            return {"success": True}
        if action == "stop_server":
            self.stop_server()
            return {"success": True}
        if action == "send_command" and data:
            cmd = data.get("command")
            if cmd:
                self._web_send_command(str(cmd))
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
        return {"error": f"Unknown action {action}"}

    def _web_manager_status_payload(self) -> dict:
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
            "network": {"local_ip": "-", "public_ip": "-", "port": props.get("server-port", "19132")},
            "server_start_time": self.server_start_time if running else None,
            "server_uptime_seconds": (time.time() - self.server_start_time) if (running and self.server_start_time) else 0,
            "backup_in_progress": False,
            "backup_error": None,
        }

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
            r"\b(?P<name>.+?)\s+left the game\b",
            r"\bPlayer\s+(?P<name>.+?)\s+left\b",
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

    def _match_player_death(self, line: str) -> Optional[str]:
        match = re.search(
            r"\b(?P<player>[A-Za-z0-9_]+)\b.*\b(?:slain|killed|died|fell|burned|shot|exploded|blew|hit)\b",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group("player").strip()
        return None

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
