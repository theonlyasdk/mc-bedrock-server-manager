import json
import os

from logger import debug


def app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def config_dir():
    return os.path.join(app_dir(), "MCBedrockServerManagerConfig")


def settings_path():
    return os.path.join(config_dir(), "settings.json")


def macros_path() -> str:
    """
    Canonical on-disk location for macros.json.

    Historical default was repo root (../macros.json). If that exists and the new
    config path doesn't, copy it forward so existing macros are preserved.
    """
    new_path = os.path.join(config_dir(), "macros.json")
    old_path = os.path.abspath(os.path.join(app_dir(), os.pardir, "macros.json"))
    try:
        if (not os.path.exists(new_path)) and os.path.isfile(old_path):
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            with open(old_path, "r", encoding="utf-8") as src:
                payload = src.read()
            with open(new_path, "w", encoding="utf-8") as dst:
                dst.write(payload)
    except Exception:
        pass
    return new_path


def load_settings():
    path = settings_path()
    if not os.path.exists(path):
        debug("Loading settings (defaults) - {} missing", path)
        return {
            "server_dir": "",
            "backups_dir": "",
            "server_backend": "auto",
            "autostart_server": False,
            "autostart_web_manager": False,
            "use_chat_logger_plugin": False,
            "debug": False,
            "web_manager_host": "127.0.0.1",
            "web_manager_port": 5050,
        }
    try:
        debug("Loading settings - {}", path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "server_dir": data.get("server_dir", ""),
            "backups_dir": data.get("backups_dir", ""),
            "server_backend": data.get("server_backend", "auto"),
            "autostart_server": bool(data.get("autostart_server", False)),
            "autostart_web_manager": bool(data.get("autostart_web_manager", False)),
            "use_chat_logger_plugin": bool(data.get("use_chat_logger_plugin", False)),
            "debug": bool(data.get("debug", False)),
            "web_manager_host": data.get("web_manager_host", "127.0.0.1"),
            "web_manager_port": data.get("web_manager_port", 5050),
        }
    except Exception:
        debug("Loading settings failed; using defaults")
        return {
            "server_dir": "",
            "backups_dir": "",
            "server_backend": "auto",
            "autostart_server": False,
            "autostart_web_manager": False,
            "use_chat_logger_plugin": False,
            "debug": False,
            "web_manager_host": "127.0.0.1",
            "web_manager_port": 5050,
        }


def save_settings(data):
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    snapshot = {
        "server_dir": data.get("server_dir", ""),
        "backups_dir": data.get("backups_dir", ""),
        "server_backend": data.get("server_backend", "auto"),
        "autostart_server": bool(data.get("autostart_server", False)),
        "autostart_web_manager": bool(data.get("autostart_web_manager", False)),
        "use_chat_logger_plugin": bool(data.get("use_chat_logger_plugin", False)),
        "debug": bool(data.get("debug", False)),
        "web_manager_host": data.get("web_manager_host", "127.0.0.1"),
        "web_manager_port": data.get("web_manager_port", 5050),
    }
    debug("Saving settings - {}", path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
