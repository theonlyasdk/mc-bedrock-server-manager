import os
import subprocess
import sys


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    entrypoint = os.path.join(root, "src", "mc_bedrock_server_manager.py")
    if not os.path.isfile(entrypoint):
        print("Entrypoint not found:", entrypoint, file=sys.stderr)
        return 1

    name = "MCBedrockServerManager.exe" if os.name == "nt" else "MCBedrockServerManager"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--clean",
        "--name",
        name,
        entrypoint,
    ]

    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
