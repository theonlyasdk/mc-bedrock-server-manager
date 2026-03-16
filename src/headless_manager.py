import time
from typing import Callable, Optional

from core_manager import ManagerCore


class HeadlessManager(ManagerCore):
    """
    Backwards-compatible wrapper for the original headless implementation.
    Prefer importing `ManagerCore` from `core_manager.py` for new code.
    """

    def __init__(
        self,
        server_dir: Optional[str] = None,
        backend_preference: Optional[str] = None,
        web_host: Optional[str] = None,
        web_port: Optional[int] = None,
        macros_path: Optional[str] = None,
        log_sink: Optional[Callable[[str], None]] = None,
    ):
        settings = None
        super().__init__(settings=settings, macros_path=macros_path, log_sink=log_sink)
        if server_dir is not None:
            self.settings["server_dir"] = server_dir
        if backend_preference is not None:
            self.settings["server_backend"] = backend_preference
        if web_host is not None:
            self.settings["web_manager_host"] = web_host
        if web_port is not None:
            self.settings["web_manager_port"] = int(web_port)

    def run_forever(self) -> None:
        try:
            while True:
                self.drain_queue()
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

