import json
import os
import threading
from typing import Callable, Optional

from flask import Flask, jsonify, render_template, request
from werkzeug.serving import make_server

try:
    from flask_sock import Sock
except Exception:
    Sock = None

from .realtime import RealtimeHub


class WebManagerServer:
    def __init__(
        self,
        status_provider: Optional[Callable[[], dict]] = None,
        command_handler: Optional[Callable[[str, dict], dict]] = None,
        macros_provider: Optional[Callable[[], list]] = None,
        macro_creator: Optional[Callable[[dict], dict]] = None,
    ):
        self.status_provider = status_provider
        self.command_handler = command_handler
        self.macros_provider = macros_provider
        self.macro_creator = macro_creator
        self.host = "127.0.0.1"
        self.port = 5050
        self._server = None
        self._thread = None
        template_folder = os.path.join(os.path.dirname(__file__), "templates")
        self.app = Flask(__name__, template_folder=template_folder)
        self.app.config["TEMPLATES_AUTO_RELOAD"] = True
        self.app.jinja_env.auto_reload = True
        self._sock = Sock(self.app) if Sock else None
        self._realtime = RealtimeHub()
        self._register_routes()
        self._register_ws_routes()

    def _register_routes(self):
        self.app.add_url_rule("/", endpoint="index", view_func=self._render_index)
        self.app.add_url_rule("/api/status", endpoint="status", view_func=self._status_json)
        self.app.add_url_rule(
            "/api/command",
            endpoint="command",
            view_func=self._run_command,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/macros",
            endpoint="macros",
            view_func=self._macros_handler,
            methods=["GET", "POST"],
        )

    def _register_ws_routes(self):
        if not self._sock:
            return
        self._sock.route("/ws")(self._ws_handler)

    @staticmethod
    def _normalize_macros_payload(payload):
        macros = []
        presets = []
        variables = []
        if isinstance(payload, dict):
            macros = payload.get("macros") or []
            presets = payload.get("presets") or []
            variables = payload.get("variables") or []
        elif isinstance(payload, list):
            macros = payload
        return macros or [], presets or [], variables or []

    def _render_index(self):
        return render_template("index.html")

    def _build_status_payload(self):
        if not self.status_provider:
            return {"success": False, "error": "Provider unavailable"}
        try:
            return self.status_provider()
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _status_json(self):
        if not self.status_provider:
            return jsonify({"success": False, "error": "Provider unavailable"}), 503
        try:
            return jsonify(self.status_provider())
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    def _ws_handler(self, ws):
        self._realtime.register(ws)
        try:
            self._send_ws_status(ws)
            while True:
                message = ws.receive()
                if message is None:
                    break
                self._handle_ws_message(ws, message)
        finally:
            self._realtime.unregister(ws)

    def _handle_ws_message(self, ws, message: str) -> None:
        try:
            payload = json.loads(message or "{}")
        except Exception:
            return
        msg_type = str(payload.get("type") or "")
        if msg_type == "status_request":
            self._send_ws_status(ws)
        elif msg_type == "ping":
            self._realtime.send(ws, {"type": "pong"})

    def _send_ws_status(self, ws) -> None:
        payload = self._build_status_payload()
        self._realtime.send(ws, {"type": "status", "payload": payload})

    def push_status(self, payload: Optional[dict] = None) -> None:
        if not self._sock:
            return
        snapshot = payload if payload is not None else self._build_status_payload()
        self._realtime.broadcast({"type": "status", "payload": snapshot})

    def push_logs(self, lines) -> None:
        if not self._sock:
            return
        self._realtime.broadcast_logs(lines)

    def _macros_handler(self):
        if request.method == "GET":
            if not self.macros_provider:
                return jsonify({"success": False, "error": "Macro provider unavailable"}), 503
            try:
                payload = self.macros_provider()
                macros, presets, variables = self._normalize_macros_payload(payload)
                return jsonify({"macros": macros, "presets": presets, "variables": variables})
            except Exception as exc:
                return jsonify({"success": False, "error": str(exc)}), 500

        if request.method == "POST":
            if not self.macro_creator:
                return jsonify({"success": False, "error": "Macro creator unavailable"}), 503
            payload = request.get_json(silent=True) or {}
            if not payload:
                return jsonify({"success": False, "error": "Missing macro payload"}), 400
            try:
                new_macro = self.macro_creator(payload)
                if isinstance(new_macro, dict) and new_macro.get("error"):
                    return jsonify({"success": False, "error": new_macro["error"]}), 400
                macros_payload = self.macros_provider() if self.macros_provider else []
                macros, presets, variables = self._normalize_macros_payload(macros_payload)
                return jsonify({"success": True, "macro": new_macro, "macros": macros, "presets": presets, "variables": variables})
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
