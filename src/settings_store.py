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
        return {"server_dir": "", "backups_dir": ""}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "server_dir": data.get("server_dir", ""),
            "backups_dir": data.get("backups_dir", ""),
        }
    except Exception:
        return {"server_dir": "", "backups_dir": ""}


def save_settings(data):
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
