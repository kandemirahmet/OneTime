import json
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.version import APP_VERSION
from app.windows.main_window import MainWindow


@pytest.fixture
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def isolated_settings(tmp_path: Path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    settings = QSettings("OneTime", "OneTime")
    settings.clear()
    settings.sync()
    yield settings
    settings.clear()
    settings.sync()


def wait_for(predicate, timeout_ms: int = 2000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        QTest.qWait(10)
    return bool(predicate())


def test_version_constant_is_1_0_0():
    assert APP_VERSION == "1.0.0"


def test_qt_metadata_uses_app_version(qt_app):
    app = QApplication.instance()
    assert app is not None
    assert app.applicationName() == "OneTime"
    assert app.applicationVersion() == APP_VERSION


def test_about_dialog_shows_version(qt_app, monkeypatch):
    captured = {}
    monkeypatch.setattr(QMessageBox, "about", lambda parent, title, text: captured.update({"parent": parent, "title": title, "text": text}))

    window = MainWindow()
    window.show_about_dialog()

    assert captured["title"] == "About OneTime"
    assert "1.0.0" in captured["text"]
    window.close()


def test_extension_manifest_version_is_1_0_0():
    manifest_path = Path(__file__).resolve().parent.parent / "extension" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0"


def test_no_saved_setting_uses_default_folder(qt_app, isolated_settings):
    window = MainWindow()

    assert window.output_dir == str(Path.home() / "Downloads" / "OneTime")
    assert window.output_folder_label.text() == window.output_dir

    window.close()


def test_existing_saved_folder_is_restored(qt_app, isolated_settings, tmp_path: Path):
    saved_folder = tmp_path / "saved"
    saved_folder.mkdir()
    isolated_settings.setValue("output_dir", str(saved_folder))
    isolated_settings.sync()

    window = MainWindow()

    assert window.output_dir == str(saved_folder)
    assert window.output_folder_label.text() == str(saved_folder)

    window.close()


def test_missing_saved_folder_uses_default_folder(qt_app, isolated_settings, tmp_path: Path):
    isolated_settings.setValue("output_dir", str(tmp_path / "deleted"))
    isolated_settings.sync()

    window = MainWindow()

    assert window.output_dir == str(Path.home() / "Downloads" / "OneTime")

    window.close()


def test_choose_folder_updates_display_and_saves_setting(
    qt_app, isolated_settings, monkeypatch, tmp_path: Path
):
    selected_folder = tmp_path / "selected"
    selected_folder.mkdir()
    monkeypatch.setattr(
        "app.windows.main_window.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(selected_folder),
    )
    window = MainWindow()

    window.choose_folder()

    assert window.output_dir == str(selected_folder)
    assert window.output_folder_label.text() == str(selected_folder)
    assert isolated_settings.value("output_dir", type=str) == str(selected_folder)

    window.close()


def test_open_folder_opens_existing_custom_folder(qt_app, isolated_settings, monkeypatch, tmp_path: Path):
    output_folder = tmp_path / "existing-output"
    output_folder.mkdir()
    isolated_settings.setValue("output_dir", str(output_folder))
    isolated_settings.sync()
    opened_paths = []
    monkeypatch.setattr(os, "startfile", opened_paths.append, raising=False)
    window = MainWindow()

    window.open_folder()

    assert output_folder.is_dir()
    assert opened_paths == [str(output_folder)]

    window.close()


def test_open_folder_falls_back_to_default_when_saved_folder_was_deleted(
    qt_app, isolated_settings, monkeypatch, tmp_path: Path
):
    deleted_folder = tmp_path / "deleted-output"
    default_folder = tmp_path / "default-output"
    opened_paths = []
    monkeypatch.setattr(os, "startfile", opened_paths.append, raising=False)
    window = MainWindow()
    window.default_output_dir = default_folder
    window.output_dir = str(deleted_folder)
    window.settings.setValue("output_dir", str(deleted_folder))
    window.settings.sync()

    window.open_folder()

    assert not deleted_folder.exists()
    assert default_folder.is_dir()
    assert window.output_dir == str(default_folder)
    assert window.output_folder_label.text() == str(default_folder)
    assert window.settings.value("output_dir", type=str) == str(default_folder)
    assert opened_paths == [str(default_folder)]

    window.close()


def test_open_folder_creates_missing_default_folder(qt_app, isolated_settings, monkeypatch, tmp_path: Path):
    default_folder = tmp_path / "default-output"
    opened_paths = []
    monkeypatch.setattr(os, "startfile", opened_paths.append, raising=False)
    window = MainWindow()
    window.default_output_dir = default_folder
    window.output_dir = str(default_folder)

    window.open_folder()

    assert default_folder.is_dir()
    assert opened_paths == [str(default_folder)]

    window.close()


def test_open_folder_failure_shows_warning(qt_app, isolated_settings, monkeypatch, tmp_path: Path):
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    warning_messages = []
    monkeypatch.setattr(os, "startfile", lambda path: (_ for _ in ()).throw(OSError("Explorer failed")), raising=False)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warning_messages.append(args),
    )
    window = MainWindow()
    window.output_dir = str(output_folder)

    window.open_folder()

    assert warning_messages
    assert warning_messages[0][1] == "Open folder"
    assert "Explorer failed" in warning_messages[0][2]

    window.close()


def test_download_button_is_disabled_while_batch_runs_and_reenabled_after_success(
    qt_app, isolated_settings, monkeypatch, tmp_path: Path
):
    def fake_download(url: str, output_dir: Path):
        target = Path(output_dir) / Path(url).name
        target.write_bytes(b"ok")
        return target

    monkeypatch.setattr("app.windows.main_window.download_original", fake_download)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    window = MainWindow()
    window.urls = ["https://example.com/one.png", "https://example.com/two.png"]
    window.output_dir = str(tmp_path)

    window.download_button.click()

    assert window.is_downloading is True
    assert window.download_button.isEnabled() is False
    assert wait_for(lambda: window.download_button.isEnabled() and not window.is_downloading)
    assert window.status.text().startswith("Downloaded: 2")
    assert (tmp_path / "one.png").exists()
    assert (tmp_path / "two.png").exists()

    window.close()


def test_second_download_click_does_not_start_another_batch(qt_app, isolated_settings, tmp_path: Path):
    window = MainWindow()
    window.urls = ["https://example.com/image.png"]
    window.output_dir = str(tmp_path)
    window.is_downloading = True
    window.download_button.setEnabled(False)
    previous_thread = window._download_thread

    window.start_downloads()

    assert window.is_downloading is True
    assert window._download_thread is previous_thread
    assert window.download_button.isEnabled() is False

    window.close()


def test_failed_download_does_not_abort_later_urls(qt_app, isolated_settings, monkeypatch, tmp_path: Path):
    calls = []

    def fake_download(url: str, output_dir: Path):
        calls.append(url)
        path = Path(url).name
        if "bad" in url:
            raise ValueError("bad image")
        target = Path(output_dir) / path
        target.write_bytes(b"ok")
        return target

    monkeypatch.setattr("app.windows.main_window.download_original", fake_download)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    window = MainWindow()
    window.urls = ["https://example.com/bad.png", "https://example.com/good.png"]
    window.output_dir = str(tmp_path)

    window.download_button.click()
    assert wait_for(lambda: not window.is_downloading)
    assert calls == ["https://example.com/bad.png", "https://example.com/good.png"]
    assert (tmp_path / "good.png").exists()
    assert "Downloaded: 1" in window.status.text()
    assert "Failed: 1" in window.status.text()

    window.close()


def test_empty_url_list_and_invalid_output_dir_show_user_messages(qt_app, isolated_settings, monkeypatch, tmp_path: Path):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))
    window = MainWindow()

    window.urls = []
    window.start_downloads()
    assert warnings and warnings[0][1] == "Download"
    assert "There are no image URLs" in warnings[0][2]

    warnings.clear()
    window.urls = ["https://example.com/image.png"]
    window.output_dir = str(tmp_path / "missing")
    window.start_downloads()
    assert warnings and warnings[0][1] == "Download"
    assert "output folder is not available" in warnings[0][2].lower()

    window.close()


def test_download_worker_thread_cleanup_happens_after_completion(qt_app, isolated_settings, monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.windows.main_window.download_original", lambda url, output_dir: Path(output_dir) / Path(url).name)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    window = MainWindow()
    window.urls = ["https://example.com/cleanup.png"]
    window.output_dir = str(tmp_path)

    window.start_downloads()
    assert wait_for(lambda: not window.is_downloading)
    assert window._download_thread is None
    assert window._download_worker is None
    assert window.download_button.isEnabled() is True

    window.close()
