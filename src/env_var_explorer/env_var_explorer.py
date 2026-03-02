"""Env Var Explorer — browse, edit, add & delete environment variables.

Far better than System Properties → Advanced → Environment Variables:
• User / System / Process (current session) tabs
• Full-text search across names and values
• PATH-type vars shown as split list (one path per row)
• Add, edit, delete with immediate winreg write (no shell restart needed)
• Undo last change (single-level)
• Export visible vars to clipboard as JSON
• Reads directly from the Windows Registry (winreg) for User & System vars
"""

import os
import sys

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from src.common.config import ICON_PATH
except ImportError:
    ICON_PATH = ""

from src.common.theme import ThemeManager
from src.common.theme_template import TOOL_SHEET
from src.env_var_explorer.style import EXTRA
from src.env_var_explorer.widgets import EnvTab


class EnvVarExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self._mgr = ThemeManager()

        self.setWindowTitle("Env Var Explorer")
        if ICON_PATH and os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(860, 580)
        self.resize(1000, 660)

        self._build_ui()
        self._apply_theme()
        self._mgr.theme_changed.connect(self._apply_theme)
        _fade_in(self)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        out = QVBoxLayout(root)
        out.setContentsMargins(20, 20, 20, 20)
        out.setSpacing(14)

        hdr = QHBoxLayout()
        title = QLabel("ENV VAR EXPLORER")
        title.setObjectName("title")
        sub = QLabel("browse · edit · add · delete  environment variables")
        sub.setObjectName("sub")
        sub.setAlignment(Qt.AlignmentFlag.AlignBottom)
        hdr.addWidget(title)
        hdr.addSpacing(10)
        hdr.addWidget(sub)
        hdr.addStretch()
        out.addLayout(hdr)

        tabs = QTabWidget()
        for scope, label in [("user", "USER"), ("system", "SYSTEM"), ("process", "PROCESS")]:
            tab = EnvTab(scope)
            tab.status_msg.connect(self._flash)
            tabs.addTab(tab, label)
        out.addWidget(tabs)

        self._status = QLabel("")
        self._status.setObjectName("status")
        out.addWidget(self._status)

    def _apply_theme(self):
        self._mgr.apply_to_widget(self, TOOL_SHEET + EXTRA)

    def _flash(self, msg: str):
        self._status.setText(msg)
        QTimer.singleShot(3500, lambda: self._status.setText(""))

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(e)


def _fade_in(w: QWidget, ms: int = 220):
    eff = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = EnvVarExplorer()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
