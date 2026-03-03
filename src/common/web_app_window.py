"""BaseWebApp – shared QMainWindow skeleton for WebEngine-based tool windows.

Every tool that renders a local HTML file via QWebEngineView shares:
  - ThemeManager + WebThemeBridge setup
  - QWebEngineView creation (with optional persistent profile)
  - QWebChannel wired to a bridge object exposed as ``pyBridge``
  - F12 → DevTools shortcut
  - Icon loading from the assets directory

Usage
-----
class MyTool(BaseWebApp):
    WINDOW_TITLE = "My Tool"
    ICON_NAME    = "my_tool"          # assets/my_tool.png
    DEFAULT_SIZE = (900, 600)

    def create_bridge(self):
        return MyBridge(self)

    def html_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "my_tool.html")
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow

from src.common.theme import ThemeManager, WebThemeBridge

_DEFAULT_WEB_ATTRS: tuple[str, ...] = (
    "DeveloperExtrasEnabled",
    "LocalContentCanAccessFileUrls",
    "LocalContentCanAccessRemoteUrls",
)


class BaseWebApp(QMainWindow):
    """Shared skeleton for all WebEngine-backed tool windows.

    Subclasses must override:
        create_bridge() -> bridge object registered as ``pyBridge``
        html_path()     -> absolute path to the HTML entry-point

    Subclasses may override:
        after_init()    -> runs after all wiring, before setUrl
    """

    # ── class-level defaults (override in each subclass) ─────────────────
    WINDOW_TITLE: str = "App"
    ICON_NAME: str | None = None
    DEFAULT_SIZE: tuple[int, int] = (1000, 700)
    MIN_SIZE: tuple[int, int] | None = None
    WEB_ATTRS: tuple[str, ...] = _DEFAULT_WEB_ATTRS
    # Set to ("profile_name", "/path/to/storage") for persistent localStorage
    PERSISTENT_PROFILE: tuple[str, str] | None = None

    # ─────────────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        super().__init__()
        self.mgr = ThemeManager()
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(*self.DEFAULT_SIZE)
        if self.MIN_SIZE:
            self.setMinimumSize(*self.MIN_SIZE)

        self._load_icon()
        self._setup_view()

        self.bridge = self.create_bridge()
        self.channel = QWebChannel(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self._theme_bridge = WebThemeBridge(self.mgr, self.view)

        self._devtools_shortcut = QShortcut(QKeySequence("F12"), self)
        self._devtools_shortcut.activated.connect(self._open_devtools)

        self.after_init()
        self.view.setUrl(QUrl.fromLocalFile(self.html_path()))

    # ── required overrides ────────────────────────────────────────────────

    def create_bridge(self):
        raise NotImplementedError(f"{type(self).__name__} must implement create_bridge()")

    def html_path(self) -> str:
        raise NotImplementedError(f"{type(self).__name__} must implement html_path()")

    # ── optional hook ─────────────────────────────────────────────────────

    def after_init(self) -> None:
        """Override to run additional setup after wiring but before setUrl."""

    # ── private helpers ───────────────────────────────────────────────────

    def _load_icon(self) -> None:
        if not self.ICON_NAME:
            return
        try:
            from src.common.config import ASSETS_DIR

            path = os.path.join(ASSETS_DIR, f"{self.ICON_NAME}.png")
            if os.path.exists(path):
                self.setWindowIcon(QIcon(path))
        except ImportError:
            pass

    def _setup_view(self) -> None:
        if self.PERSISTENT_PROFILE:
            profile_name, profile_path = self.PERSISTENT_PROFILE
            os.makedirs(profile_path, exist_ok=True)
            self._profile = QWebEngineProfile(profile_name, self)
            self._profile.setPersistentStoragePath(profile_path)
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
            )
            page = QWebEnginePage(self._profile, self)
            self.view = QWebEngineView()
            self.view.setPage(page)
        else:
            self.view = QWebEngineView()

        settings = self.view.settings()
        for attr_name in self.WEB_ATTRS:
            attr = getattr(QWebEngineSettings.WebAttribute, attr_name, None)
            if attr is not None:
                settings.setAttribute(attr, True)

        self.setCentralWidget(self.view)

    def _open_devtools(self) -> None:
        self._devtools = QWebEngineView()
        self._devtools.setWindowTitle(f"{self.windowTitle()} DevTools")
        self._devtools.resize(1000, 700)
        self.view.page().setDevToolsPage(self._devtools.page())
        self._devtools.show()
