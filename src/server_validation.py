import os


def server_executable(server_dir):
    candidates = ["bedrock_server", "bedrock_server.exe"]
    for name in candidates:
        path = os.path.join(server_dir, name)
        if os.path.exists(path):
            return path
    return None


def server_dir_missing_files(server_dir):
    if not server_dir or not os.path.isdir(server_dir):
        return ["server folder"]
    missing = []
    if not os.path.exists(os.path.join(server_dir, "server.properties")):
        missing.append("server.properties")
    if not server_executable(server_dir):
        missing.append("bedrock_server(.exe)")
    if not os.path.exists(os.path.join(server_dir, "permissions.json")):
        missing.append("permissions.json")
    allowlist = os.path.join(server_dir, "allowlist.json")
    whitelist = os.path.join(server_dir, "whitelist.json")
    if not (os.path.exists(allowlist) or os.path.exists(whitelist)):
        missing.append("allowlist.json or whitelist.json")
    return missing


def validate_properties_data(data):
    errors = []

    def require_int(key, min_value=None, max_value=None):
        value = data.get(key)
        if value is None:
            errors.append((key, "Missing."))
            return
        try:
            ivalue = int(value)
            if min_value is not None and ivalue < min_value:
                errors.append((key, f"Must be >= {min_value}."))
            if max_value is not None and ivalue > max_value:
                errors.append((key, f"Must be <= {max_value}."))
        except ValueError:
            errors.append((key, "Must be an integer."))

    def require_enum(key, options):
        value = (data.get(key) or "").lower()
        if not value:
            errors.append((key, "Missing."))
            return
        if value not in options:
            errors.append((key, f"Must be one of {', '.join(sorted(options))}."))

    require_int("server-port", 1, 65535)
    require_int("max-players", 1, None)
    require_enum("gamemode", {"survival", "creative", "adventure", "spectator"})
    require_enum("difficulty", {"peaceful", "easy", "normal", "hard"})
    require_enum("online-mode", {"true", "false"})
    require_enum("allow-cheats", {"true", "false"})

    return errors
