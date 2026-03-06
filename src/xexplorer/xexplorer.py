"""XExplorer — WebEngine-powered file explorer main window."""

import os
import sys

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from src.common.config import ASSETS_DIR, XEXPLORER_DIR
from src.common.theme import ThemeManager, WebThemeBridge
from src.xexplorer.bridge import XExplorerBridge

# Keep references so windows aint garbage-collected
_open_windows: list = []

# Persistent web profile for session restore
_web_profile: QWebEngineProfile | None = None


def get_web_profile() -> QWebEngineProfile:
    """Get or create the persistent web profile for xexplorer."""
    global _web_profile
    if _web_profile is None:
        profile_dir = os.path.join(XEXPLORER_DIR, "webprofile")
        os.makedirs(profile_dir, exist_ok=True)
        _web_profile = QWebEngineProfile("xexplorer", None)
        _web_profile.setPersistentStoragePath(profile_dir)
        _web_profile.setCachePath(os.path.join(profile_dir, "cache"))
        # Enable persistent cookies and local storage
        _web_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
    return _web_profile


class LoadingSplash(QWidget):
    """Simple loading splash screen shown while database warms up."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("X-Explorer")
        self.resize(400, 200)

        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)

        # Title
        title = QLabel("X-Explorer")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #2196F3;")
        layout.addWidget(title)

        # Status message
        self.status = QLabel("Initializing database...")
        self.status.setStyleSheet("font-size: 14px; color: #666; margin-top: 20px;")
        layout.addWidget(self.status)

        # Animated dots
        self.dots = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_dots)
        self.timer.start(500)

        layout.addStretch()
        self.setLayout(layout)

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

    def _update_dots(self):
        self.dots = (self.dots + 1) % 4
        self.status.setText("Initializing database" + "." * self.dots)


class xexplorer(QMainWindow):
    def __init__(self, initial_path: str = "", show_splash: bool = True) -> None:
        super().__init__()
        self.mgr = ThemeManager()

        self.setWindowTitle("X-Explorer")
        self.resize(1380, 860)
        self.setMinimumSize(900, 580)

        icon_path = os.path.join(ASSETS_DIR, "xexplorer.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Show splash screen while database warms up (only for first window)
        self.splash = None
        if show_splash:
            self.splash = LoadingSplash()
            self.splash.show()

        # Create persistent profile FIRST, then create page with it
        profile = get_web_profile()
        page = QWebEnginePage(profile, self)
        self.view = QWebEngineView()
        self.view.setPage(page)

        s = self.view.settings()
        for attr in ("DeveloperExtrasEnabled", "LocalContentCanAccessFileUrls",
                     "LocalContentCanAccessRemoteUrls"):
            a = getattr(QWebEngineSettings.WebAttribute, attr, None)
            if a:
                s.setAttribute(a, True)

        self.setCentralWidget(self.view)

        self.bridge = XExplorerBridge(initial_path=initial_path)

        # When database is ready, hide splash and show main window
        if self.splash:
            self.bridge.db_ready.connect(self._on_db_ready)

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

    def _on_db_ready(self):
        """Called when database cache is warmed up."""
        if self.splash:
            self.splash.close()
            self.splash = None
        self.show()

    def _spawn_window(self, path: str) -> None:
        # Spawned windows don't need splash (db already warmed)
        win = xexplorer(initial_path=path, show_splash=False)
        win.resize(self.width(), self.height())
        win.move(self.x() + 40, self.y() + 40)
        win.show()
        _open_windows.append(win)

    def closeEvent(self, event):  # type: ignore[override]
        # Properly cleanup WebEngine resources to avoid warnings
        if hasattr(self, "_devtools"):
            self._devtools.setPage(None)
            self._devtools.deleteLater()
            self._devtools = None

        # Disconnect signals
        if hasattr(self, "bridge"):
            self.bridge.open_window_requested.disconnect()

        # Clear web channel
        if hasattr(self, "channel"):
            self.channel.deregisterObject(self.bridge)

        # Cleanup view and page
        if hasattr(self, "view"):
            page = self.view.page()
            self.view.setPage(None)
            if page:
                page.deleteLater()
            self.view.deleteLater()

        with __import__("contextlib").suppress(ValueError):
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
    # Don't show main window yet - splash will show first, then main window when db ready
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
