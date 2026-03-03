"""
Chronos — main window and application entry point.

Heavy lifting lives in dedicated modules:
  db.py     — SQLite schema & migrations
  bridge.py — Qt/Python backend bridge (ChronosBridge + _AIWorker)
"""

import datetime
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from src.chronos.bridge import ChronosBridge
from src.chronos.db import init_db
from src.common.config import CHRONOS_DIR
from src.common.web_app_window import BaseWebApp

os.makedirs(CHRONOS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class ChronosApp(BaseWebApp):
    WINDOW_TITLE = "Chronos"
    ICON_NAME = "chronos"
    DEFAULT_SIZE = (1200, 900)
    WEB_ATTRS = ("DeveloperExtrasEnabled",)
    PERSISTENT_PROFILE = ("chronos", os.path.join(CHRONOS_DIR, "webprofile"))

    def __init__(self) -> None:
        init_db()
        super().__init__()

    def create_bridge(self) -> ChronosBridge:
        return ChronosBridge()

    def html_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "chronos_v4.html")

    def after_init(self) -> None:
        self.rem_timer = QTimer(self)
        self.rem_timer.timeout.connect(self._check_reminders)
        self.rem_timer.start(60_000)
        self.last_hour = -1

    def _check_reminders(self) -> None:
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
