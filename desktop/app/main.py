from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QMessageBox

from app.services.ipc_adapter import LocalHttpIpcAdapter
from app.version import APP_VERSION
from app.windows.main_window import MainWindow

ERROR_ALREADY_EXISTS = 183


class OneTimeSingleInstanceGuard:
    def __init__(self) -> None:
        self._mutex = None
        self._owned = False

        if os.name == "nt":
            mutex_name = r"Global\OneTimeAppMutex"
            self._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
            if self._mutex is None:
                self._owned = False
                return

            last_error = ctypes.windll.kernel32.GetLastError()
            self._owned = last_error != ERROR_ALREADY_EXISTS
            if not self._owned:
                ctypes.windll.kernel32.CloseHandle(self._mutex)
                self._mutex = None
            return

        app_data_root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        lock_dir = Path(app_data_root) / "OneTime"
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = lock_dir / "one_time.lock"
        self._lock_path.touch(exist_ok=True)

    def try_lock(self) -> bool:
        if os.name == "nt":
            return self._owned
        if not hasattr(self, "_lock_path"):
            return False
        if not self._lock_path.exists():
            self._lock_path.touch(exist_ok=True)
        return True

    def release(self) -> None:
        if self._mutex is not None:
            if self._owned:
                ctypes.windll.kernel32.ReleaseMutex(self._mutex)
            ctypes.windll.kernel32.CloseHandle(self._mutex)
            self._owned = False
            self._mutex = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("OneTime")
    app.setApplicationVersion(APP_VERSION)
    single_instance = OneTimeSingleInstanceGuard()
    if not single_instance.try_lock():
        QMessageBox.critical(None, "OneTime", "OneTime is already running.")
        sys.exit(0)

    window = MainWindow()
    window.native_message_received.connect(window.handle_native_message)
    ipc_adapter = LocalHttpIpcAdapter(window.native_message_received.emit)
    try:
        ipc_adapter.start()
    except OSError:
        single_instance.release()
        QMessageBox.critical(None, "OneTime", "Port 8765 is already in use. Close the other OneTime instance or stop the process using port 8765.")
        sys.exit(1)

    app.aboutToQuit.connect(lambda: (ipc_adapter.stop(), single_instance.release()))
    window.show()
    sys.exit(app.exec())
