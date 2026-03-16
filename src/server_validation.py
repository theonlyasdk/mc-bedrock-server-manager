import os
import shutil


def server_executable(server_dir):
    candidates = ["bedrock_server", "bedrock_server.exe"]
    for name in candidates:
        path = os.path.join(server_dir, name)
        if os.path.exists(path):
            return path
    return None


def _endstone_start_script(server_dir):
    candidates = ["start.sh", "start.bat"]
    for name in candidates:
        path = os.path.join(server_dir, name)
        if os.path.exists(path):
            return path
    return None


def _endstone_executable(server_dir):
    candidates = ["endstone", "endstone.exe"]
    for name in candidates:
        path = os.path.join(server_dir, name)
        if os.path.exists(path):
            return path
    return None


def server_launch_command(server_dir, preferred_backend="auto"):
    preferred_backend = (preferred_backend or "auto").lower()
    if preferred_backend not in {"auto", "bedrock", "endstone"}:
        preferred_backend = "auto"

    def resolve_endstone_cli():
        local_exe = _endstone_executable(server_dir)
        if local_exe:
            return local_exe
        found = shutil.which("endstone")
        if found:
            return found
        home = os.path.expanduser("~")
        candidate = os.path.join(home, ".local", "bin", "endstone")
        if os.path.exists(candidate):
            return candidate
        return None

    def endstone_cli_command():
        endstone = resolve_endstone_cli()
        if not endstone:
            return None
        return [endstone, "-s", server_dir, "--yes", "--no-interactive"]

    if preferred_backend == "bedrock":
        bedrock = server_executable(server_dir)
        if bedrock:
            return ([bedrock], "bedrock")
        return (None, None)

    if preferred_backend == "endstone":
        script = _endstone_start_script(server_dir)
        if script:
            if script.endswith(".bat") or os.name == "nt":
                return (["cmd.exe", "/c", script], "endstone")
            return (["bash", script], "endstone")
        exe = _endstone_executable(server_dir)
        if exe:
            return ([exe], "endstone")
        cmd = endstone_cli_command()
        if cmd:
            return (cmd, "endstone")
        return (None, None)

    script = _endstone_start_script(server_dir)
    if script:
        if script.endswith(".bat") or os.name == "nt":
            return (["cmd.exe", "/c", script], "endstone")
        return (["bash", script], "endstone")
    exe = _endstone_executable(server_dir)
    if exe:
        return ([exe], "endstone")
    bedrock = server_executable(server_dir)
    if bedrock:
        return ([bedrock], "bedrock")
    cmd = endstone_cli_command()
    if cmd:
        return (cmd, "endstone")
    return (None, None)


def server_dir_missing_files(server_dir, preferred_backend="auto"):
    if not server_dir or not os.path.isdir(server_dir):
        return ["server folder"]
    missing = []
    if not os.path.exists(os.path.join(server_dir, "server.properties")):
        missing.append("server.properties")
    launch_cmd, _ = server_launch_command(server_dir, preferred_backend=preferred_backend)
    if not launch_cmd:
        missing.append("bedrock_server(.exe) or endstone")
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
