from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.services.ipc_adapter import LocalHttpIpcAdapter
from app.version import APP_VERSION
from app.windows.main_window import MainWindow


def application_icon_path() -> Path:
    """Return the bundled icon path, or the project icon during development."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "OneTime.ico"
    return Path(__file__).resolve().parents[2] / "OneTime.ico"


class OneTimeSingleInstanceGuard:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateMutexW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    _kernel32.ReleaseMutex.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 0x00000102
    _mutex_name = "Global\\OneTime_SingleInstance"

    def __init__(self) -> None:
        self._mutex = self._kernel32.CreateMutexW(None, False, self._mutex_name)
        if not self._mutex:
            raise OSError(ctypes.get_last_error())
        self._owned = False

    def try_lock(self) -> bool:
        if self._mutex is None:
            return False
        wait_result = self._kernel32.WaitForSingleObject(self._mutex, 0)
        if wait_result == self._WAIT_OBJECT_0:
            self._owned = True
            return True
        return False

    def release(self) -> None:
        if self._mutex is not None and self._owned:
            self._kernel32.ReleaseMutex(self._mutex)
            self._owned = False

    def __del__(self) -> None:
        try:
            if self._mutex is not None:
                if self._owned:
                    self.release()
                self._kernel32.CloseHandle(self._mutex)
        except Exception:
            pass
        self._mutex = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("OneTime")
    app.setApplicationVersion(APP_VERSION)
    app_icon = QIcon(str(application_icon_path()))
    app.setWindowIcon(app_icon)
    single_instance = OneTimeSingleInstanceGuard()
    if not single_instance.try_lock():
        QMessageBox.critical(None, "OneTime", "OneTime is already running.")
        sys.exit(0)

    window = MainWindow()
    window.setWindowIcon(app_icon)
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
