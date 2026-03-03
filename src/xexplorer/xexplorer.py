"""XExplorer — WebEngine-powered file explorer main window."""

import os
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow

from src.common.config import ASSETS_DIR
from src.common.theme import ThemeManager, WebThemeBridge
from src.xexplorer.bridge import XExplorerBridge

# Keep references so windows aren’t garbage-collected
_open_windows: list = []


class xexplorer(QMainWindow):
    def __init__(self, initial_path: str = "") -> None:
        super().__init__()
        self.mgr = ThemeManager()

        self.setWindowTitle("X-Explorer")
        self.resize(1380, 860)
        self.setMinimumSize(900, 580)

        icon_path = os.path.join(ASSETS_DIR, "xexplorer.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.view = QWebEngineView()
        s = self.view.settings()
        for attr in ("DeveloperExtrasEnabled", "LocalContentCanAccessFileUrls",
                     "LocalContentCanAccessRemoteUrls"):
            a = getattr(QWebEngineSettings.WebAttribute, attr, None)
            if a:
                s.setAttribute(a, True)

        self.setCentralWidget(self.view)

        self.bridge = XExplorerBridge(initial_path=initial_path)
        self.channel = QWebChannel(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # Live theme injection
        self._theme_bridge = WebThemeBridge(self.mgr, self.view)

        self.shortcut_devtools = QShortcut(QKeySequence("F12"), self)
        self.shortcut_devtools.activated.connect(self._open_devtools)

        # Spawn a new window when JS tears off a tab
        self.bridge.open_window_requested.connect(self._spawn_window)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        html_path  = os.path.join(script_dir, "xexplorer.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

    def _spawn_window(self, path: str) -> None:
        win = xexplorer(initial_path=path)
        win.resize(self.width(), self.height())
        win.move(self.x() + 40, self.y() + 40)
        win.show()
        _open_windows.append(win)

    def closeEvent(self, event):  # type: ignore[override]
        with __import__('contextlib').suppress(ValueError):
            _open_windows.remove(self)
        super().closeEvent(event)

    def _open_devtools(self) -> None:
        self._devtools = QWebEngineView()
        self._devtools.setWindowTitle("XExplorer DevTools")
        self._devtools.resize(1100, 750)
        self.view.page().setDevToolsPage(self._devtools.page())
        self._devtools.show()


def main() -> None:
    from PyQt6.QtCore import Qt
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.xexplorer")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = xexplorer()
    _open_windows.append(win)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
