"""Ghost Typist — main window."""

import os
import sys

from PyQt6.QtWidgets import QApplication

from src.common.web_app_window import BaseWebApp
from src.ghost_typist.bridge import GhostTypistBridge


class GhostTypistApp(BaseWebApp):
    WINDOW_TITLE = "Ghost Typist"
    ICON_NAME = "ghost_typist"
    DEFAULT_SIZE = (900, 650)
    WEB_ATTRS = ("DeveloperExtrasEnabled",)

    def create_bridge(self) -> GhostTypistBridge:
        return GhostTypistBridge()

    def html_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ghost_typist.html")

    def closeEvent(self, event) -> None:
        # Just hide; keep watcher alive
        event.ignore()
        self.hide()


def launch() -> "GhostTypistApp":
    """Create and show the window (for embedding inside nexus; QApplication must exist)."""
    from src.ghost_typist.db import init_db
    init_db()
    win = GhostTypistApp()
    win.show()
    return win


def main() -> None:
    """Standalone entry point — creates its own QApplication."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.ghost_typist")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    from src.ghost_typist.db import init_db
    init_db()
    win = GhostTypistApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
