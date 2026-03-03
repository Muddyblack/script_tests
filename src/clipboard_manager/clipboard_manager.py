"""Clipboard Manager — WebEngine-powered viewer/editor of persistent clipboard history.

The actual clipboard capture runs 24/7 via ClipboardWatcher in Nexus.
This window is a pure React/web UI backed by ClipboardBridge over QWebChannel.
"""

import os
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow

try:
    from src.common.config import ASSETS_DIR
except ImportError:
    ASSETS_DIR = ""

from src.common.theme import ThemeManager, WebThemeBridge
from src.clipboard_manager.bridge import ClipboardBridge


class ClipboardManager(QMainWindow):
    """Clipboard history viewer powered by a web UI."""

    def __init__(self) -> None:
        super().__init__()
        self.mgr = ThemeManager()

        self.setWindowTitle("Clipboard Manager")
        self.resize(1100, 700)
        self.setMinimumSize(740, 480)

        icon_path = os.path.join(ASSETS_DIR, "clipboard_manager.png")
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

        self.bridge = ClipboardBridge(self)
        self.channel = QWebChannel(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self._theme_bridge = WebThemeBridge(self.mgr, self.view)

        self.shortcut_devtools = QShortcut(QKeySequence("F12"), self)
        self.shortcut_devtools.activated.connect(self._open_devtools)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        html_path  = os.path.join(script_dir, "clipboard_manager.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

    def _open_devtools(self) -> None:
        self._devtools = QWebEngineView()
        self._devtools.setWindowTitle("Clipboard Manager DevTools")
        self._devtools.resize(1100, 750)
        self.view.page().setDevToolsPage(self._devtools.page())
        self._devtools.show()

    def closeEvent(self, event):
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
