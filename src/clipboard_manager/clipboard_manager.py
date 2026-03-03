"""Clipboard Manager — WebEngine-powered viewer/editor of persistent clipboard history.

The actual clipboard capture runs 24/7 via ClipboardWatcher in Nexus.
This window is a pure React/web UI backed by ClipboardBridge over QWebChannel.
"""

import os
import sys

from PyQt6.QtWidgets import QApplication

from src.clipboard_manager.bridge import ClipboardBridge
from src.common.web_app_window import BaseWebApp


class ClipboardManager(BaseWebApp):
    """Clipboard history viewer powered by a web UI."""

    WINDOW_TITLE = "Clipboard Manager"
    ICON_NAME = "clipboard_manager"
    DEFAULT_SIZE = (1100, 700)
    MIN_SIZE = (740, 480)

    def create_bridge(self) -> ClipboardBridge:
        return ClipboardBridge(self)

    def html_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "clipboard_manager.html")

    def closeEvent(self, event) -> None:
        self.bridge.close()
        super().closeEvent(event)


def main() -> None:
    from PyQt6.QtCore import Qt
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.clipboard_manager")

    app = QApplication.instance() or QApplication(sys.argv)

    # When run standalone (not inside Nexus) spin up a local watcher
    from src.clipboard_manager.watcher import ClipboardWatcher, get_watcher
    if get_watcher() is None:
        _watcher = ClipboardWatcher(app)  # noqa: F841 — keep alive

    win = ClipboardManager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
