"""SQLite Viewer — WebEngine-powered database browser."""

from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import QApplication

from src.common.web_app_window import BaseWebApp
from src.sqlite_viewer.bridge import SqliteViewerBridge

_DIR = os.path.dirname(os.path.abspath(__file__))


class SqliteViewer(BaseWebApp):
    WINDOW_TITLE = "SQLite Viewer"
    ICON_NAME    = "sqlite_viewer"
    DEFAULT_SIZE = (1260, 800)
    MIN_SIZE     = (840, 560)

    def create_bridge(self) -> SqliteViewerBridge:
        return SqliteViewerBridge(self)

    def html_path(self) -> str:
        return os.path.join(_DIR, "sqlite_viewer.html")


def launch() -> SqliteViewer:
    win = SqliteViewer()
    win.show()
    return win


def main() -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.sqlite_viewer")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = SqliteViewer()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
