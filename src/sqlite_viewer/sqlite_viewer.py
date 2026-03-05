"""SQLite Viewer — WebEngine-powered database browser."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication

from src.common.web_app_window import BaseWebApp
from src.sqlite_viewer.bridge import SqliteViewerBridge


class SqliteViewer(BaseWebApp):
    WINDOW_TITLE = "SQLite Viewer"
    ICON_NAME    = "sqlite_viewer"
    DEFAULT_SIZE = (1260, 800)
    MIN_SIZE     = (840, 560)

    def create_bridge(self) -> SqliteViewerBridge:
        return SqliteViewerBridge(self)

    def html_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "sqlite_viewer.html")

    def after_init(self) -> None:
        """Called by BaseWebApp after setup; install our drop handler."""
        # QWebEngineView needs setAcceptDrops(True) and can be intercepted via event filter.
        self.view.setAcceptDrops(True)
        self.view.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.view:
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.Drop:
                urls = event.mimeData().urls()
                if urls:
                    path = urls[0].toLocalFile()
                    if path and os.path.isfile(path):
                        # Use the bridge to open the database.
                        # Since open_db now emits db_opened, the JS listener will update the UI.
                        self.bridge.open_db(path)
                        return True
        return super().eventFilter(obj, event)


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
