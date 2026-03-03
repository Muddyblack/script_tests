"""Ghost Typist — main window."""

import os
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow

from src.common.theme import ThemeManager, WebThemeBridge
from src.ghost_typist.bridge import GhostTypistBridge


class GhostTypistApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.mgr = ThemeManager()
        self.setWindowTitle("Ghost Typist")

        try:
            from src.common.config import ASSETS_DIR
            icon_path = os.path.join(ASSETS_DIR, "ghost_typist.png")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except ImportError:
            pass

        self.resize(900, 650)

        self.view = QWebEngineView()
        settings = self.view.settings()
        dev_attr = getattr(QWebEngineSettings.WebAttribute, "DeveloperExtrasEnabled", None)
        if dev_attr:
            settings.setAttribute(dev_attr, True)

        self.setCentralWidget(self.view)

        self.bridge = GhostTypistBridge()
        self.channel = QWebChannel(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # Live theme injection
        self._theme_bridge = WebThemeBridge(self.mgr, self.view)

        self.shortcut = QShortcut(QKeySequence("F12"), self)
        self.shortcut.activated.connect(self._open_devtools)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(script_dir, "ghost_typist.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

    def _open_devtools(self) -> None:
        self._devtools = QWebEngineView()
        self._devtools.setWindowTitle("Ghost Typist DevTools")
        self._devtools.resize(1000, 700)
        self.view.page().setDevToolsPage(self._devtools.page())
        self._devtools.show()

    def closeEvent(self, event):
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
