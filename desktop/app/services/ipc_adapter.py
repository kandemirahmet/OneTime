from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Callable


LOCALHOST = "127.0.0.1"
HTTP_PORT = 8765
IMAGE_TABS_PATH = "/image-tabs"
ALLOWED_ORIGIN = "chrome-extension://example"
BROWSER_EXTENSION_SCHEMES = {"chrome-extension", "opera-extension"}


def is_valid_browser_extension_origin(origin: str | None) -> bool:
    if not isinstance(origin, str):
        return False
    if not origin:
        return False
    if origin.endswith("/"):
        return False

    parsed = urllib.parse.urlsplit(origin)
    if parsed.scheme.lower() not in BROWSER_EXTENSION_SCHEMES:
        return False
    if not parsed.netloc:
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.path not in ("",):
        return False
    if parsed.query or parsed.fragment:
        return False
    return True


@dataclass
class NativeMessage:
    type: str
    version: int
    browser: str
    request_id: str
    tabs: list[dict]


def _validate_image_tabs_payload(payload: object) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "payload must be a JSON object"
    if payload.get("type") != "image_tabs":
        return False, "unsupported message type"
    if payload.get("version") != 1:
        return False, "unsupported version"
    if payload.get("browser") not in {"opera", "chromium"}:
        return False, "unsupported browser"
    if not isinstance(payload.get("request_id"), str):
        return False, "request_id must be a string"
    if not isinstance(payload.get("tabs"), list):
        return False, "tabs must be a list"
    for tab in payload["tabs"]:
        if not isinstance(tab, dict) or not isinstance(tab.get("url"), str):
            return False, "tabs must contain objects with string urls"
    return True, None


class _LocalHttpRequestHandler(BaseHTTPRequestHandler):
    server: "_LocalHttpServer"

    def _origin_from_request(self) -> str | None:
        return self.headers.get("Origin")

    def _set_cors_headers(self, origin: str) -> None:
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, payload: dict, origin: str | None = None) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if origin is not None:
            self._set_cors_headers(origin)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:
        if self.path != IMAGE_TABS_PATH:
            self.send_error(404)
            return
        origin = self._origin_from_request()
        if not is_valid_browser_extension_origin(origin):
            self.send_error(403)
            return
        self.send_response(204)
        self._set_cors_headers(origin)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != IMAGE_TABS_PATH:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(content_length)
            except ValueError:
                pass
            self.send_error(404)
            return

        origin = self._origin_from_request()
        if not is_valid_browser_extension_origin(origin):
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(content_length)
            except ValueError:
                pass
            self._send_json(403, {"ok": False, "error": "origin_not_allowed"})
            return

        if self.headers.get_content_type() != "application/json":
            self._send_json(400, {"ok": False, "error": "content_type_must_be_application_json"}, origin)
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid_json"}, origin)
            return

        valid, error = _validate_image_tabs_payload(payload)
        if not valid:
            self._send_json(400, {"ok": False, "error": error}, origin)
            return

        self.server.on_message(payload)
        self._send_json(
            200,
            {
                "ok": True,
                "type": payload["type"],
                "version": payload["version"],
                "browser": payload["browser"],
                "request_id": payload["request_id"],
                "received_count": len(payload["tabs"]),
            },
            origin,
        )

    def do_GET(self) -> None:
        self.send_error(405)

    def log_message(self, format: str, *args: object) -> None:
        return


class _LocalHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, on_message: Callable[[dict], None]):
        super().__init__((LOCALHOST, port), _LocalHttpRequestHandler)
        self.on_message = on_message


class LocalHttpIpcAdapter:
    def __init__(self, on_message: Callable[[dict], None], port: int = HTTP_PORT):
        self._on_message = on_message
        self._port = port
        self._server: _LocalHttpServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._server.server_port if self._server else self._port

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        try:
            self._server = _LocalHttpServer(self._port, self._on_message)
        except OSError:
            self._server = None
            raise

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        try:
            self._thread.start()
        except Exception:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
            raise

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None


class NamedPipeIpcAdapter:
    """IPC adapter interface for the desktop app.

    The adapter hides the preferred Windows named-pipe backend behind a simple service interface.
    The current scaffold intentionally holds the local receive contract in one place so the
    concrete transport can be replaced later by a pure Windows pipe or socket backend.
    """

    def __init__(self, on_message: Callable[[dict], None], pipe_path: str | None = None):
        self._on_message = on_message
        self._stop = threading.Event()
        self._thread = None
        self.pipe_path = pipe_path or os.path.expanduser(r"~\AppData\Local\OneTime\one_time_pipe.sock")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # Placeholder for the first Windows named-pipe implementation.
        # The service is intentionally kept in the adapter interface so a future real named pipe
        # can replace the current file/socket simulation without changing the UI.
        # No inbox.json bridge is used here.
        while not self._stop.is_set():
            try:
                if os.path.exists(self.pipe_path):
                    with open(self.pipe_path, "r", encoding="utf-8") as fp:
                        payload = json.load(fp)
                    if payload.get("type") == "image_tabs":
                        self._on_message(payload)
                    os.remove(self.pipe_path)
                time.sleep(0.2)
            except Exception:
                time.sleep(0.2)
