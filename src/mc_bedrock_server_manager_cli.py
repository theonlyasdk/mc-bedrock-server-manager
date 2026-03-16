import argparse
import os
import sys

from constants import APP_NAME
from headless_manager import HeadlessManager
from settings_store import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcbsm-cli",
        description=(
            f"{APP_NAME} (Headless CLI)\n\n"
            "Starts the Web UI and/or the Bedrock/Endstone server without Tkinter.\n"
            "Useful for headless Linux servers (tmux/systemd/Docker)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--server-dir", help="Server directory (overrides saved setting).")
    parser.add_argument(
        "--backend",
        choices=["auto", "endstone", "bedrock"],
        help="Server backend preference (overrides saved setting).",
    )
    parser.add_argument("--web-host", default=None, help="Web manager host (default: saved setting).")
    parser.add_argument("--web-port", type=int, default=None, help="Web manager port (default: saved setting).")
    parser.add_argument("--macros-file", default=None, help="Path to macros.json (optional).")

    server_group = parser.add_argument_group("Server")
    server_group.add_argument(
        "--start-server",
        action="store_true",
        help="Start the Minecraft server process.",
    )

    web_group = parser.add_argument_group("Web Manager")
    web_group.add_argument(
        "--start-web",
        action="store_true",
        help="Start the Web Manager.",
    )
    web_group.add_argument(
        "--no-web",
        action="store_true",
        help="Do not start the Web UI/API server (even if --start-server is used).",
    )
    return parser


def autodetect_server_dir(start_dir: str, max_parents: int = 2) -> str | None:
    current = os.path.abspath(start_dir)
    for _ in range(max_parents + 1):
        try:
            server_props = os.path.join(current, "server.properties")
            if os.path.isfile(server_props):
                candidates = [
                    os.path.join(current, "bedrock_server"),
                    os.path.join(current, "bedrock_server.exe"),
                    os.path.join(current, "start.sh"),
                    os.path.join(current, "start.bat"),
                    os.path.join(current, "endstone"),
                    os.path.join(current, "endstone.exe"),
                ]
                if any(os.path.exists(p) for p in candidates):
                    return current
        except Exception:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # If user didn't specify anything, default to starting the Web UI.
    start_web = args.start_web or (not args.start_server and not args.no_web)
    if args.no_web:
        start_web = False

    settings = load_settings()
    server_dir = args.server_dir
    server_dir_source = "arg" if server_dir else None
    if not server_dir:
        configured = (settings.get("server_dir") or "").strip()
        if configured and os.path.isdir(configured):
            server_dir = configured
            server_dir_source = "config"
        else:
            detected = autodetect_server_dir(os.getcwd(), max_parents=2)
            if detected:
                server_dir = detected
                server_dir_source = "autodetect"
            elif configured:
                # Keep showing what config had, even if invalid, for debugging.
                server_dir = configured
                server_dir_source = "config (invalid)"

    mgr = HeadlessManager(
        server_dir=server_dir,
        backend_preference=args.backend,
        web_host=args.web_host,
        web_port=args.web_port,
        macros_path=args.macros_file,
        log_sink=lambda line: sys.stdout.write(line),
    )

    try:
        if server_dir:
            sys.stdout.write(f"[ServerDir] {server_dir} ({server_dir_source or 'unknown'})\n")
        else:
            sys.stdout.write("[ServerDir] (not set)\n")
        if start_web:
            mgr.start_web_manager(host=args.web_host, port=args.web_port)
        if args.start_server:
            mgr.start_server()
        mgr.run_forever()
        return 0
    except Exception as exc:
        sys.stderr.write(f"[Error] {exc}\n")
        try:
            mgr.close()
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
