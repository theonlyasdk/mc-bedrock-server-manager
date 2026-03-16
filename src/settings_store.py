import json
import os


def app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def config_dir():
    return os.path.join(app_dir(), "MCBedrockServerManagerConfig")


def settings_path():
    return os.path.join(config_dir(), "settings.json")


def load_settings():
    path = settings_path()
    if not os.path.exists(path):
        return {
            "server_dir": "",
            "backups_dir": "",
            "server_backend": "auto",
            "autostart_server": False,
            "autostart_web_manager": False,
            "web_manager_host": "127.0.0.1",
            "web_manager_port": 5050,
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "server_dir": data.get("server_dir", ""),
            "backups_dir": data.get("backups_dir", ""),
            "server_backend": data.get("server_backend", "auto"),
            "autostart_server": bool(data.get("autostart_server", False)),
            "autostart_web_manager": bool(data.get("autostart_web_manager", False)),
            "web_manager_host": data.get("web_manager_host", "127.0.0.1"),
            "web_manager_port": data.get("web_manager_port", 5050),
        }
    except Exception:
        return {
            "server_dir": "",
            "backups_dir": "",
            "server_backend": "auto",
            "autostart_server": False,
            "autostart_web_manager": False,
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
        "web_manager_host": data.get("web_manager_host", "127.0.0.1"),
        "web_manager_port": data.get("web_manager_port", 5050),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
