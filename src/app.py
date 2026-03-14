import os
import queue
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
import webbrowser
import zipfile
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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x600")
        apply_theme()

        self.settings = load_settings()
        self.properties = None
        self.server_process = None
        self.server_queue = queue.Queue()
        self.live_players = set()

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

        self.tabs.add(self.tab_prefs, text="Preferences")
        self.tabs.add(self.tab_details, text="Server Properties")
        self.tabs.add(self.tab_backups, text="Backups")
        self.tabs.add(self.tab_manage, text="Server Management")

        self._build_prefs_tab()
        self._build_details_tab()
        self._build_backups_tab()
        self._build_manage_tab()

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
        self.backups_tree.heading("name", text="Name")
        self.backups_tree.heading("size", text="Size")
        self.backups_tree.heading("modified", text="Modified")
        self.backups_tree.column("name", width=320, anchor="w")
        self.backups_tree.column("size", width=120, anchor="e")
        self.backups_tree.column("modified", width=200, anchor="w")
        self.backups_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.backups_tree.bind("<<TreeviewSelect>>", self._on_backup_select)

        self.backups_empty = ttk.Label(self.tab_backups, text="No backups. Click New Backup to backup current world.")
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

    def _load_preferences_into_ui(self):
        self.server_dir_var.set(self.settings.get("server_dir", ""))
        self.backups_dir_var.set(self.settings.get("backups_dir", ""))
        self._validate_settings()

    def _save_preferences_from_ui(self):
        self.settings["server_dir"] = self.server_dir_var.get().strip()
        self.settings["backups_dir"] = self.backups_dir_var.get().strip()
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
        for item in self.backups_tree.get_children():
            self.backups_tree.delete(item)
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
                size = self._format_size(self._path_size(path))
                modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path)))
            except OSError:
                size = "-"
                modified = "-"
            self.backups_tree.insert("", "end", values=(name, size, modified))
        self.backups_status.config(text=f"{len(files)} backup(s) found.")
        self._set_backup_buttons_state(False)
        if files:
            self.backups_empty.place_forget()
        else:
            self.backups_empty.lift()
            self.backups_empty.place(relx=0.5, rely=0.5, anchor="center")

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
        try:
            shutil.make_archive(base_name, "zip", source)
            self._refresh_backups()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Backup failed: {exc}")

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
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                shutil.copytree(path, dest)
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
        self._append_console("Server started.\n")

        threading.Thread(target=self._server_reader, daemon=True).start()

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
                self._append_console(item)
        except queue.Empty:
            pass
        if self.server_process and self.server_process.poll() is not None:
            self.btn_server_start.config(state="normal")
            self.btn_server_stop.config(state="disabled")
            self.btn_server_refresh.config(state="disabled")
            self.status_running_var.set("Stopped")
        self.after(200, self._poll_server_output)

    def _append_console(self, text):
        self.console_text.config(state="normal")
        self.console_text.insert("end", text)
        self.console_text.see("end")
        self.console_text.config(state="disabled")

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
        self.btn_server_start.config(state="normal")
        self.btn_server_stop.config(state="disabled")
        self.btn_server_refresh.config(state="disabled")
        self.status_running_var.set("Stopped")
        self.live_players.clear()
        self._refresh_live_players()

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

        for entry in allowlist:
            name = entry.get("name", "unknown")
            xuid = entry.get("xuid", "")
            display = f"{name} ({xuid})" if xuid else name
            self.whitelist_list.insert(tk.END, display)

        for entry in permissions:
            name = entry.get("name", "unknown")
            xuid = entry.get("xuid", "")
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

