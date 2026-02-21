#!/usr/bin/env python3
"""Serve intake UI in a browser with local tool-call fallback."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.core.logging import configure_logging
from app.modules.mcp.server_main import _intake_html, handle_request
from app.queue.db import init_db


HOST = os.getenv("AURORA_INTAKE_UI_HOST", "127.0.0.1")
PORT = int(os.getenv("AURORA_INTAKE_UI_PORT", "8765"))


class IntakeHandler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._write_json(200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html", "/intake", "/intake.html"}:
            self._write_html(_intake_html())
            return
        if self.path == "/health":
            self._write_json(200, {"ok": True})
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/tools/call":
            self._write_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0
        raw = self.rfile.read(max(0, length)).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            self._write_json(400, {"error": "invalid_json"})
            return

        name = payload.get("name")
        arguments = payload.get("arguments") or {}
        if not isinstance(name, str) or not name.strip():
            self._write_json(400, {"error": "name is required"})
            return
        if not isinstance(arguments, dict):
            self._write_json(400, {"error": "arguments must be an object"})
            return

        try:
            result = handle_request(
                {
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            self._write_json(200, {"result": result})
        except Exception as exc:
            self._write_json(400, {"error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    configure_logging()
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), IntakeHandler)
    print(f"Aurora Intake UI server running at http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
