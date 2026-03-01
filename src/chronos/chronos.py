"""
Chronos — main window and application entry point.

Heavy lifting lives in dedicated modules:
  db.py     — SQLite schema & migrations
  bridge.py — Qt/Python backend bridge (ChronosBridge + _AIWorker)
"""

import datetime
import os
import sys

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow

from src.chronos.bridge import ChronosBridge
from src.chronos.db import init_db
from src.common.config import CHRONOS_DIR
from src.common.theme import ThemeManager, WebThemeBridge

os.makedirs(CHRONOS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class ChronosApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.mgr = ThemeManager()
        init_db()
        self.setWindowTitle("Chronos")
        try:
            from src.common.config import ASSETS_DIR

            icon_path = os.path.join(ASSETS_DIR, "chronos.png")

            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except ImportError:
            pass
        self.resize(1200, 900)

        # Persistent profile so localStorage survives app restarts
        profile_path = os.path.join(CHRONOS_DIR, "webprofile")
        os.makedirs(profile_path, exist_ok=True)
        self._profile = QWebEngineProfile("chronos", self)
        self._profile.setPersistentStoragePath(profile_path)
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        page = QWebEnginePage(self._profile, self)
        self.view = QWebEngineView()
        self.view.setPage(page)
        attrs = self.view.settings()
        dev_attr = getattr(
            QWebEngineSettings.WebAttribute, "DeveloperExtrasEnabled", None
        )
        if dev_attr is not None:
            attrs.setAttribute(dev_attr, True)

        self.setCentralWidget(self.view)

        self.bridge = ChronosBridge()
        self.channel = QWebChannel(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.shortcut = QShortcut(QKeySequence("F12"), self)
        self.shortcut.activated.connect(self._open_devtools)

        # WebThemeBridge handles all theme injection (DocumentCreation + live updates)
        self._theme_bridge = WebThemeBridge(self.mgr, self.view)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(script_dir, "chronos_v4.html")
        self.view.setUrl(QUrl.fromLocalFile(html_path))

        self.rem_timer = QTimer(self)
        self.rem_timer.timeout.connect(self._check_reminders)
        self.rem_timer.start(60000)
        self.last_hour = -1

    def _open_devtools(self):
        self.devtools_view = QWebEngineView()
        self.devtools_view.setWindowTitle("Chronos DevTools")
        self.devtools_view.resize(1000, 700)
        self.view.page().setDevToolsPage(self.devtools_view.page())
        self.devtools_view.show()

    def _check_reminders(self):
        if not self.bridge.settings.get("reminders_enabled"):
            return
        hr = datetime.datetime.now().hour
        if hr in [12, 17] and hr != self.last_hour:
            self.last_hour = hr
            self.view.page().runJavaScript("triggerReminderPopup()")
            self.showNormal()
            self.activateWindow()


if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.chronos")
    app = QApplication(sys.argv)
    window = ChronosApp()
    window.show()
    sys.exit(app.exec())
