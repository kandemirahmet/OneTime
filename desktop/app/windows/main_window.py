from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.download_service import download_original
from app.version import APP_VERSION


class DownloadWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(int, int, list)

    def __init__(self, urls: list[str], output_dir: Path) -> None:
        super().__init__()
        self.urls = list(urls)
        self.output_dir = output_dir.expanduser()

    @Slot()
    def run(self) -> None:
        successful = 0
        failed = 0
        results: list[tuple[str, bool, str | None, str | None]] = []
        total = len(self.urls)

        for index, url in enumerate(self.urls, start=1):
            try:
                saved_path = download_original(url, self.output_dir)
                successful += 1
                results.append((url, True, str(saved_path), None))
            except (OSError, ValueError, urllib.error.URLError) as exc:
                failed += 1
                results.append((url, False, None, str(exc)))

            self.progress.emit(index, total, url)

        self.finished.emit(successful, failed, results)


class MainWindow(QMainWindow):
    native_message_received = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            app.setApplicationName("OneTime")
            app.setApplicationVersion(APP_VERSION)

        self.setWindowTitle("OneTime")
        self.resize(760, 520)
        self.setMinimumSize(680, 460)

        self.urls: list[str] = []
        self.default_output_dir = Path.home() / "Downloads" / "OneTime"
        self.settings = QSettings("OneTime", "OneTime")
        self.is_downloading = False
        self._download_thread: QThread | None = None
        self._download_worker: DownloadWorker | None = None

        saved_output_dir = self.settings.value("output_dir", "", type=str)
        saved_path = Path(saved_output_dir).expanduser() if saved_output_dir else None
        if saved_path and saved_path.is_dir():
            self.output_dir = str(saved_path)
        else:
            self.output_dir = str(self.default_output_dir)

        central = QWidget()
        self.setCentralWidget(central)

        self.layout = QVBoxLayout(central)
        title = QLabel("OneTime")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.layout.addWidget(title)

        subtitle = QLabel("Collect image URLs from the current Opera/Chromium browser session.")
        self.layout.addWidget(subtitle)

        folder_label = QLabel("Output folder:")
        self.output_folder_label = QLabel()
        self.output_folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.output_folder_label.setWordWrap(True)
        self._update_output_folder_label()

        folder_buttons = QHBoxLayout()
        self.folder_button = QPushButton("Choose folder…")
        self.folder_button.clicked.connect(self.choose_folder)
        folder_buttons.addWidget(self.folder_button)

        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.clicked.connect(self.open_folder)
        folder_buttons.addWidget(self.open_folder_button)

        self.layout.addWidget(folder_label)
        self.layout.addWidget(self.output_folder_label)
        self.layout.addLayout(folder_buttons)

        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.start_downloads)
        self.layout.addWidget(self.download_button)

        self.progress_label = QLabel("Ready")
        self.layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

        self.list_widget = QListWidget()
        self.layout.addWidget(self.list_widget)

        self.status = QLabel("Ready")
        self.layout.addWidget(self.status)

        self._build_menu_bar()

    def _build_menu_bar(self) -> None:
        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About OneTime", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def show_about_dialog(self) -> None:
        message = (
            "OneTime\n\n"
            "Collect direct image URLs from the current Opera/Chromium session and download the original files.\n\n"
            f"Version: {APP_VERSION}"
        )
        QMessageBox.about(self, "About OneTime", message)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose OneTime destination folder", self.output_dir)
        if folder:
            self.output_dir = folder
            self.settings.setValue("output_dir", folder)
            self._update_output_folder_label()
            self.status.setText(f"Destination folder: {folder}")

    def _update_output_folder_label(self) -> None:
        self.output_folder_label.setText(self.output_dir)

    def _ensure_valid_output_dir(self) -> Path:
        output_dir = Path(self.output_dir).expanduser()
        if output_dir.is_dir():
            return output_dir

        output_dir = self.default_output_dir
        self.output_dir = str(output_dir)
        self.settings.setValue("output_dir", self.output_dir)
        self._update_output_folder_label()
        return output_dir

    def open_folder(self) -> None:
        output_dir = self._ensure_valid_output_dir()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(output_dir))
        except OSError as exc:
            QMessageBox.warning(self, "Open folder", f"The output folder could not be opened:\n{exc}")

    def _set_download_progress(self, current: int, total: int, url: str) -> None:
        if total <= 0:
            return

        display_name = Path(urllib.parse.urlparse(url).path).name or url
        percent = int((current / total) * 100)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.progress_bar.setVisible(True)
        self.progress_label.setText(f"Downloading {current} of {total}: {display_name}")
        self.status.setText(f"Downloading {current} of {total}")
        self.progress_bar.setFormat(f"{percent}%")

    def _reset_download_progress(self) -> None:
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Ready")
        self.status.setText("Ready")

    def _show_download_summary(self, successful: int, failed: int, results: list[tuple[str, bool, str | None, str | None]]) -> None:
        summary = f"Downloaded: {successful}\nFailed: {failed}"
        self.status.setText(summary)

        if failed:
            failure_details = [
                f"{url}: {error}"
                for url, ok, _, error in results
                if not ok and error
            ]
            message = summary + (f"\n\n{chr(10).join(failure_details[:10])}" if failure_details else "")
            QMessageBox.warning(self, "Download", message)
        else:
            QMessageBox.information(self, "Download", summary)

    def _on_download_progress(self, current: int, total: int, url: str) -> None:
        self._set_download_progress(current, total, url)

    def _on_download_finished(self, successful: int, failed: int, results: list[tuple[str, bool, str | None, str | None]]) -> None:
        self.is_downloading = False
        self.download_button.setEnabled(True)
        self.download_button.setText("Download")
        self._show_download_summary(successful, failed, results)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Ready")

        thread = self._download_thread
        worker = self._download_worker

        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(1000)

        if thread is not None:
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()

        self._download_thread = None
        self._download_worker = None

    def _cleanup_download_thread(self) -> None:
        if self._download_thread is not None and self._download_thread.isRunning():
            self._download_thread.quit()
            self._download_thread.wait(1000)

        thread = self._download_thread
        worker = self._download_worker
        if thread is not None:
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()

        self._download_thread = None
        self._download_worker = None

    def start_downloads(self) -> None:
        if self.is_downloading:
            return

        if not self.output_dir:
            QMessageBox.warning(self, "Download", "Choose a destination folder first.")
            return

        if not self.urls:
            QMessageBox.warning(self, "Download", "There are no image URLs to download.")
            return

        output_dir = Path(self.output_dir).expanduser()
        if not output_dir.exists() or not output_dir.is_dir():
            QMessageBox.warning(
                self,
                "Download",
                "The output folder is not available. Please choose a valid destination folder first.",
            )
            return

        if not os.access(output_dir, os.W_OK):
            QMessageBox.warning(self, "Download", f"The output folder is not writable:\n{output_dir}")
            return

        self.is_downloading = True
        self.download_button.setEnabled(False)
        self.download_button.setText("Downloading…")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, max(len(self.urls), 1))
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"Downloading 0 of {len(self.urls)}")
        self.status.setText(f"Downloading 0 of {len(self.urls)}")

        self._download_thread = QThread(self)
        self._download_worker = DownloadWorker(self.urls, output_dir)
        self._download_worker.moveToThread(self._download_thread)

        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_thread.finished.connect(self._cleanup_download_thread)

        self._download_thread.start()

    def add_urls(self, urls: list[str]) -> None:
        for url in urls:
            if url not in self.urls:
                self.urls.append(url)
                self.list_widget.addItem(url)
        self.status.setText(f"Received {len(self.urls)} image URL(s)")

    def handle_native_message(self, payload: dict) -> None:
        if payload.get("type") != "image_tabs":
            return
        tabs = payload.get("tabs", [])
        urls = [tab.get("url") for tab in tabs if isinstance(tab, dict) and tab.get("url")]
        self.add_urls(urls)

    def closeEvent(self, event):
        if self._download_thread is not None and self._download_thread.isRunning():
            self._download_thread.quit()
            self._download_thread.wait(1000)
        super().closeEvent(event)
