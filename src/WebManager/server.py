import os
import threading
from typing import Callable, Optional

from flask import Flask, jsonify, render_template, request
from werkzeug.serving import make_server


class WebManagerServer:
    def __init__(self, status_provider: Optional[Callable[[], dict]] = None, command_handler: Optional[Callable[[str, dict], dict]] = None):
        self.status_provider = status_provider
        self.command_handler = command_handler
        self.host = "127.0.0.1"
        self.port = 5050
        self._server = None
        self._thread = None
        template_folder = os.path.join(os.path.dirname(__file__), "templates")
        self.app = Flask(__name__, template_folder=template_folder)
        self.app.config["TEMPLATES_AUTO_RELOAD"] = True
        self.app.jinja_env.auto_reload = True
        self._register_routes()

    def _register_routes(self):
        self.app.add_url_rule("/", endpoint="index", view_func=self._render_index)
        self.app.add_url_rule("/api/status", endpoint="status", view_func=self._status_json)
        self.app.add_url_rule(
            "/api/command",
            endpoint="command",
            view_func=self._run_command,
            methods=["POST"],
        )

    def _render_index(self):
        return render_template("index.html")

    def _status_json(self):
        if not self.status_provider:
            return jsonify({"success": False, "error": "Provider unavailable"}), 503
        try:
            return jsonify(self.status_provider())
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    def _run_command(self):
        payload = request.get_json(silent=True) or {}
        if not payload:
            return jsonify({"success": False, "error": "Missing JSON body"}), 400
        action = payload.get("action")
        if not action:
            return jsonify({"success": False, "error": "Missing action"}), 400
        if not self.command_handler:
            return jsonify({"success": False, "error": "Handler unavailable"}), 503
        try:
            result = self.command_handler(action, payload.get("data"))
            if isinstance(result, dict) and "error" in result:
                return jsonify({"success": False, "error": result["error"]}), 400
            return jsonify({"success": True, "result": result or {}})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    def start(self, host: str = "127.0.0.1", port: int = 5050):
        if self._server:
            raise RuntimeError("Web manager already running")
        self.host = host
        self.port = port
        self._server = make_server(self.host, self.port, self.app, threaded=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._server:
            return
        server = self._server
        self._server = None
        server.shutdown()
        server.server_close()
        if self._thread:
            self._thread.join(timeout=1)
        self._thread = None

    def is_running(self) -> bool:
        return self._server is not None

    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
