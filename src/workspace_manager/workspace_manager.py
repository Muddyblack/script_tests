"""Workspace Manager — WebEngine-powered workspace launcher."""

import os
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow

try:
    from src.common.config import WORKSPACE_MANAGER_ICON_PATH
except ImportError:
    WORKSPACE_MANAGER_ICON_PATH = ""

from src.common.theme import ThemeManager, WebThemeBridge
from src.workspace_manager.bridge import WorkspaceBridge


class WorkspaceManager(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.mgr = ThemeManager()
        self.setWindowTitle("Workspace Manager")
        try:
            if os.path.exists(WORKSPACE_MANAGER_ICON_PATH):
                self.setWindowIcon(QIcon(WORKSPACE_MANAGER_ICON_PATH))
        except Exception:
            pass
        self.resize(880, 640)
        self.setMinimumSize(640, 480)

        self.view = QWebEngineView()
        settings = self.view.settings()
        for attr_name in (
            "DeveloperExtrasEnabled",
            "LocalContentCanAccessFileUrls",
            "LocalContentCanAccessRemoteUrls",
        ):
            attr = getattr(QWebEngineSettings.WebAttribute, attr_name, None)
            if attr:
                settings.setAttribute(attr, True)
        self.setCentralWidget(self.view)

        self.bridge = WorkspaceBridge(self)
        self.channel = QWebChannel(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self._theme_bridge = WebThemeBridge(self.mgr, self.view)

        self.shortcut_devtools = QShortcut(QKeySequence("F12"), self)
        self.shortcut_devtools.activated.connect(self._open_devtools)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(script_dir, "workspace_manager.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

    def _open_devtools(self) -> None:
        self._devtools = QWebEngineView()
        self._devtools.setWindowTitle("Workspace Manager DevTools")
        self._devtools.resize(1100, 750)
        self.view.page().setDevToolsPage(self._devtools.page())
        self._devtools.show()


def launch() -> "WorkspaceManager":
    """Create and show the window (for embedding inside nexus)."""
    win = WorkspaceManager()
    win.show()
    return win


def main() -> None:
    """Standalone entry point."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "nexus.workspace_manager"
        )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = WorkspaceManager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
