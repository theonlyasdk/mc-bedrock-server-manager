import json
import os
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
import zipfile
from collections import deque
from tkinter import filedialog, messagebox, ttk
from typing import Optional
from uuid import uuid4

from constants import APP_AUTHOR, APP_LICENSE, APP_NAME
from dialogs import confirm_dialog, prompt_string, show_validation_dialog
from properties_file import PropertiesFile
from server_validation import (
    server_dir_missing_files,
    server_launch_command,
    validate_properties_data,
)
from settings_store import load_settings, save_settings
from theme import apply_theme
from WebManager import WebManagerServer
from core_manager import ManagerCore
from macros import MacroStore

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

MACROS_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "macros.json"))
WELCOME_MESSAGE = {"rawtext": [{"text": "Welcome, {player}!"}]}
PRESET_MACROS = [
    {
        "id": "preset-login-message",
        "title": "Login message",
        "icon": "bi-box-arrow-in-right",
        "commands": [
            f"tellraw {{player}} {json.dumps(WELCOME_MESSAGE)}"
        ],
        "trigger": "player_join",
        "description": "Send a friendly greeting when someone logs in.",
    },
    {
        "id": "preset-auto-save",
        "title": "Auto-Save World",
        "icon": "bi-save",
        "commands": ["save hold", "save query", "save resume"],
        "trigger": "interval",
        "interval_seconds": 3600,
        "description": "Force a world save every hour.",
    },
    {
        "id": "preset-clear-lag",
        "title": "Clear Entities (Lag Fix)",
        "icon": "bi-trash",
        "commands": ["kill @e[type=item]", "say Lag cleared: Dropped items removed."],
        "trigger": "manual",
        "description": "Remove all dropped items from the world to reduce lag.",
    },
    {
        "id": "preset-day-cycle",
        "title": "Always Day",
        "icon": "bi-sun",
        "commands": ["alwaysday on", "time set day"],
        "trigger": "server_started",
        "description": "Ensures it is always daytime when the server starts.",
    },
    {
        "id": "preset-op-creative",
        "title": "OP Creative Mode",
        "icon": "bi-shield-check",
        "commands": ["gamemode creative @p[tag=admin]", "ability @p[tag=admin] mayfly true"],
        "trigger": "player_join",
        "description": "Automatically set admins to creative mode and enable flight.",
    },
    {
        "id": "preset-world-border-warn",
        "title": "Border Warning",
        "icon": "bi-exclamation-triangle",
        "commands": ["titleraw @a actionbar {\"rawtext\":[{\"text\":\"§cWarning: Stay within the server borders!\"}]}"],
        "trigger": "interval",
        "interval_seconds": 300,
        "description": "Display a recurring warning in the action bar.",
    },
    {
        "id": "preset-death-coordinates",
        "title": "Death Notification",
        "icon": "bi-skull",
        "commands": ["tellraw @a {\"rawtext\":[{\"text\":\"§e{player} §7has fallen at their current location.\"}]}"],
        "trigger": "player_death",
        "description": "Notify all players when someone dies.",
    },
    {
        "id": "preset-rest-reminder",
        "title": "Rest Reminder",
        "icon": "bi-alarm",
        "commands": ["say §bRemember to take a break and hydrate!"],
        "trigger": "interval",
        "interval_seconds": 7200,
        "description": "Send a friendly reminder every 2 hours.",
    },
    {
        "id": "preset-maintenance-mode",
        "title": "Maintenance Start",
        "icon": "bi-hammer",
        "commands": ["say §cServer entering maintenance in 1 minute!", "wait 60", "kick @a Server maintenance in progress.", "whitelist on"],
        "trigger": "manual",
        "description": "Warn players, kick everyone, and enable whitelist.",
    },
    {
        "id": "preset-welcome-kit",
        "title": "New Player Kit",
        "icon": "bi-gift",
        "commands": ["give {player} stone_sword", "give {player} bread 16", "give {player} torch 32"],
        "trigger": "player_join",
        "description": "Give basic tools and food to joining players.",
    },
    {
        "id": "preset-weather-clear",
        "title": "Clear Weather",
        "icon": "bi-cloud-sun",
        "commands": ["weather clear"],
        "trigger": "chat_keyword",
        "chat_keyword": "!sun",
        "description": "Clears the weather when someone types !sun in chat.",
    },
    {
        "id": "preset-center-title",
        "title": "Center Screen Text",
        "icon": "bi-chat-square-text",
        "commands": ["title @a title {message_text}"],
        "trigger": "chat_keyword",
        "chat_keyword": "!title",
        "description": "Type in chat: !title Your message (shows a centered title).",
    }
]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x600")
        apply_theme()
        self.style = ttk.Style()

        self.settings = load_settings()
        self.properties = None
        self.server_process = None
        self.server_start_time = None
        self.server_start_monotonic = None
        self.server_backend = None
        self._server_dir_running = None
        self._perf_prev = None
        self.core = ManagerCore(settings=self.settings, macros_path=MACROS_FILE_PATH)
        self.server_queue = self.core.server_queue
        self.live_players = self.core.live_players
        self.web_logs = self.core.web_logs
        self._macro_runs_lock = threading.RLock()
        self._macro_runs_by_id = {}
        self._macro_run_ids_by_macro = {}
        self._macro_run_requests: "queue.Queue[dict]" = queue.Queue()
        self._active_macro_run = None
        self.cached_public_ip = "-"
        self.cached_local_ip = self._get_local_ip()
        threading.Thread(target=self._fetch_public_ip, daemon=True).start()
        self.web_manager_host_var = tk.StringVar()
        self.web_manager_port_var = tk.StringVar()
        self.web_manager_status_var = tk.StringVar(value="Web manager stopped.")
        self.macro_store: MacroStore = self.core.macro_store
        self.web_manager = WebManagerServer(
            status_provider=self._web_manager_status_payload,
            command_handler=self._web_manager_command_handler,
            macros_provider=self._macro_list_payload,
            macro_creator=self._macro_creator_handler,
        )
        self.web_backup_in_progress = False
        self.web_backup_error = None
        self._log_tailer_stop = threading.Event()
        self._log_tailer_thread = None
        self._log_tailer_path = None

        self._resource_history = deque(maxlen=1440)
        self._resource_history_stop = threading.Event()
        threading.Thread(target=self._resource_history_loop, daemon=True).start()

        self._build_menu()
        self._build_tabs()
        self._load_preferences_into_ui()
        self._refresh_properties()
        self._refresh_backups()
        self._refresh_players()
        self._poll_server_output()
        self.after(150, self._maybe_autostart_web_manager)
        self.after(250, self._maybe_autostart_server)

    def _build_menu(self):
        menu = tk.Menu(self)

        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Open Server Folder", command=self._open_server_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(label="Reload", command=self._reload_all)
        menu.add_cascade(label="Tools", menu=tools_menu)

        server_menu = tk.Menu(menu, tearoff=False)
        server_menu.add_command(label="Validate", command=self._validate_server_menu)
        menu.add_cascade(label="Server", menu=server_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=self._show_about)
        menu.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menu)

    def _build_tabs(self):
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_prefs = ttk.Frame(self.tabs)
        self.tab_details = ttk.Frame(self.tabs)
        self.tab_backups = ttk.Frame(self.tabs)
        self.tab_manage = ttk.Frame(self.tabs)
        self.tab_web_manager = ttk.Frame(self.tabs)

        self.tabs.add(self.tab_prefs, text="Preferences")
        self.tabs.add(self.tab_details, text="Server Properties")
        self.tabs.add(self.tab_backups, text="Backups")
        self.tabs.add(self.tab_manage, text="Server Management")
        self.tabs.add(self.tab_web_manager, text="Web Manager")

        self._build_prefs_tab()
        self._build_details_tab()
        self._build_backups_tab()
        self._build_manage_tab()
        self._build_web_manager_tab()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_prefs_tab(self):
        pad = {"padx": 10, "pady": 6}

        self.download_frame = ttk.Frame(self.tab_prefs)
        self.download_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(8, 2))
        self.btn_download_server = ttk.Button(
            self.download_frame,
            text="Download Server",
            command=self._open_server_download,
        )
        self.btn_download_server.pack()

        ttk.Label(self.tab_prefs, text="Server residing folder:").grid(row=1, column=0, sticky="w", **pad)
        self.server_dir_var = tk.StringVar()
        ttk.Entry(self.tab_prefs, textvariable=self.server_dir_var).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(self.tab_prefs, text="Choose", command=self._choose_server_dir).grid(row=1, column=2, **pad)

        ttk.Label(self.tab_prefs, text="Server backup location:").grid(row=2, column=0, sticky="w", **pad)
        self.backups_dir_var = tk.StringVar()
        ttk.Entry(self.tab_prefs, textvariable=self.backups_dir_var).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(self.tab_prefs, text="Choose", command=self._choose_backups_dir).grid(row=2, column=2, **pad)

        ttk.Label(self.tab_prefs, text="Server backend:").grid(row=3, column=0, sticky="w", **pad)
        self.server_backend_var = tk.StringVar()
        server_backend = ttk.Combobox(
            self.tab_prefs,
            textvariable=self.server_backend_var,
            values=("auto", "endstone", "bedrock"),
            state="readonly",
            width=12,
        )
        server_backend.grid(row=3, column=1, sticky="w", **pad)
        server_backend.bind("<<ComboboxSelected>>", lambda _e: (self._save_preferences_from_ui(), self._validate_settings()))

        self.autostart_server_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.tab_prefs,
            text="Autostart server on start",
            variable=self.autostart_server_var,
            command=self._save_preferences_from_ui,
        ).grid(row=4, column=0, columnspan=3, sticky="w", **pad)

        self.autostart_web_manager_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.tab_prefs,
            text="Autostart web manager on start",
            variable=self.autostart_web_manager_var,
            command=self._save_preferences_from_ui,
        ).grid(row=5, column=0, columnspan=3, sticky="w", **pad)

        self.prefs_status = ttk.Label(self.tab_prefs, text="")
        self.prefs_status.grid(row=6, column=0, columnspan=3, sticky="w", **pad)

        self.tab_prefs.columnconfigure(1, weight=1)

    def _build_details_tab(self):
        self.props_tree = ttk.Treeview(self.tab_details, columns=("key", "value"), show="headings")
        self.props_tree.heading("key", text="Key")
        self.props_tree.heading("value", text="Value")
        self.props_tree.column("key", width=250, anchor="w")
        self.props_tree.column("value", width=450, anchor="w")
        self.props_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.props_tree.bind("<Double-1>", self._edit_property)

        self.details_status = ttk.Label(self.tab_details, text="")
        self.details_status.pack(fill="x", padx=8, pady=(0, 8))

        self.details_empty = ttk.Label(self.tab_details, text="Choose a valid server location.")
        self.details_empty.place(relx=0.5, rely=0.5, anchor="center")

    def _build_backups_tab(self):
        self.backups_tree = ttk.Treeview(
            self.tab_backups,
            columns=("name", "size", "modified"),
            show="headings",
        )
        self.backups_tree.heading("name", text="Name", command=lambda col="name": self._sort_backups(col))
        self.backups_tree.heading("size", text="Size", command=lambda col="size": self._sort_backups(col))
        self.backups_tree.heading(
            "modified", text="Modified", command=lambda col="modified": self._sort_backups(col)
        )
        self.backups_tree.column("name", width=320, anchor="w")
        self.backups_tree.column("size", width=120, anchor="e")
        self.backups_tree.column("modified", width=200, anchor="w")
        self.backups_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.backups_tree.bind("<<TreeviewSelect>>", self._on_backup_select)

        self.backups_metadata = {}
        self.backups_sort_column = None
        self.backups_sort_reverse = False

        self.style.configure("BackupsEmpty.TLabel", background="white")
        self.backups_empty = ttk.Label(
            self.tab_backups,
            text="No backups. Click New Backup to backup current world.",
            style="BackupsEmpty.TLabel",
        )
        self.backups_empty.place(relx=0.5, rely=0.5, anchor="center")

        actions = ttk.Frame(self.tab_backups)
        actions.pack(fill="x", padx=8, pady=(0, 8))

        self.btn_backup_new = ttk.Button(actions, text="New Backup", command=self._create_backup, state="disabled")
        self.btn_backup_restore = ttk.Button(actions, text="Restore", command=self._restore_backup, state="disabled")
        self.btn_backup_rename = ttk.Button(actions, text="Rename", command=self._rename_backup, state="disabled")
        self.btn_backup_delete = ttk.Button(actions, text="Delete", command=self._delete_backup, state="disabled")
        self.btn_backup_open = ttk.Button(actions, text="Open Backups Folder", command=self._open_backups_folder)

        self.btn_backup_new.pack(side="left", padx=4)
        self.btn_backup_restore.pack(side="left", padx=4)
        self.btn_backup_rename.pack(side="left", padx=4)
        self.btn_backup_delete.pack(side="left", padx=4)
        self.btn_backup_open.pack(side="right", padx=4)

        self.backups_status = ttk.Label(self.tab_backups, text="")
        self.backups_status.pack(fill="x", padx=8, pady=(0, 8))

    def _build_manage_tab(self):
        controls = ttk.Frame(self.tab_manage)
        controls.pack(fill="x", padx=8, pady=8)

        self.btn_server_start = ttk.Button(controls, text="Start Server", command=self._start_server)
        self.btn_server_stop = ttk.Button(controls, text="Stop Server", command=self._stop_server, state="disabled")
        self.btn_server_refresh = ttk.Button(controls, text="Refresh Players", command=self._refresh_players, state="disabled")

        self.btn_server_start.pack(side="left", padx=4)
        self.btn_server_stop.pack(side="left", padx=4)
        self.btn_server_refresh.pack(side="left", padx=4)

        status_frame = ttk.LabelFrame(self.tab_manage, text="Server Status")
        status_frame.pack(fill="x", padx=8, pady=(0, 8))

        self.status_running_var = tk.StringVar(value="Stopped")
        self.status_port_var = tk.StringVar(value="-")
        self.status_gamemode_var = tk.StringVar(value="-")
        self.status_max_players_var = tk.StringVar(value="-")
        self.status_connected_var = tk.StringVar(value="0")
        self.status_uptime_var = tk.StringVar(value="Uptime: -")
        self.status_local_url_var = tk.StringVar(value="Local URL: -")

        ttk.Label(status_frame, text="State:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, textvariable=self.status_running_var).grid(row=0, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, text="Port:").grid(row=0, column=2, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, textvariable=self.status_port_var).grid(row=0, column=3, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, text="Gamemode:").grid(row=0, column=4, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, textvariable=self.status_gamemode_var).grid(row=0, column=5, sticky="w", padx=8, pady=4)

        ttk.Label(status_frame, text="Max Players:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, textvariable=self.status_max_players_var).grid(row=1, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, text="Connected:").grid(row=1, column=2, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, textvariable=self.status_connected_var).grid(row=1, column=3, sticky="w", padx=8, pady=4)
        
        ttk.Label(status_frame, textvariable=self.status_uptime_var).grid(row=1, column=4, sticky="w", padx=8, pady=4)
        ttk.Label(status_frame, textvariable=self.status_local_url_var).grid(row=1, column=5, sticky="w", padx=8, pady=4)
        status_frame.columnconfigure(5, weight=1)

        console_frame = ttk.Frame(self.tab_manage)
        console_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.console_text = tk.Text(console_frame, height=12, wrap="word")
        self.console_text.pack(side="left", fill="both", expand=True)
        console_scroll = ttk.Scrollbar(console_frame, orient="vertical", command=self.console_text.yview)
        console_scroll.pack(side="right", fill="y")
        self.console_text.config(yscrollcommand=console_scroll.set, state="disabled")
        self.console_text.bind("<Key>", self._redirect_console_input)

        input_frame = ttk.Frame(self.tab_manage)
        input_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(input_frame, text="Command:").pack(side="left")
        self.console_input = ttk.Entry(input_frame)
        self.console_input.pack(side="left", fill="x", expand=True, padx=6)
        self.console_input.bind("<Return>", self._send_console_input)
        self._set_console_enabled(False)

        players_frame = ttk.Frame(self.tab_manage)
        players_frame.pack(fill="both", expand=False, padx=8, pady=(0, 8))

        players_tabs = ttk.Notebook(players_frame)
        players_tabs.pack(fill="both", expand=True)

        self.tab_whitelist = ttk.Frame(players_tabs)
        self.tab_ops = ttk.Frame(players_tabs)
        self.tab_players = ttk.Frame(players_tabs)

        players_tabs.add(self.tab_whitelist, text="Whitelist")
        players_tabs.add(self.tab_ops, text="Ops")
        players_tabs.add(self.tab_players, text="Players")

        self._build_whitelist_tab()
        self._build_ops_tab()
        self._build_players_tab()

    def _build_web_manager_tab(self):
        pad = {"padx": 8, "pady": 6}
        container = ttk.Frame(self.tab_web_manager)
        container.pack(fill="both", expand=True, padx=8, pady=8)

        settings_frame = ttk.LabelFrame(container, text="Web manager settings")
        settings_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(settings_frame, text="Host:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(settings_frame, textvariable=self.web_manager_host_var).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(settings_frame, text="Port:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(settings_frame, textvariable=self.web_manager_port_var).grid(row=1, column=1, sticky="ew", **pad)
        settings_frame.columnconfigure(1, weight=1)

        control_frame = ttk.Frame(container)
        control_frame.pack(fill="x", pady=(0, 12))
        self.btn_web_manager_start = ttk.Button(control_frame, text="Start Web Manager", command=self._start_web_manager)
        self.btn_web_manager_stop = ttk.Button(
            control_frame, text="Stop Web Manager", command=self._stop_web_manager, state="disabled"
        )
        self.btn_web_manager_open = ttk.Button(
            control_frame, text="Open Web UI", command=self._open_web_manager, state="disabled"
        )
        self.btn_web_manager_start.pack(side="left", padx=4)
        self.btn_web_manager_stop.pack(side="left", padx=4)
        self.btn_web_manager_open.pack(side="right", padx=4)

        self.web_manager_status_label = ttk.Label(container, textvariable=self.web_manager_status_var)
        self.web_manager_status_label.pack(fill="x", pady=(0, 4))

    def _start_web_manager(self):
        if self.web_manager.is_running():
            messagebox.showinfo(APP_NAME, "Web manager is already running.")
            return
        host = self.web_manager_host_var.get().strip() or "0.0.0.0"
        port_text = self.web_manager_port_var.get().strip()
        try:
            port = int(port_text) if port_text else 5050
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_NAME, "Enter a valid port between 1 and 65535.")
            return
        try:
            self.web_manager.start(host, port)
        except RuntimeError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to start web manager: {exc}")
            return
        self.settings["web_manager_host"] = host
        self.settings["web_manager_port"] = port
        save_settings(self.settings)
        self._update_web_manager_status()

    def _stop_web_manager(self):
        self.web_manager.stop()
        self._update_web_manager_status()

    def _open_web_manager(self):
        if not self.web_manager.is_running():
            messagebox.showwarning(APP_NAME, "Web manager is not running.")
            return
        webbrowser.open(self.web_manager.url())

    def _update_web_manager_status(self):
        running = self.web_manager.is_running()
        host = self.web_manager.host if running else (self.web_manager_host_var.get().strip() or "127.0.0.1")
        port = self.web_manager.port if running else self.settings.get("web_manager_port", 5050)
        status = "Running" if running else "Stopped"
        self.web_manager_status_var.set(f"{status} - {host}:{port}")
        self.btn_web_manager_start.config(state="disabled" if running else "normal")
        self.btn_web_manager_stop.config(state="normal" if running else "disabled")
        self.btn_web_manager_open.config(state="normal" if running else "disabled")

    def _web_manager_command_handler(self, action: str, data: dict = None):
        actions = {
            "start_server": self._start_server,
            "stop_server": self._stop_server,
            "refresh_players": self._refresh_players,
        }
        if action == "set_server_backend" and data:
            backend = (data.get("backend") or "").strip().lower()
            if backend not in {"auto", "endstone", "bedrock"}:
                return {"error": "Invalid backend. Use auto/endstone/bedrock."}
            self.after(0, lambda: self._set_server_backend(backend))
            return {"scheduled": True}
        if action == "set_autostart_server" and data is not None:
            enabled = bool(data.get("enabled", False))
            self.after(0, lambda: self._set_autostart_server(enabled))
            return {"scheduled": True}
        if action == "run_macro" and data:
            commands = data.get("commands") or []
            macro_id = data.get("macro_id")
            player_name = data.get("player_name", "")
            message = data.get("message", "")
            commands = [str(c).strip() for c in commands if str(c).strip()]
            if commands:
                macro_title = str(data.get("macro_title") or "").strip()
                run_id = self._queue_macro_run(commands, macro_id=macro_id, macro_title=macro_title, player_name=player_name, message=message)
                return {"success": True, "run_id": run_id}
            return {"error": "No commands provided"}
        if action == "get_macro_run" and data:
            run_id = str(data.get("run_id") or "").strip()
            if not run_id:
                return {"error": "run_id is required"}
            with self._macro_runs_lock:
                run = self._macro_runs_by_id.get(run_id)
            if not run:
                return {"error": "Run not found"}
            return {"run": run}
        if action == "get_latest_macro_run" and data:
            macro_id = str(data.get("macro_id") or "").strip()
            if not macro_id:
                return {"error": "macro_id is required"}
            with self._macro_runs_lock:
                ids = self._macro_run_ids_by_macro.get(macro_id) or []
                latest_id = ids[-1] if ids else ""
                run = self._macro_runs_by_id.get(latest_id) if latest_id else None
            if not run:
                return {"error": "No runs yet"}
            return {"run": run}
        if action == "import_macros" and data:
            macros = data.get("macros")
            self.after(0, lambda: self._import_macros(macros))
            return {"scheduled": True}
        if action == "send_command" and data:
            cmd = data.get("command")
            if cmd:
                initial_len = len(self.web_logs)
                self.after(0, lambda: self._web_send_command(cmd))
                
                # Strict wait: wait for echo (> cmd) AND server response
                start_wait = time.time()
                while time.time() - start_wait < 10: # 10s timeout
                    if len(self.web_logs) > initial_len + 1:
                        return {"success": True, "status": "processed"}
                    time.sleep(0.1)
                return {"success": True, "status": "timeout"}
        if action == "update_property" and data:
            key = data.get("key")
            value = data.get("value")
            if key and value is not None:
                self.after(0, lambda: self._web_update_property(key, value))
                return {"scheduled": True}
        if action == "delete_backup" and data:
            name = data.get("name")
            if name:
                self.after(0, lambda: self._web_delete_backup(name))
                return {"scheduled": True}
        if action == "restore_backup" and data:
            name = data.get("name")
            if name:
                self.after(0, lambda: self._web_restore_backup(name))
                return {"scheduled": True}
        if action == "new_backup" and data:
            name = data.get("name")
            if name:
                self.after(0, lambda: self._web_create_backup(name))
                return {"scheduled": True}

        target = actions.get(action)
        if not target:
            return {"error": f"Unknown action {action}"}
        
        self.after(0, target)

        # Wait for confirmation if starting or stopping
        if action == "start_server":
            start_wait = time.time()
            while time.time() - start_wait < 15: # 15s timeout
                # Check if process is running and has produced some logs
                if self.server_process and self.server_process.poll() is None:
                    if len(self.web_logs) > 2: # "Server started" + actual output
                        return {"success": True, "status": "running"}
                time.sleep(0.5)
            return {"success": True, "status": "starting"}
            
        if action == "stop_server":
            start_wait = time.time()
            while time.time() - start_wait < 15: # 15s timeout
                # Check if process is fully stopped
                if not self.server_process or self.server_process.poll() is not None:
                    return {"success": True, "status": "stopped"}
                time.sleep(0.5)
            return {"success": True, "status": "stopping"}

        return {"scheduled": True}

    def _set_server_backend(self, backend: str):
        self.settings["server_backend"] = backend
        if hasattr(self, "server_backend_var"):
            try:
                self.server_backend_var.set(backend)
            except Exception:
                pass
        save_settings(self.settings)

    def _set_autostart_server(self, enabled: bool):
        self.settings["autostart_server"] = bool(enabled)
        if hasattr(self, "autostart_server_var"):
            try:
                self.autostart_server_var.set(bool(enabled))
            except Exception:
                pass
        save_settings(self.settings)

    def _import_macros(self, macros):
        try:
            count = self.macro_store.replace_all(macros if macros is not None else [])
        except Exception as exc:
            self.web_logs.append(f"[Macros] Import failed: {exc}\n")
            return
        self.web_logs.append(f"[Macros] Imported {count} macro(s).\n")

    def _web_send_command(self, cmd):
        try:
            self.core.send_command(cmd)
            self._append_console(f"> {cmd}\n")
        except Exception:
            pass

    def _run_macro_commands(self, commands, macro_id=None, player_name: str = "", message: str = ""):
        if macro_id:
            self.macro_store.increment_times_ran(macro_id)
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
            self.after(0, lambda c=rendered: self._web_send_command(c))

    def _queue_macro_run(self, commands, macro_id=None, macro_title: str = "", player_name: str = "", message: str = "") -> str:
        run_id = str(uuid4())
        msg = str(message or "")
        msg_text = msg
        msg_keyword = ""
        if msg:
            msg_keyword = msg.split()[0]
            msg_text = msg[len(msg_keyword):].lstrip() if msg.lower().startswith(msg_keyword.lower()) else msg
        request = {
            "run_id": run_id,
            "macro_id": str(macro_id or "").strip() or None,
            "macro_title": str(macro_title or "").strip(),
            "commands": [
                str(c)
                .strip()
                .replace("{player}", player_name)
                .replace("{message}", msg)
                .replace("{message_keyword}", msg_keyword)
                .replace("{message_text}", msg_text)
                for c in (commands or [])
                if str(c).strip()
            ],
            "requested_at": time.time(),
        }
        self._macro_run_requests.put(request)
        with self._macro_runs_lock:
            self._macro_runs_by_id[run_id] = {
                "id": run_id,
                "macro_id": request["macro_id"],
                "macro_title": request["macro_title"],
                "requested_at": request["requested_at"],
                "started_at": None,
                "finished_at": None,
                "success": None,
                "steps": [],
            }
            if request["macro_id"]:
                ids = self._macro_run_ids_by_macro.setdefault(request["macro_id"], [])
                ids.append(run_id)
                if len(ids) > 50:
                    del ids[:-50]
        return run_id

    def _macro_list_payload(self):
        return {"macros": self.macro_store.list(), "presets": PRESET_MACROS}

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
            if interval_seconds < 0:
                interval_seconds = 0
        except (TypeError, ValueError):
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
        macro = self.macro_store.add_macro(
            title=title,
            icon=icon or "bi-gear-fill",
            commands=commands,
            interval_seconds=interval_seconds,
            time_of_day=time_of_day,
            trigger=trigger,
            chat_keyword=chat_keyword,
        )
        return macro

    def _web_update_property(self, key, value):
        try:
            self._set_property_value(key, value)
            self._refresh_properties()
        except Exception:
            pass

    def _set_property_value(self, key, value):
        cleaned_key = (str(key or "")).strip()
        if not cleaned_key:
            raise ValueError("Property key is required.")
        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            raise ValueError("Server folder is not configured.")
        if not os.path.isdir(server_dir):
            raise FileNotFoundError("Server folder not found.")
        prop_path = os.path.join(server_dir, "server.properties")
        if not self.properties or self.properties.path != prop_path:
            self.properties = PropertiesFile(prop_path)
            self.properties.load()
        self.properties.set_value(cleaned_key, "" if value is None else str(value))
        self.properties.save()

    def _web_delete_backup(self, name):
        backups_dir = self.backups_dir_var.get().strip()
        if not backups_dir: return
        path = os.path.join(backups_dir, name)
        try:
            if os.path.exists(path):
                if os.path.isdir(path): shutil.rmtree(path)
                else: os.remove(path)
                self._refresh_backups()
        except Exception:
            pass

    def _web_restore_backup(self, name):
        backups_dir = self.backups_dir_var.get().strip()
        if not backups_dir: return
        path = os.path.join(backups_dir, name)
        if not os.path.exists(path): return
        self._restore_backup_logic(path)

    def _web_create_backup(self, name):
        if self.web_backup_in_progress:
            self.web_backup_error = "A backup is already in progress."
            return
        backups_dir = self.backups_dir_var.get().strip()
        if not backups_dir:
            self.web_backup_error = "Backups folder is not set."
            return
        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            self.web_backup_error = "Server folder is not set."
            return
        if not os.path.isdir(server_dir):
            self.web_backup_error = "Server folder does not exist."
            return
        os.makedirs(backups_dir, exist_ok=True)
        source = os.path.join(server_dir, "worlds")
        if not os.path.isdir(source):
            source = server_dir
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        world_name = self._world_name(server_dir)
        safe_name = (name or "").strip()
        if not safe_name:
            safe_name = f"mcbak-{timestamp}_{world_name}"
        base_name = os.path.join(backups_dir, safe_name)
        self.web_backup_in_progress = True

        def worker():
            error = None
            try:
                shutil.make_archive(base_name, "zip", source)
            except Exception as exc:
                error = exc
            finally:
                self.after(0, lambda: self._web_backup_finished(error))

        threading.Thread(target=worker, daemon=True).start()

    def _web_backup_finished(self, error):
        self.web_backup_in_progress = False
        if error:
            self.web_backup_error = f"Backup failed: {error}"
        self._refresh_backups()

    def _restore_backup_logic(self, path):
        # Simplified restore logic for web call
        server_dir = self.server_dir_var.get().strip()
        if not server_dir: return
        worlds_root = os.path.join(server_dir, "worlds")
        world_name = self._world_name(server_dir)
        previous_world = os.path.join(worlds_root, world_name)
        old_world = os.path.join(worlds_root, f"Old_{world_name}")
        try:
            if os.path.isdir(old_world): shutil.rmtree(old_world)
            if os.path.isdir(previous_world):
                os.makedirs(worlds_root, exist_ok=True)
                shutil.move(previous_world, old_world)
            if path.endswith(".zip"):
                shutil.unpack_archive(path, os.path.join(server_dir, "worlds"))
            elif os.path.isdir(path):
                dest = os.path.join(server_dir, "worlds")
                basename = os.path.basename(path.rstrip(os.sep))
                target = os.path.join(dest, basename)
                if os.path.isdir(target):
                    shutil.rmtree(target)
                os.makedirs(dest, exist_ok=True)
                shutil.copytree(path, target)
            self.after(0, self._refresh_backups)
        except Exception:
            pass

    def _web_manager_status_payload(self):
        running = bool(self.server_process and self.server_process.poll() is None)
        if running and not self.server_start_time:
            self.server_start_time = time.time()
            self.server_start_monotonic = time.monotonic()
        uptime_seconds = self._get_uptime_seconds() if running else 0
        props = self.properties.data if self.properties and self.properties.data else {}
        
        backups = []
        backups_dir = self.backups_dir_var.get().strip()
        if backups_dir and os.path.isdir(backups_dir):
            for name in sorted(os.listdir(backups_dir)):
                path = os.path.join(backups_dir, name)
                try:
                    mtime = os.path.getmtime(path)
                    size = self._path_size(path)
                    backups.append({
                        "name": name,
                        "size": self._format_size(size),
                        "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                        "timestamp": mtime
                    })
                except OSError: pass

        server_dir = self.server_dir_var.get().strip()
        ops_names = []
        if server_dir and os.path.isdir(server_dir):
            xuid_name_map = self._build_xuid_name_map(server_dir)
            permissions = self._load_json_list(self._server_path("permissions.json"))
            for entry in permissions:
                raw_name = entry.get("name", "")
                xuid = (entry.get("xuid") or "").strip()
                name = (raw_name or "").strip()
                if (not name or name.lower() == "unknown") and xuid:
                    name = xuid_name_map.get(xuid, name)
                if name:
                    ops_names.append(name)

        metrics = self._server_process_metrics() if running else {}
        bedrock = {
            "running": running,
            "port": props.get("server-port", "-"),
            "gamemode": props.get("gamemode", "-"),
            "connected": len(self.live_players),
            "max_players": props.get("max-players", "-"),
            "backend": self.server_backend if running else "-",
            "backend_preference": (self.settings.get("server_backend", "auto") or "auto").lower(),
            "autostart_server": bool(self.settings.get("autostart_server", False)),
            "cpu_percent": metrics.get("cpu_percent"),
            "mem_percent": metrics.get("mem_percent"),
            "mem_rss_bytes": metrics.get("mem_rss_bytes"),
        }
        web_running = self.web_manager.is_running()
        web_host = self.web_manager.host if web_running else (self.web_manager_host_var.get().strip() or "127.0.0.1")
        web_port = self.web_manager.port if web_running else self.settings.get("web_manager_port", 5050)
        manager_url = f"http://{web_host}:{web_port}"
        backup_error = self.web_backup_error
        self.web_backup_error = None
        return {
            "bedrock": bedrock,
            "web_manager": {
                "running": web_running,
                "host": web_host,
                "port": web_port,
                "url": manager_url,
            },
            "players": self._resolve_live_players_for_web(server_dir),
            "operators": sorted(set(ops_names)),
            "properties": props,
            "backups": backups,
            "logs": list(self.web_logs),
            "network": {
                "local_ip": self.cached_local_ip,
                "public_ip": self.cached_public_ip,
                "port": props.get("server-port", "19132")
            },
            "server_start_time": self.server_start_time if running else None,
            "server_uptime_seconds": uptime_seconds,
            "resource_history": list(self._resource_history),
            "backup_in_progress": self.web_backup_in_progress,
            "backup_error": backup_error,
        }

    def _maybe_autostart_server(self):
        if self.server_process and self.server_process.poll() is None:
            return
        if not bool(self.settings.get("autostart_server", False)):
            return
        server_dir = self.server_dir_var.get().strip()
        if not server_dir or not os.path.isdir(server_dir):
            return
        self._start_server()

    def _maybe_autostart_web_manager(self):
        if self.web_manager.is_running():
            return
        if not bool(self.settings.get("autostart_web_manager", False)):
            return
        try:
            self._start_web_manager()
        except Exception:
            # _start_web_manager already shows a dialog for validation errors; ignore unexpected failures.
            pass

    def _update_uptime(self):
        if self.server_process and self.server_process.poll() is None:
            if not self.server_start_time:
                self.server_start_time = time.time()
            if not self.server_start_monotonic:
                self.server_start_monotonic = time.monotonic()
            delta = self._get_uptime_seconds()
            self.status_uptime_var.set(f"Uptime: {self._format_duration(delta)}")
            self.after(1000, self._update_uptime)
        else:
            self.server_start_time = None
            self.server_start_monotonic = None
            self.status_uptime_var.set("Uptime: -")

    def _resource_history_loop(self):
        while not self._resource_history_stop.is_set():
            if self.server_process and self.server_process.poll() is None:
                metrics = self._server_process_metrics()
                if metrics:
                    self._resource_history.append({
                        "timestamp": time.time(),
                        "cpu": metrics.get("cpu_percent") or 0,
                        "mem": metrics.get("mem_percent") or 0
                    })
            self._resource_history_stop.wait(60)

    def _server_process_metrics(self) -> dict:
        proc = self.server_process
        if not proc or proc.poll() is not None or not proc.pid:
            self._perf_prev = None
            return {}
        if os.name != "posix":
            return {}

        pid = proc.pid
        now = time.monotonic()
        try:
            ticks_per_sec = os.sysconf("SC_CLK_TCK")
        except Exception:
            ticks_per_sec = 100

        proc_ticks = None
        try:
            with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as fp:
                stat_line = fp.read().strip()
            # /proc/<pid>/stat includes the process name in parentheses and it may contain spaces.
            # Parse by locating the closing paren and splitting the remainder.
            close_idx = stat_line.rfind(")")
            if close_idx != -1:
                rest = stat_line[close_idx + 2 :].split()  # fields 3..N
                # rest[11] = utime (field 14), rest[12] = stime (field 15)
                if len(rest) >= 13:
                    utime = int(rest[11])
                    stime = int(rest[12])
                    proc_ticks = utime + stime
        except Exception:
            proc_ticks = None

        cpu_percent = None
        if proc_ticks is not None:
            prev = self._perf_prev
            if prev:
                prev_ticks, prev_time = prev
                dt = max(0.0001, now - prev_time)
                d_ticks = max(0, proc_ticks - prev_ticks)
                cpu_seconds = d_ticks / float(ticks_per_sec)
                cpu_percent = (cpu_seconds / dt) * 100.0
            self._perf_prev = (proc_ticks, now)

        mem_rss_bytes = None
        try:
            with open(f"/proc/{pid}/status", "r", encoding="utf-8") as fp:
                for line in fp:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            mem_rss_bytes = int(parts[1]) * 1024
                        break
        except Exception:
            mem_rss_bytes = None

        mem_percent = None
        if mem_rss_bytes is not None:
            mem_total_kb = None
            try:
                with open("/proc/meminfo", "r", encoding="utf-8") as fp:
                    for line in fp:
                        if line.startswith("MemTotal:"):
                            parts = line.split()
                            if len(parts) >= 2:
                                mem_total_kb = int(parts[1])
                            break
            except Exception:
                mem_total_kb = None
            if mem_total_kb and mem_total_kb > 0:
                mem_percent = (mem_rss_bytes / (mem_total_kb * 1024.0)) * 100.0

        return {
            "cpu_percent": cpu_percent,
            "mem_rss_bytes": mem_rss_bytes,
            "mem_percent": mem_percent,
        }

    def _get_uptime_seconds(self):
        if not self.server_process or self.server_process.poll() is not None:
            return 0
        if self.server_start_monotonic:
            return max(0, int(time.monotonic() - self.server_start_monotonic))
        if self.server_start_time:
            return max(0, int(time.time() - self.server_start_time))
        return 0

    def _format_duration(self, seconds):
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connect to an external IP address (Google's public DNS server)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except socket.error:
            local_ip = "127.0.0.1" # Fallback to loopback if no connection
        finally:
            s.close()
        return local_ip

    def _fetch_public_ip(self):
        services = ["https://api.ipify.org", "https://ident.me", "https://icanhazip.com"]
        for service in services:
            try:
                with urllib.request.urlopen(service, timeout=5) as response:
                    ip = response.read().decode("utf-8").strip()
                    if ip:
                        self.cached_public_ip = ip
                        self.after(0, self._update_server_status)
                        return
            except Exception:
                continue
        self.cached_public_ip = "-"
        self.after(0, self._update_server_status)

    def _load_preferences_into_ui(self):
        self.server_dir_var.set(self.settings.get("server_dir", ""))
        self.backups_dir_var.set(self.settings.get("backups_dir", ""))
        self.server_backend_var.set(self.settings.get("server_backend", "auto"))
        if hasattr(self, "autostart_server_var"):
            try:
                self.autostart_server_var.set(bool(self.settings.get("autostart_server", False)))
            except Exception:
                pass
        if hasattr(self, "autostart_web_manager_var"):
            try:
                self.autostart_web_manager_var.set(bool(self.settings.get("autostart_web_manager", False)))
            except Exception:
                pass
        self.web_manager_host_var.set(self.settings.get("web_manager_host", "127.0.0.1"))
        self.web_manager_port_var.set(str(self.settings.get("web_manager_port", 5050)))
        self._validate_settings()
        self._update_web_manager_status()

    def _save_preferences_from_ui(self):
        self.settings["server_dir"] = self.server_dir_var.get().strip()
        self.settings["backups_dir"] = self.backups_dir_var.get().strip()
        self.settings["server_backend"] = (self.server_backend_var.get().strip() or "auto").lower()
        if hasattr(self, "autostart_server_var"):
            try:
                self.settings["autostart_server"] = bool(self.autostart_server_var.get())
            except Exception:
                self.settings["autostart_server"] = bool(self.settings.get("autostart_server", False))
        if hasattr(self, "autostart_web_manager_var"):
            try:
                self.settings["autostart_web_manager"] = bool(self.autostart_web_manager_var.get())
            except Exception:
                self.settings["autostart_web_manager"] = bool(self.settings.get("autostart_web_manager", False))
        host = self.web_manager_host_var.get().strip() or "127.0.0.1"
        port_value = self.settings.get("web_manager_port", 5050)
        try:
            port_value = int(self.web_manager_port_var.get().strip())
        except ValueError:
            pass
        self.settings["web_manager_host"] = host
        self.settings["web_manager_port"] = port_value
        save_settings(self.settings)

    def _choose_server_dir(self):
        path = filedialog.askdirectory(title="Choose server folder")
        if path:
            self.server_dir_var.set(path)
            self._save_preferences_from_ui()
            self._validate_settings()
            self._refresh_properties()
            self._refresh_players()

    def _choose_backups_dir(self):
        path = filedialog.askdirectory(title="Choose backups folder")
        if path:
            self.backups_dir_var.set(path)
            self._save_preferences_from_ui()
            self._validate_settings()
            self._refresh_backups()

    def _open_server_download(self):
        webbrowser.open("https://www.minecraft.net/en-us/download/server/bedrock")

    def _open_server_folder(self):
        path = self.server_dir_var.get().strip()
        if not path:
            messagebox.showinfo(APP_NAME, "Server folder is not set.")
            return
        try:
            if os.name == "nt":
                os.startfile(path)
            elif os.name == "posix":
                os.system(f'xdg-open "{path}"')
        except Exception:
            messagebox.showerror(APP_NAME, "Unable to open server folder.")

    def _show_about(self):
        messagebox.showinfo(APP_NAME, f"{APP_NAME}\nBy {APP_AUTHOR}\nLicense {APP_LICENSE}")

    def _reload_all(self):
        self.settings = load_settings()
        self._load_preferences_into_ui()
        self._refresh_properties()
        self._refresh_backups()
        self._refresh_players()

    def _validate_settings(self):
        server_dir = self.server_dir_var.get().strip()
        backups_dir = self.backups_dir_var.get().strip()
        backend_pref = (self.server_backend_var.get().strip() or self.settings.get("server_backend", "auto")).lower()
        server_status = "Missing"
        if server_dir:
            missing = server_dir_missing_files(server_dir, preferred_backend=backend_pref)
            if missing and missing != ["server folder"]:
                server_status = "Missing: " + ", ".join(missing)
            elif missing == ["server folder"]:
                server_status = "Not found"
            else:
                server_status = "OK"
        backups_status = "Missing"
        if backups_dir:
            backups_status = "OK" if os.path.isdir(backups_dir) else "Not found"
        self.prefs_status.config(
            text=f"Server folder: {server_status} | Backups folder: {backups_status}"
        )
        if server_status == "OK":
            self.download_frame.grid_remove()
        else:
            self.download_frame.grid()

    def _refresh_properties(self):
        for item in self.props_tree.get_children():
            self.props_tree.delete(item)

        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            self.details_status.config(text="Set the server folder to load server.properties.")
            self.details_empty.lift()
            self.details_empty.place(relx=0.5, rely=0.5, anchor="center")
            return
        self.details_empty.place_forget()
        prop_path = os.path.join(server_dir, "server.properties")
        self.properties = PropertiesFile(prop_path)
        try:
            self.properties.load()
        except Exception as exc:
            self.details_status.config(text=f"Failed to read server.properties: {exc}")
            return
        if not self.properties.data:
            self.details_status.config(text=f"No properties found at {prop_path}")
            return
        for key in sorted(self.properties.data.keys()):
            self.props_tree.insert("", "end", values=(key, self.properties.data[key]))
        self.details_status.config(text=f"Loaded {len(self.properties.data)} properties.")
        self._update_server_status()

    def _edit_property(self, _event):
        selection = self.props_tree.selection()
        if not selection:
            return
        item = selection[0]
        key, value = self.props_tree.item(item, "values")
        new_value = prompt_string(self, f"Edit value for '{key}':", value)
        if new_value is None:
            return
        try:
            self._set_property_value(key, new_value)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to write server.properties: {exc}")
            return
        self._refresh_properties()

    def _format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        for unit in ["KB", "MB", "GB", "TB"]:
            size_bytes /= 1024.0
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
        return f"{size_bytes:.1f} PB"

    def _path_size(self, path):
        if os.path.isfile(path):
            return os.path.getsize(path)
        total = 0
        for root, _, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    continue
        return total

    def _refresh_backups(self):
        self.backups_tree.delete(*self.backups_tree.get_children())
        self.backups_metadata.clear()
        backups_dir = self.backups_dir_var.get().strip()
        if not backups_dir:
            self.backups_status.config(text="Set the backups folder to list backups.")
            self._set_backup_buttons_state(False)
            self.backups_empty.lift()
            self.backups_empty.place(relx=0.5, rely=0.5, anchor="center")
            return
        if not os.path.isdir(backups_dir):
            self.backups_status.config(text="Backups folder does not exist.")
            self._set_backup_buttons_state(False)
            self.backups_empty.lift()
            self.backups_empty.place(relx=0.5, rely=0.5, anchor="center")
            return

        files = sorted(os.listdir(backups_dir))
        for name in files:
            path = os.path.join(backups_dir, name)
            try:
                size_bytes = self._path_size(path)
                size = self._format_size(size_bytes)
                modified_ts = os.path.getmtime(path)
                modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(modified_ts))
            except OSError:
                size_bytes = 0
                modified_ts = 0
                size = "-"
                modified = "-"
            item = self.backups_tree.insert("", "end", values=(name, size, modified))
            self.backups_metadata[item] = {
                "name": name,
                "size": size_bytes,
                "modified_ts": modified_ts,
            }
        self.backups_status.config(text=f"{len(files)} backup(s) found.")
        self._set_backup_buttons_state(False)
        if files:
            self.backups_empty.place_forget()
        else:
            self.backups_empty.lift()
            self.backups_empty.place(relx=0.5, rely=0.5, anchor="center")

    def _sort_backups(self, column):
        items = list(self.backups_tree.get_children())
        if not items:
            return
        sort_data = []
        for item in items:
            meta = self.backups_metadata.get(item, {})
            if column == "size":
                key = meta.get("size", 0)
            elif column == "modified":
                key = meta.get("modified_ts", 0)
            else:
                key = meta.get("name", self.backups_tree.set(item, "name")).lower()
            sort_data.append((key, item))
        reverse = False
        if self.backups_sort_column == column:
            reverse = not self.backups_sort_reverse
        self.backups_sort_column = column
        self.backups_sort_reverse = reverse
        sort_data.sort(key=lambda pair: pair[0], reverse=reverse)
        for index, (_, item) in enumerate(sort_data):
            self.backups_tree.move(item, "", index)

    def _on_backup_select(self, _event):
        selection = self.backups_tree.selection()
        self._set_backup_buttons_state(bool(selection))

    def _set_backup_buttons_state(self, enabled):
        state = "normal" if enabled else "disabled"
        self.btn_backup_restore.config(state=state)
        self.btn_backup_rename.config(state=state)
        self.btn_backup_delete.config(state=state)
        backups_dir = self.backups_dir_var.get().strip()
        self.btn_backup_new.config(state="normal" if backups_dir else "disabled")

    def _selected_backup_path(self):
        backups_dir = self.backups_dir_var.get().strip()
        if not backups_dir or not os.path.isdir(backups_dir):
            messagebox.showwarning(APP_NAME, "Backups folder is not available.")
            return None
        selection = self.backups_tree.selection()
        if not selection:
            return None
        name = self.backups_tree.item(selection[0], "values")[0]
        return os.path.join(backups_dir, name)

    def _ensure_backups_dir(self):
        backups_dir = self.backups_dir_var.get().strip()
        if not backups_dir:
            messagebox.showwarning(APP_NAME, "Please set the backups folder in Preferences.")
            return None
        os.makedirs(backups_dir, exist_ok=True)
        return backups_dir

    def _world_name(self, server_dir):
        worlds_dir = os.path.join(server_dir, "worlds")
        if os.path.isdir(worlds_dir):
            entries = [n for n in os.listdir(worlds_dir) if os.path.isdir(os.path.join(worlds_dir, n))]
            if entries:
                return sorted(entries)[0]
        return "world"

    def _create_backup(self, suffix=""):
        backups_dir = self._ensure_backups_dir()
        if not backups_dir:
            return
        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            messagebox.showwarning(APP_NAME, "Please set the server folder in Preferences.")
            return
        if not os.path.isdir(server_dir):
            messagebox.showwarning(APP_NAME, "Server folder does not exist.")
            return
        source = os.path.join(server_dir, "worlds")
        if not os.path.isdir(source):
            source = server_dir
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        world_name = self._world_name(server_dir)
        extra = f"_{suffix}" if suffix else ""
        default_name = f"mcbak-{timestamp}_{world_name}{extra}"
        chosen_name = prompt_string(self, "Backup name:", default_name)
        if not chosen_name:
            return
        base_name = os.path.join(backups_dir, chosen_name)
        progress_dialog = self._show_progress_dialog("Creating backup…")

        def worker():
            error = None
            try:
                shutil.make_archive(base_name, "zip", source)
            except Exception as exc:
                error = exc
            finally:
                self.after(50, lambda: self._backup_finished(progress_dialog, error))

        threading.Thread(target=worker, daemon=True).start()

    def _backup_finished(self, dialog, error):
        if not dialog.winfo_exists():
            return
        progress_bar = getattr(dialog, "progress_bar", None)
        if progress_bar:
            progress_bar.stop()
        dialog.destroy()
        if error:
            messagebox.showerror(APP_NAME, f"Backup failed: {error}")
        else:
            self._refresh_backups()

    def _show_progress_dialog(self, message):
        dialog = tk.Toplevel(self)
        dialog.title(APP_NAME)
        dialog.transient(self)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=message, anchor="w", justify="left").pack(fill="x", anchor="w")
        progress_bar = ttk.Progressbar(frame, mode="indeterminate")
        progress_bar.pack(fill="x", pady=(10, 0))
        progress_bar.start(20)
        dialog.progress_bar = progress_bar

        dialog.update_idletasks()
        width = max(320, dialog.winfo_reqwidth())
        height = dialog.winfo_reqheight() + 20
        x = self.winfo_rootx() + (self.winfo_width() // 2) - (width // 2)
        y = self.winfo_rooty() + (self.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        return dialog

    def _delete_backup(self):
        path = self._selected_backup_path()
        if not path:
            return
        if not os.path.exists(path):
            messagebox.showwarning(APP_NAME, "Selected backup no longer exists.")
            self._refresh_backups()
            return
        if not confirm_dialog(self, "Delete selected backup?"):
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            self._refresh_backups()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Delete failed: {exc}")

    def _rename_backup(self):
        path = self._selected_backup_path()
        if not path:
            return
        if not os.path.exists(path):
            messagebox.showwarning(APP_NAME, "Selected backup no longer exists.")
            self._refresh_backups()
            return
        name = os.path.basename(path)
        new_name = prompt_string(self, "New name:", name)
        if not new_name:
            return
        new_path = os.path.join(os.path.dirname(path), new_name)
        try:
            os.rename(path, new_path)
            self._refresh_backups()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Rename failed: {exc}")

    def _restore_backup(self):
        path = self._selected_backup_path()
        if not path:
            return
        if not os.path.exists(path):
            messagebox.showwarning(APP_NAME, "Selected backup no longer exists.")
            self._refresh_backups()
            return
        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            messagebox.showwarning(APP_NAME, "Please set the server folder in Preferences.")
            return
        worlds_root = os.path.join(server_dir, "worlds")
        world_name = self._world_name(server_dir)
        previous_world = os.path.join(worlds_root, world_name)
        old_world = os.path.join(worlds_root, f"Old_{world_name}")
        if os.path.isdir(old_world):
            shutil.rmtree(old_world)
        if os.path.isdir(previous_world):
            os.makedirs(worlds_root, exist_ok=True)
            shutil.move(previous_world, old_world)
        if not confirm_dialog(
            self,
            "Restore selected backup? This may overwrite data.",
            min_width=420,
            wraplength=420,
            extra_width=0,
        ):
            return
        create_backup = confirm_dialog(
            self,
            "Create a backup of the current world before restoring?",
            min_width=420,
            wraplength=420,
            extra_width=0,
        )
        if create_backup:
            if self.backups_dir_var.get().strip():
                self._create_backup(suffix="pre-restore")
            else:
                messagebox.showwarning(APP_NAME, "Backups folder is not set. Skipping pre-restore backup.")
        if path.endswith(".zip"):
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    bad = zf.testzip()
                if bad:
                    messagebox.showerror(APP_NAME, f"Backup verification failed: {bad}")
                    return
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"Backup verification failed: {exc}")
                return
        try:
            if path.endswith(".zip"):
                shutil.unpack_archive(path, os.path.join(server_dir, "worlds"))
            elif os.path.isdir(path):
                dest = os.path.join(server_dir, "worlds")
                basename = os.path.basename(path.rstrip(os.sep))
                target = os.path.join(dest, basename)
                if os.path.isdir(target):
                    shutil.rmtree(target)
                os.makedirs(dest, exist_ok=True)
                shutil.copytree(path, target)
            else:
                messagebox.showinfo(APP_NAME, "Unsupported backup format.")
                return
            messagebox.showinfo(APP_NAME, "Restore completed.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Restore failed: {exc}")

    def _open_backups_folder(self):
        path = self.backups_dir_var.get().strip()
        if not path:
            messagebox.showinfo(APP_NAME, "Backups folder is not set.")
            return
        if not os.path.isdir(path):
            messagebox.showwarning(APP_NAME, "Backups folder does not exist.")
            return
        try:
            if os.name == "nt":
                os.startfile(path)
            elif os.name == "posix":
                os.system(f'xdg-open "{path}"')
        except Exception:
            messagebox.showerror(APP_NAME, "Unable to open backups folder.")

    def _start_server(self):
        if self.server_process and self.server_process.poll() is None:
            messagebox.showinfo(APP_NAME, "Server is already running.")
            return
        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            messagebox.showwarning(APP_NAME, "Please set the server folder in Preferences.")
            return
        if not os.path.isdir(server_dir):
            messagebox.showwarning(APP_NAME, "Server folder does not exist.")
            return
        try:
            self.core.start_server()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to start server: {exc}")
            return
        self.server_process = self.core.server_process
        self.server_backend = self.core.server_backend
        self._server_dir_running = server_dir

        self.btn_server_start.config(state="disabled")
        self.btn_server_stop.config(state="normal")
        self.btn_server_refresh.config(state="normal")
        self.status_running_var.set("Running")
        self.server_start_time = self.core.server_start_time or time.time()
        self.server_start_monotonic = time.monotonic()
        self._append_console("Server started.\n")
        self._trigger_macros_for_event("server_started", None)
        self._set_console_enabled(True)
        self._update_uptime()

    def _server_reader(self):
        try:
            for line in self.server_process.stdout:
                if line:
                    self.server_queue.put(line)
                    name = self._parse_player_event(line)
                    if name:
                        self.server_queue.put(name)
                    chat = self._parse_chat_message(line)
                    if chat:
                        self.server_queue.put(("chat_message", chat))
        except Exception as exc:
            self.server_queue.put(f"[Console error] {exc}\n")
        finally:
            self.server_queue.put("[Server stopped]\n")
            self.server_queue.put(("server_stopped", None))

    def _poll_server_output(self):
        try:
            while True:
                item = self.server_queue.get_nowait()
                if isinstance(item, tuple):
                    event, value = item
                    if event == "player_connected":
                        self.live_players.add(value)
                        self._refresh_live_players()
                        self._trigger_macros_for_event("player_connected", value)
                    elif event == "player_join":
                        self.live_players.add(value)
                        self._refresh_live_players()
                        self._trigger_macros_for_event("player_join", value)
                    elif event == "player_leave":
                        self.live_players.discard(value)
                        self._refresh_live_players()
                        self._trigger_macros_for_event("player_leave", value)
                    elif event == "player_death":
                        self._trigger_macros_for_event("player_death", value)
                    elif event == "server_stopped":
                        self.live_players.clear()
                        self._refresh_live_players()
                        self._trigger_macros_for_event("server_stopped", None)
                    elif event == "chat_message":
                        if isinstance(value, dict):
                            self._trigger_macros_for_chat_keyword(value.get("player"), value.get("message"))
                    continue
                self.web_logs.append(item)
                self._append_console(item)
        except queue.Empty:
            pass
        self._poll_macro_runs()
        if self.server_process and self.server_process.poll() is not None:
            self._stop_log_tailer()
            self.btn_server_start.config(state="normal")
            self.btn_server_stop.config(state="disabled")
            self.btn_server_refresh.config(state="disabled")
            self.status_running_var.set("Stopped")
            self.server_start_time = None
            self.server_start_monotonic = None
            self.server_backend = None
            self._server_dir_running = None
            self._perf_prev = None
            self.status_uptime_var.set("Uptime: -")
            self._set_console_enabled(False)
        self.after(200, self._poll_server_output)

    def _poll_macro_runs(self):
        if self._active_macro_run is None:
            try:
                req = self._macro_run_requests.get_nowait()
            except queue.Empty:
                return
            if not req or not req.get("commands"):
                return
            run_id = req["run_id"]
            self._active_macro_run = {
                "run_id": run_id,
                "macro_id": req.get("macro_id"),
                "macro_title": req.get("macro_title"),
                "commands": list(req.get("commands") or []),
                "idx": 0,
            }
            with self._macro_runs_lock:
                run = self._macro_runs_by_id.get(run_id)
                if run:
                    run["started_at"] = time.time()
            self.after(10, self._macro_run_next_step)

    def _macro_run_next_step(self):
        state = self._active_macro_run
        if not state:
            return
        commands = state.get("commands") or []
        idx = int(state.get("idx") or 0)
        run_id = state.get("run_id")
        if idx >= len(commands):
            with self._macro_runs_lock:
                run = self._macro_runs_by_id.get(run_id)
                if run and run.get("finished_at") is None:
                    run["finished_at"] = time.time()
                    steps = run.get("steps") or []
                    run["success"] = all(bool(step.get("success")) for step in steps) if steps else True
            self._active_macro_run = None
            self.after(10, self._poll_macro_runs)
            return

        cmd = str(commands[idx] or "").strip()
        if not cmd:
            state["idx"] = idx + 1
            self.after(10, self._macro_run_next_step)
            return

        try:
            self.core.send_command(cmd)
        except Exception:
            pass
        capture_start_len = len(self.web_logs)
        try:
            self._append_console(f"> {cmd}\n")
        except Exception:
            pass
        # Capture output shortly after sending the command (best-effort; logs are async).
        state["pending"] = {"cmd": cmd, "capture_start_len": capture_start_len, "sent_at": time.time()}
        self.after(900, self._macro_run_capture_step)

    def _macro_run_capture_step(self):
        state = self._active_macro_run
        if not state or not state.get("pending"):
            return
        pending = state.pop("pending")
        cmd = pending.get("cmd") or ""
        capture_start_len = int(pending.get("capture_start_len") or 0)
        sent_at = float(pending.get("sent_at") or time.time())
        run_id = state.get("run_id")

        logs_now = list(self.web_logs)
        output_lines = []
        truncated = False
        if capture_start_len <= len(logs_now):
            output_lines = logs_now[capture_start_len:]
        else:
            # Deque may have rotated; fallback to last few lines.
            truncated = True
            output_lines = logs_now[-30:]

        joined = "".join(output_lines).lower()
        success = True
        if "unknown command" in joined or "error" in joined or "exception" in joined:
            success = False

        step = {
            "command": cmd,
            "sent_at": sent_at,
            "captured_at": time.time(),
            "success": success,
            "truncated": truncated,
            "output": output_lines,
        }
        with self._macro_runs_lock:
            run = self._macro_runs_by_id.get(run_id)
            if run:
                run.setdefault("steps", []).append(step)

        state["idx"] = int(state.get("idx") or 0) + 1
        self.after(10, self._macro_run_next_step)

    def _trigger_macros_for_event(self, trigger_event, player_name=None):
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
            stored_trigger = TRIGGER_CANONICAL.get(str(macro.get("trigger") or "").strip().lower(), (macro.get("trigger") or "manual").strip().lower())
            if stored_trigger != trigger_event:
                continue
            commands = macro.get("commands") or []
            if not commands:
                continue
            self._queue_macro_run(commands, macro_id=macro.get("id"), macro_title=macro.get("title", ""), player_name=name)

    def _trigger_macros_for_chat_keyword(self, player_name=None, message: str = ""):
        msg = str(message or "")
        if not msg:
            return
        name = str(player_name or "").strip() if player_name else ""
        try:
            macros = self.macro_store.list()
        except Exception:
            return
        for macro in macros:
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
            self._queue_macro_run(commands, macro_id=macro.get("id"), macro_title=macro.get("title", ""), player_name=name, message=msg)

    def _append_console(self, text):
        self.console_text.config(state="normal")
        self.console_text.insert("end", text)
        self.console_text.see("end")
        self.console_text.config(state="disabled")

    def _set_console_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.console_input.config(state=state)
        if not enabled:
            self.console_input.delete(0, tk.END)

    def _redirect_console_input(self, event):
        if (event.state & 0x4) and event.keysym.lower() in {"c", "a"}:
            return
        if event.char and event.char.isprintable():
            self.console_input.focus_set()
            self.console_input.insert("end", event.char)
            return "break"
        if event.keysym == "Return":
            self.console_input.focus_set()
            return "break"
        return "break"

    def _send_console_input(self, _event):
        cmd = self.console_input.get().strip()
        if not cmd:
            return "break"
        if not self.server_process or self.server_process.poll() is not None:
            messagebox.showwarning(APP_NAME, "Server is not running.")
            return "break"
        try:
            self.server_process.stdin.write(cmd + "\n")
            self.server_process.stdin.flush()
            self._append_console(f"> {cmd}\n")
            self.console_input.delete(0, tk.END)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to send command: {exc}")
        return "break"

    def _stop_server(self):
        if not self.server_process or self.server_process.poll() is not None:
            return
        try:
            self.core.stop_server()
        except Exception:
            pass
        self.after(5000, self._force_stop_server)

    def _force_stop_server(self):
        if not self.server_process or self.server_process.poll() is not None:
            return
        try:
            self.core.stop_server()
        except Exception:
            pass
        self._stop_log_tailer()
        self.server_start_time = None
        self.server_start_monotonic = None
        self.server_backend = None
        self._server_dir_running = None
        self._perf_prev = None
        self.status_uptime_var.set("Uptime: -")
        self.btn_server_start.config(state="normal")
        self.btn_server_stop.config(state="disabled")
        self.btn_server_refresh.config(state="disabled")
        self.status_running_var.set("Stopped")
        self.live_players.clear()
        self._refresh_live_players()
        self._set_console_enabled(False)

    def _on_close(self):
        try:
            self.core.close()
        except Exception:
            pass
        self._stop_web_manager()
        self._shutdown_server_process()
        self.destroy()

    def _shutdown_server_process(self):
        try:
            self.core.stop_server()
        except Exception:
            pass
        self.server_backend = None
        self._server_dir_running = None
        self._perf_prev = None
        self._stop_log_tailer()

    def _build_whitelist_tab(self):
        self.whitelist_list = tk.Listbox(self.tab_whitelist)
        self.whitelist_list.pack(fill="both", expand=True, padx=8, pady=8)
        buttons = ttk.Frame(self.tab_whitelist)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Add", command=self._add_whitelist).pack(side="left", padx=4)
        ttk.Button(buttons, text="Remove", command=self._remove_whitelist).pack(side="left", padx=4)

    def _build_ops_tab(self):
        self.ops_list = tk.Listbox(self.tab_ops)
        self.ops_list.pack(fill="both", expand=True, padx=8, pady=8)
        buttons = ttk.Frame(self.tab_ops)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Add", command=self._add_op).pack(side="left", padx=4)
        ttk.Button(buttons, text="Remove", command=self._remove_op).pack(side="left", padx=4)

    def _build_players_tab(self):
        live_label = ttk.Label(self.tab_players, text="Live Players")
        live_label.pack(fill="x", padx=8, pady=(8, 0))
        self.live_players_list = tk.Listbox(self.tab_players, height=6)
        self.live_players_list.pack(fill="x", padx=8, pady=(0, 8))

        known_label = ttk.Label(self.tab_players, text="Known Players")
        known_label.pack(fill="x", padx=8, pady=(4, 0))
        self.players_list = tk.Listbox(self.tab_players)
        self.players_list.pack(fill="both", expand=True, padx=8, pady=8)
        self.players_status = ttk.Label(self.tab_players, text="")
        self.players_status.pack(fill="x", padx=8, pady=(0, 8))

    def _server_path(self, filename):
        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            return None
        return os.path.join(server_dir, filename)

    def _load_json_list(self, path):
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_json_list(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _build_xuid_name_map(self, server_dir):
        mapping = {}
        allowlist = self._load_json_list(self._server_path("allowlist.json"))
        for entry in allowlist:
            name = (entry.get("name") or "").strip()
            xuid = (entry.get("xuid") or "").strip()
            if xuid and name:
                mapping[xuid] = name
        players_json = os.path.join(server_dir, "players.json")
        if os.path.exists(players_json):
            data = self._load_json_list(players_json)
            for entry in data:
                name = (entry.get("name") or "").strip()
                xuid = (entry.get("xuid") or "").strip()
                if xuid and name:
                    mapping.setdefault(xuid, name)
        return mapping

    def _resolve_live_players_for_web(self, server_dir):
        xuid_name_map = self._build_xuid_name_map(server_dir) if server_dir else {}
        resolved = []
        seen = set()
        for name in sorted(self.live_players):
            resolved_name = xuid_name_map.get(name, name)
            if resolved_name and resolved_name not in seen:
                resolved.append(resolved_name)
                seen.add(resolved_name)
        return resolved

    def _refresh_players(self):
        self.whitelist_list.delete(0, tk.END)
        self.ops_list.delete(0, tk.END)
        self.players_list.delete(0, tk.END)
        server_dir = self.server_dir_var.get().strip()
        if not server_dir or not os.path.isdir(server_dir):
            self.players_status.config(text="Set a valid server folder.")
            return

        allowlist = self._load_json_list(self._server_path("allowlist.json"))
        permissions = self._load_json_list(self._server_path("permissions.json"))
        xuid_name_map = self._build_xuid_name_map(server_dir)

        for entry in allowlist:
            name = entry.get("name", "unknown")
            xuid = entry.get("xuid", "")
            display = f"{name} ({xuid})" if xuid else name
            self.whitelist_list.insert(tk.END, display)

        for entry in permissions:
            raw_name = entry.get("name", "")
            xuid = (entry.get("xuid") or "").strip()
            name = (raw_name or "").strip()
            if (not name or name.lower() == "unknown") and xuid:
                name = xuid_name_map.get(xuid, name)
            if not name:
                name = "unknown"
            perm = entry.get("permission", "operator")
            display = f"{name} [{perm}] ({xuid})" if xuid else f"{name} [{perm}]"
            self.ops_list.insert(tk.END, display)

        players = self._load_known_players(server_dir)
        for name in players:
            self.players_list.insert(tk.END, name)
        self.players_status.config(text=f"{len(players)} player(s) found.")
        self._refresh_live_players()

    def _load_known_players(self, server_dir):
        players = set()
        players_json = os.path.join(server_dir, "players.json")
        if os.path.exists(players_json):
            data = self._load_json_list(players_json)
            for entry in data:
                name = entry.get("name")
                if name:
                    players.add(name)
        worlds_dir = os.path.join(server_dir, "worlds")
        if os.path.isdir(worlds_dir):
            worlds = [n for n in os.listdir(worlds_dir) if os.path.isdir(os.path.join(worlds_dir, n))]
            if worlds:
                players_dir = os.path.join(worlds_dir, sorted(worlds)[0], "players")
                if os.path.isdir(players_dir):
                    for file_name in os.listdir(players_dir):
                        base = os.path.splitext(file_name)[0]
                        if base:
                            players.add(base)
        return sorted(players)

    def _add_whitelist(self):
        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            messagebox.showwarning(APP_NAME, "Please set the server folder in Preferences.")
            return
        name = prompt_string(self, "Player name:")
        if not name:
            return
        xuid = prompt_string(self, "XUID (optional):")
        path = self._server_path("allowlist.json")
        data = self._load_json_list(path)
        data.append({"name": name, "xuid": xuid or ""})
        try:
            self._save_json_list(path, data)
            self._refresh_players()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to update allowlist: {exc}")

    def _remove_whitelist(self):
        selection = self.whitelist_list.curselection()
        if not selection:
            return
        path = self._server_path("allowlist.json")
        data = self._load_json_list(path)
        index = selection[0]
        if index >= len(data):
            return
        data.pop(index)
        try:
            self._save_json_list(path, data)
            self._refresh_players()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to update allowlist: {exc}")

    def _add_op(self):
        server_dir = self.server_dir_var.get().strip()
        if not server_dir:
            messagebox.showwarning(APP_NAME, "Please set the server folder in Preferences.")
            return
        name = prompt_string(self, "Player name:")
        if not name:
            return
        xuid = prompt_string(self, "XUID (optional):")
        perm = prompt_string(self, "Permission (operator/member/visitor):", "operator")
        path = self._server_path("permissions.json")
        data = self._load_json_list(path)
        data.append({"name": name, "xuid": xuid or "", "permission": perm or "operator"})
        try:
            self._save_json_list(path, data)
            self._refresh_players()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to update permissions: {exc}")

    def _remove_op(self):
        selection = self.ops_list.curselection()
        if not selection:
            return
        path = self._server_path("permissions.json")
        data = self._load_json_list(path)
        index = selection[0]
        if index >= len(data):
            return
        data.pop(index)
        try:
            self._save_json_list(path, data)
            self._refresh_players()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to update permissions: {exc}")

    def _refresh_live_players(self):
        self.live_players_list.delete(0, tk.END)
        for name in sorted(self.live_players):
            self.live_players_list.insert(tk.END, name)
        self.status_connected_var.set(str(len(self.live_players)))

    def _parse_player_event(self, line):
        # Important: "Player connected" happens before the player is fully targetable by commands.
        # We treat it as a separate event for live player tracking, and only fire macros on "joined the game".
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

        # Kept for potential future use, but does not trigger macros.
        spawned = re.search(r"Player Spawned:\s*(?P<name>.+?)(?:,|\s+xuid:|$)", line, re.IGNORECASE)
        if spawned:
            name = self._clean_player_name(spawned.group("name"))
            if name:
                return ("player_connected", name)

        leave_patterns = [
            r"Player disconnected:\s*(?P<name>[^,]+)",
            r"\b(?P<name>.+?)\s+left the game\b",
            r"\bPlayer\s+(?P<name>.+?)\s+left\b",
            r"Lost connection:\s*(?P<name>[^,]+)",
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
        """Best-effort chat parsing for BDS/Endstone logs."""
        text = str(line or "").strip("\n")
        if not text:
            return None
        patterns = [
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
            return {"player": name, "message": message}
        return None

    def _clean_player_name(self, raw_name: str) -> str:
        name = str(raw_name or "").strip()
        if not name:
            return ""
        # Endstone/BDS logs sometimes include extra tokens after the name (xuid/pfid/etc).
        name = re.sub(r"\s+xuid:.*$", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\s+pfid:.*$", "", name, flags=re.IGNORECASE).strip()
        # Occasionally "name, xuid: ..." is passed through here.
        if "," in name:
            name = name.split(",", 1)[0].strip()
        return name

    def _start_log_tailer(self, server_dir: str, backend: str):
        self._stop_log_tailer()
        if not server_dir or not os.path.isdir(server_dir):
            return
        backend = (backend or "").lower()
        # Endstone servers often write logs to files instead of stdout (especially when using start.sh).
        if backend != "endstone":
            return
        self._log_tailer_stop = threading.Event()
        self._log_tailer_thread = threading.Thread(
            target=self._log_tailer_loop, args=(server_dir, self._log_tailer_stop), daemon=True
        )
        self._log_tailer_thread.start()

    def _stop_log_tailer(self):
        stop_event = self._log_tailer_stop
        thread = self._log_tailer_thread
        if stop_event:
            stop_event.set()
        if thread and thread.is_alive():
            try:
                thread.join(timeout=1.5)
            except Exception:
                pass
        self._log_tailer_path = None
        self._log_tailer_thread = None

    def _pick_log_file(self, server_dir: str) -> Optional[str]:
        logs_dir = os.path.join(server_dir, "logs")
        if not os.path.isdir(logs_dir):
            return None
        candidates = []
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

    def _log_tailer_loop(self, server_dir: str, stop_event: threading.Event):
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
                    self._log_tailer_path = path
                    try:
                        fp = open(path, "r", encoding="utf-8", errors="replace")
                        fp.seek(0, os.SEEK_END)
                        pos = fp.tell()
                    except Exception:
                        fp = None
                        path = None
                        self._log_tailer_path = None

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

    def _match_player_death(self, line):
        match = re.search(
            r"\b(?P<player>[A-Za-z0-9_]+)\b.*\b(?:slain|killed|died|fell|burned|shot|exploded|blew|hit)\b",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group("player").strip()
        return None

    def _update_server_status(self):
        running = "Running" if self.server_process and self.server_process.poll() is None else "Stopped"
        self.status_running_var.set(running)
        port = "-"
        gamemode = "-"
        max_players = "-"
        if self.properties and self.properties.data:
            port = self.properties.data.get("server-port", "-")
            gamemode = self.properties.data.get("gamemode", "-")
            max_players = self.properties.data.get("max-players", "-")
        self.status_port_var.set(port)
        self.status_gamemode_var.set(gamemode)
        self.status_max_players_var.set(max_players)
        self.cached_local_ip = self._get_local_ip()
        self.status_local_url_var.set(f"Local URL: {self.cached_local_ip}:{port}")

    def _validate_server_menu(self):
        server_dir = self.server_dir_var.get().strip()
        errors = []
        backend_pref = (self.settings.get("server_backend", "auto") or "auto").lower()
        missing = server_dir_missing_files(server_dir, preferred_backend=backend_pref)
        if missing:
            if missing == ["server folder"]:
                errors.append(("server_dir", "Server folder is not set or not found."))
            else:
                for name in missing:
                    errors.append((name, "File not found."))
            show_validation_dialog(self, errors)
            return
        prop_path = os.path.join(server_dir, "server.properties")

        props = PropertiesFile(prop_path)
        props.load()
        errors.extend(validate_properties_data(props.data))

        show_validation_dialog(self, errors)
