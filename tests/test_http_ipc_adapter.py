import json
import os
import subprocess
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))

import app.main as app_main
from app.main import OneTimeSingleInstanceGuard
from app.services.ipc_adapter import ALLOWED_ORIGIN, LocalHttpIpcAdapter, is_valid_browser_extension_origin


def request(port: int, method: str, path: str, payload: object | None = None, origin: str = ALLOWED_ORIGIN):
    data = None
    headers = {"Origin": origin}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def valid_payload() -> dict:
    return {
        "type": "image_tabs",
        "version": 1,
        "browser": "opera",
        "request_id": "req-http-001",
        "tabs": [{"tab_id": 1, "title": "Image", "url": "https://example.com/image.png"}],
    }


def test_browser_extension_origin_parser_accepts_valid_chrome_and_opera_origins():
    assert is_valid_browser_extension_origin("chrome-extension://abcdefgh")
    assert is_valid_browser_extension_origin("opera-extension://abcd1234")


def test_browser_extension_origin_parser_rejects_invalid_or_non_extension_origins():
    assert not is_valid_browser_extension_origin("")
    assert not is_valid_browser_extension_origin("chrome-extension://")
    assert not is_valid_browser_extension_origin("chrome-extension:///")
    assert not is_valid_browser_extension_origin("http://example.com")
    assert not is_valid_browser_extension_origin("https://example.com")
    assert not is_valid_browser_extension_origin("chrome-extension://abc/")


def running_adapter(callback):
    adapter = LocalHttpIpcAdapter(callback, port=0)
    adapter.start()
    return adapter


def test_valid_post_acknowledges_and_emits_payload():
    received = []
    adapter = running_adapter(received.append)
    try:
        status, headers, body = request(adapter.port, "POST", "/image-tabs", valid_payload())
        assert status == 200
        assert headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
        assert json.loads(body) == {
            "ok": True,
            "type": "image_tabs",
            "version": 1,
            "browser": "opera",
            "request_id": "req-http-001",
            "received_count": 1,
        }
        assert received == [valid_payload()]
    finally:
        adapter.stop()


def test_malformed_json_returns_bad_request():
    received = []
    adapter = running_adapter(received.append)
    try:
        request_data = urllib.request.Request(
            f"http://127.0.0.1:{adapter.port}/image-tabs",
            data=b"{not-json",
            headers={"Content-Type": "application/json", "Origin": ALLOWED_ORIGIN},
            method="POST",
        )
        try:
            urllib.request.urlopen(request_data, timeout=2)
        except urllib.error.HTTPError as error:
            assert error.code == 400
        assert received == []
    finally:
        adapter.stop()


def test_invalid_payload_returns_bad_request():
    received = []
    adapter = running_adapter(received.append)
    try:
        status, _, _ = request(adapter.port, "POST", "/image-tabs", {"type": "wrong"})
        assert status == 400
        assert received == []
    finally:
        adapter.stop()


def test_wrong_path_and_method_are_rejected():
    adapter = running_adapter(lambda payload: None)
    try:
        path_status, _, _ = request(adapter.port, "POST", "/wrong", valid_payload())
        method_status, _, _ = request(adapter.port, "GET", "/image-tabs")
        assert path_status == 404
        assert method_status == 405
    finally:
        adapter.stop()


def test_options_returns_cors_headers():
    adapter = running_adapter(lambda payload: None)
    try:
        status, headers, _ = request(adapter.port, "OPTIONS", "/image-tabs")
        assert status == 204
        assert headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
        assert headers["Access-Control-Allow-Methods"] == "POST, OPTIONS"
        assert headers["Access-Control-Allow-Headers"] == "Content-Type"
    finally:
        adapter.stop()


def test_trailing_slash_origin_is_rejected():
    adapter = running_adapter(lambda payload: None)
    try:
        status, _, body = request(
            adapter.port,
            "POST",
            "/image-tabs",
            valid_payload(),
            ALLOWED_ORIGIN + "/",
        )
        assert status == 403
        assert json.loads(body)["error"] == "origin_not_allowed"
    finally:
        adapter.stop()


def test_origin_is_returned_verbatim_on_acceptance():
    adapter = running_adapter(lambda payload: None)
    try:
        origin = "opera-extension://abcdef"
        status, headers, body = request(adapter.port, "POST", "/image-tabs", valid_payload(), origin)
        assert status == 200
        assert headers["Access-Control-Allow-Origin"] == origin
        assert json.loads(body)["ok"] is True
    finally:
        adapter.stop()


def test_wrong_origin_is_rejected():
    adapter = running_adapter(lambda payload: None)
    try:
        status, _, body = request(adapter.port, "POST", "/image-tabs", valid_payload(), "https://example.com")
        assert status == 403
        assert json.loads(body)["error"] == "origin_not_allowed"
    finally:
        adapter.stop()


def test_stop_releases_port():
    adapter = running_adapter(lambda payload: None)
    port = adapter.port
    adapter.stop()
    replacement = LocalHttpIpcAdapter(lambda payload: None, port=port)
    replacement.start()
    replacement.stop()


def test_windows_mutex_is_acquired_and_released_cleanly():
    guard = OneTimeSingleInstanceGuard()
    assert guard.try_lock() is True
    guard.release()
    assert guard.try_lock() is True
    guard.release()


def test_single_instance_guard_rejects_second_instance():
    first_guard = OneTimeSingleInstanceGuard()
    assert first_guard.try_lock() is True

    repo_root = Path(__file__).resolve().parent.parent
    script = """
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(r'REPO_ROOT') / 'desktop'))
from app.main import OneTimeSingleInstanceGuard

guard = OneTimeSingleInstanceGuard()
print(guard.try_lock())
""".replace("REPO_ROOT", str(repo_root))

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "desktop") + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, cwd=str(repo_root))

    assert completed.returncode == 0
    assert completed.stdout.strip() == "False"

    first_guard.release()