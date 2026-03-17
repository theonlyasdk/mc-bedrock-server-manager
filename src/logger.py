import os
import time
from typing import Any

_DEBUG = True


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def set_debug(enabled: bool) -> None:
    global _DEBUG
    _DEBUG = bool(enabled)


def is_debug() -> bool:
    env = os.environ.get("MBM_DEBUG")
    if env is not None:
        return _truthy(env)
    return _DEBUG


def debug(message: str, *args: Any) -> None:
    if not is_debug():
        return
    if args:
        try:
            message = message.format(*args)
        except Exception:
            pass
    ts = time.strftime("%H:%M:%S")
    print(f"[DEBUG {ts}] {message}", flush=True)

