import hashlib
import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))

from app.windows.main_window import MainWindow
from test_download_service import IMAGE_BYTES, image_server


def test_image_tabs_message_reaches_mainwindow_and_downloads_exact_bytes(monkeypatch, tmp_path: Path):
    # Keep the test headless and non-interactive by removing UI modal popups from the test path.
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    with image_server() as server_url:
        image_url = f"{server_url}/sample.png"
        payload = {
            "type": "image_tabs",
            "version": 1,
            "browser": "opera",
            "request_id": "req-001",
            "tabs": [
                {"tab_id": 1, "title": "Image", "url": image_url},
            ],
        }

        window = MainWindow()
        window.native_message_received.connect(window.handle_native_message)
        window.native_message_received.emit(payload)

        assert window.urls == [image_url]
        assert window.list_widget.count() == 1
        assert window.list_widget.item(0).text() == image_url

        window.output_dir = str(tmp_path)
        window.download_button.click()

        deadline = 5000
        while deadline > 0:
            QCoreApplication.processEvents()
            QTest.qWait(10)
            deadline -= 10
            if any(tmp_path.glob("sample.png")):
                break

        downloaded = next(tmp_path.glob("sample.png"))
        assert downloaded.name == "sample.png"
        assert downloaded.read_bytes() == IMAGE_BYTES
        assert hashlib.sha256(downloaded.read_bytes()).hexdigest() == hashlib.sha256(IMAGE_BYTES).hexdigest()

        window.close()
        app.processEvents()
