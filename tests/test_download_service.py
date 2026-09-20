import hashlib
import socket
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from desktop.app.services.download_service import download_original, sanitize_filename


PNG_BYTES = b"\x89PNG\r\n\x1a\nOneTime test image bytes"
JPEG_BYTES = b"\xff\xd8\xff\xe0OneTime test image bytes\xff\xd9"
IMAGE_BYTES = PNG_BYTES


class ImageRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/sample.png":
            content_disposition = None
            content_type = "image/png"
            image_bytes = PNG_BYTES
        elif self.path == "/sample.jpg":
            content_disposition = None
            content_type = "image/jpeg"
            image_bytes = JPEG_BYTES
        elif self.path == "/media/twitter-image?format=jpg":
            content_disposition = None
            content_type = "image/jpeg"
            image_bytes = JPEG_BYTES
        elif self.path == "/media/jpeg-image?format=jpeg":
            content_disposition = None
            content_type = "image/jpeg"
            image_bytes = JPEG_BYTES
        elif self.path == "/media/unknown-image?format=unknown":
            content_disposition = None
            content_type = "image/jpeg"
            image_bytes = JPEG_BYTES
        elif self.path in {"/media/no-format", "/media/"}:
            content_disposition = None
            content_type = "image/jpeg"
            image_bytes = JPEG_BYTES
        elif self.path in {"/download", "/download?format=jpg"}:
            content_disposition = 'attachment; filename="renamed-image.png"'
            content_type = "image/png"
            image_bytes = PNG_BYTES
        elif self.path == "/not-an-image":
            content_disposition = None
            content_type = "text/plain"
            image_bytes = b"not an image"
        else:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if content_disposition:
            self.send_header("Content-Disposition", content_disposition)
        self.send_header("Content-Length", str(len(image_bytes)))
        self.end_headers()
        self.wfile.write(image_bytes)

    def log_message(self, format, *args):
        return


@contextmanager
def image_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ImageRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_download_original_preserves_png_bytes_and_hash(tmp_path: Path):
    with image_server() as server_url:
        target = download_original(f"{server_url}/sample.png", tmp_path)

    assert target.parent == tmp_path
    assert target.name == "sample.png"
    assert target.read_bytes() == PNG_BYTES
    assert hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(PNG_BYTES).hexdigest()


def test_download_original_preserves_jpg_extension_and_bytes(tmp_path: Path):
    with image_server() as server_url:
        target = download_original(f"{server_url}/sample.jpg", tmp_path)

    assert target.name == "sample.jpg"
    assert target.read_bytes() == JPEG_BYTES
    assert hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(JPEG_BYTES).hexdigest()


def test_download_original_adds_jpg_from_format_query(tmp_path: Path):
    with image_server() as server_url:
        target = download_original(f"{server_url}/media/twitter-image?format=jpg", tmp_path)

    assert target.name == "twitter-image.jpg"
    assert target.read_bytes() == JPEG_BYTES
    assert hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(JPEG_BYTES).hexdigest()


def test_download_original_adds_jpeg_from_format_query(tmp_path: Path):
    with image_server() as server_url:
        target = download_original(f"{server_url}/media/jpeg-image?format=jpeg", tmp_path)

    assert target.name == "jpeg-image.jpeg"
    assert target.read_bytes() == JPEG_BYTES


def test_download_original_ignores_unknown_format_query(tmp_path: Path):
    with image_server() as server_url:
        target = download_original(f"{server_url}/media/unknown-image?format=unknown", tmp_path)

    assert target.name == "unknown-image.jpg"
    assert ".unknown" not in target.name
    assert target.read_bytes() == JPEG_BYTES


def test_download_original_prefers_content_disposition_filename(tmp_path: Path):
    with image_server() as server_url:
        target = download_original(f"{server_url}/download?format=jpg", tmp_path)

    assert target.parent == tmp_path
    assert target.name == "renamed-image.png"
    assert target.read_bytes() == PNG_BYTES


def test_download_original_uses_content_type_extension_fallback(tmp_path: Path):
    with image_server() as server_url:
        target = download_original(f"{server_url}/media/no-format", tmp_path)

    assert target.name == "no-format.jpg"
    assert target.read_bytes() == JPEG_BYTES


def test_download_original_rejects_non_image_content_type(tmp_path: Path):
    with image_server() as server_url:
        try:
            download_original(f"{server_url}/not-an-image", tmp_path)
        except ValueError as error:
            assert "text/plain" in str(error)
        else:
            raise AssertionError("non-image response should raise ValueError")


class FailureStatusRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/403":
            self.send_error(403)
        elif self.path == "/404":
            self.send_error(404)
        elif self.path == "/500":
            self.send_error(500)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        return


@contextmanager
def error_status_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FailureStatusRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class PartialImageRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", "64")
        self.end_headers()
        self.wfile.write(b"\x89PNG\r\n\x1a\n")
        self.wfile.flush()
        self.connection.shutdown(socket.SHUT_RDWR)

    def log_message(self, format, *args):
        return


@contextmanager
def partial_image_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), PartialImageRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class MissingFilenameRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        image_bytes = JPEG_BYTES
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(image_bytes)))
        self.end_headers()
        self.wfile.write(image_bytes)

    def log_message(self, format, *args):
        return


@contextmanager
def missing_filename_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MissingFilenameRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CON", "CON_"),
        ("CON.txt", "CON_.txt"),
        ("PRN.jpg", "PRN_.jpg"),
        ("NUL", "NUL_"),
        ("COM1", "COM1_"),
        ("LPT9.png", "LPT9_.png"),
        ("  name.. ", "name"),
        ("name<.png", "name_.png"),
        ("a/b\\c?.png", "a_b_c_.png"),
    ],
)
def test_sanitize_filename_handles_reserved_windows_names_and_trailing_noise(value, expected):
    assert sanitize_filename(value) == expected


@pytest.mark.parametrize(
    ("value", "expected_suffix"),
    [
        ("a" * 400 + ".png", ".png"),
        ("a" * 400, ""),
    ],
)
def test_sanitize_filename_truncates_overlong_names(value, expected_suffix):
    result = sanitize_filename(value)
    assert len(result) <= 255
    assert result.endswith(expected_suffix)


def test_download_original_does_not_leave_final_file_after_http_403(tmp_path: Path):
    with error_status_server() as server_url:
        target = tmp_path / "missing.jpg"
        with pytest.raises(Exception):
            download_original(f"{server_url}/403", tmp_path)
        assert not target.exists()
        assert list(tmp_path.iterdir()) == []


def test_download_original_does_not_leave_final_file_after_http_404(tmp_path: Path):
    with error_status_server() as server_url:
        target = tmp_path / "missing.jpg"
        with pytest.raises(Exception):
            download_original(f"{server_url}/404", tmp_path)
        assert not target.exists()
        assert list(tmp_path.iterdir()) == []


def test_download_original_does_not_leave_final_file_after_http_500(tmp_path: Path):
    with error_status_server() as server_url:
        target = tmp_path / "missing.jpg"
        with pytest.raises(Exception):
            download_original(f"{server_url}/500", tmp_path)
        assert not target.exists()
        assert list(tmp_path.iterdir()) == []


def test_download_original_removes_temporary_file_after_incomplete_transfer(tmp_path: Path):
    with partial_image_server() as server_url:
        with pytest.raises(Exception):
            download_original(f"{server_url}/partial.png", tmp_path)
        assert list(tmp_path.iterdir()) == []


def test_download_original_uses_missing_url_filename_when_no_name_is_present(tmp_path: Path):
    with missing_filename_server() as server_url:
        target = download_original(f"{server_url}/media/", tmp_path)
        assert target.name == "image.jpg"
        assert target.read_bytes() == JPEG_BYTES


def test_download_original_prefers_content_disposition_filename_over_url_name_even_when_sanitized(tmp_path: Path):
    with image_server() as server_url:
        target = download_original(f"{server_url}/download?format=jpg", tmp_path)
        assert target.name == "renamed-image.png"
        assert target.read_bytes() == PNG_BYTES


def test_download_original_handles_existing_filename_collisions_by_adding_numeric_suffix(tmp_path: Path):
    with image_server() as server_url:
        existing = tmp_path / "sample.png"
        existing.write_bytes(PNG_BYTES)

        target = download_original(f"{server_url}/sample.png", tmp_path)
        assert target.name == "sample (2).png"
        assert target.read_bytes() == PNG_BYTES