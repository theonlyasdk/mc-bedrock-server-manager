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

from constants import APP_AUTHOR, APP_LICENSE, APP_NAME
from dialogs import confirm_dialog, prompt_string, show_validation_dialog
from properties_file import PropertiesFile
from server_validation import (
    server_dir_missing_files,
    server_executable,
    validate_properties_data,
)
from settings_store import load_settings, save_settings
from theme import apply_theme
from WebManager import WebManagerServer


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
        self.server_queue = queue.Queue()
        self.live_players = set()
        self.web_logs = deque(maxlen=200)
        self.cached_public_ip = "-"
        self.cached_local_ip = self._get_local_ip()
        threading.Thread(target=self._fetch_public_ip, daemon=True).start()
        self.web_manager_host_var = tk.StringVar()
        self.web_manager_port_var = tk.StringVar()
        self.web_manager_status_var = tk.StringVar(value="Web manager stopped.")
        self.web_manager = WebManagerServer(
            status_provider=self._web_manager_status_payload,
            command_handler=self._web_manager_command_handler,
        )
        self.web_backup_in_progress = False
        self.web_backup_error = None

        self._build_menu()
        self._build_tabs()
        self._load_preferences_into_ui()
        self._refresh_properties()
        self._refresh_backups()
        self._refresh_players()
        self._poll_server_output()

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

        self.prefs_status = ttk.Label(self.tab_prefs, text="")
        self.prefs_status.grid(row=3, column=0, columnspan=3, sticky="w", **pad)

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

    def _web_send_command(self, cmd):
        if not self.server_process or self.server_process.poll() is not None:
            return
        try:
            self.server_process.stdin.write(cmd + "\n")
            self.server_process.stdin.flush()
            # Log the sent command
            self.web_logs.append(f"> {cmd}\n")
            self._append_console(f"> {cmd}\n")
        except Exception:
            pass

    def _web_update_property(self, key, value):
        if not self.properties: return
        self.properties.set_value(key, value)
        try:
            self.properties.save()
            self._refresh_properties()
        except Exception:
            pass

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
                if os.path.isdir(target): shutil.rmtree(target)
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

        bedrock = {
            "running": running,
            "port": props.get("server-port", "-"),
            "gamemode": props.get("gamemode", "-"),
            "connected": len(self.live_players),
            "max_players": props.get("max-players", "-"),
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
            "backup_in_progress": self.web_backup_in_progress,
            "backup_error": backup_error,
        }

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
        self.web_manager_host_var.set(self.settings.get("web_manager_host", "127.0.0.1"))
        self.web_manager_port_var.set(str(self.settings.get("web_manager_port", 5050)))
        self._validate_settings()
        self._update_web_manager_status()

    def _save_preferences_from_ui(self):
        self.settings["server_dir"] = self.server_dir_var.get().strip()
        self.settings["backups_dir"] = self.backups_dir_var.get().strip()
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
        server_status = "Missing"
        if server_dir:
            missing = server_dir_missing_files(server_dir)
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
        if not self.properties:
            return
        if not os.path.exists(self.properties.path):
            messagebox.showerror(APP_NAME, "server.properties not found.")
            return
        self.properties.set_value(key, new_value)
        try:
            self.properties.save()
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
        exe = server_executable(server_dir)
        if not exe:
            messagebox.showwarning(APP_NAME, "Server executable not found in server folder.")
            return
        try:
            self.server_process = subprocess.Popen(
                [exe],
                cwd=server_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to start server: {exc}")
            return

        self.btn_server_start.config(state="disabled")
        self.btn_server_stop.config(state="normal")
        self.btn_server_refresh.config(state="normal")
        self.status_running_var.set("Running")
        self.server_start_time = time.time()
        self.server_start_monotonic = time.monotonic()
        self.web_logs.clear()
        self.web_logs.append("Server started.\n")
        self._append_console("Server started.\n")
        self._set_console_enabled(True)

        threading.Thread(target=self._server_reader, daemon=True).start()
        self._update_uptime()

    def _server_reader(self):
        try:
            for line in self.server_process.stdout:
                if line:
                    self.server_queue.put(line)
                    name = self._parse_player_event(line)
                    if name:
                        self.server_queue.put(name)
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
                    elif event == "player_disconnected":
                        self.live_players.discard(value)
                        self._refresh_live_players()
                    elif event == "server_stopped":
                        self.live_players.clear()
                        self._refresh_live_players()
                    continue
                self.web_logs.append(item)
                self._append_console(item)
        except queue.Empty:
            pass
        if self.server_process and self.server_process.poll() is not None:
            self.btn_server_start.config(state="normal")
            self.btn_server_stop.config(state="disabled")
            self.btn_server_refresh.config(state="disabled")
            self.status_running_var.set("Stopped")
            self.server_start_time = None
            self.server_start_monotonic = None
            self.status_uptime_var.set("Uptime: -")
            self._set_console_enabled(False)
        self.after(200, self._poll_server_output)

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
            self.server_process.stdin.write("stop\n")
            self.server_process.stdin.flush()
        except Exception:
            pass
        self.after(5000, self._force_stop_server)

    def _force_stop_server(self):
        if not self.server_process or self.server_process.poll() is not None:
            return
        try:
            self.server_process.terminate()
        except Exception:
            pass
        self.server_start_time = None
        self.server_start_monotonic = None
        self.status_uptime_var.set("Uptime: -")
        self.btn_server_start.config(state="normal")
        self.btn_server_stop.config(state="disabled")
        self.btn_server_refresh.config(state="disabled")
        self.status_running_var.set("Stopped")
        self.live_players.clear()
        self._refresh_live_players()
        self._set_console_enabled(False)

    def _on_close(self):
        self._stop_web_manager()
        self._shutdown_server_process()
        self.destroy()

    def _shutdown_server_process(self):
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
        except subprocess.TimeoutExpired:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

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
        connected = re.search(r"Player connected:\s*([^,]+)", line)
        if connected:
            name = connected.group(1).strip()
            return ("player_connected", name)
        disconnected = re.search(r"Player disconnected:\s*([^,]+)", line)
        if disconnected:
            name = disconnected.group(1).strip()
            return ("player_disconnected", name)
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
        missing = server_dir_missing_files(server_dir)
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
