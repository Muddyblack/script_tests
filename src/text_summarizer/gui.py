"""Text Summarizer — PyQt6 + QWebEngineView UI.

Architecture:
  - QWebEngineView hosts the entire UI as embedded HTML/CSS/JS (src/text_summarizer/web/)
  - QWebChannel bridges Python \u2194 JS via src/text_summarizer/bridge.py
  - ThemeManager drives color tokens via WebThemeBridge and WindowThemeBridge
"""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from src.common.theme import ThemeManager, WebThemeBridge, WindowThemeBridge
from src.common.theme_template import TOOL_SHEET

from .bridge import Bridge


class TextSummarizerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text Summarizer")
        self.setMinimumSize(900, 600)
        self.resize(1200, 760)

        # Set object name for QSS targeting if needed, though TOOL_SHEET uses QMainWindow
        self.setObjectName("TextSummarizerWindow")

        self._bridge = Bridge(self)
        self._bridge.findRequest.connect(self._on_find_request)

        # Web view
        self._view = QWebEngineView()
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._view.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # Prevents focus theft on highlights

        # Web channel
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        # Load HTML from local file
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        index_path = os.path.join(curr_dir, "web", "index.html")
        self._view.load(QUrl.fromLocalFile(index_path))

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)
        self.setCentralWidget(container)

        # Theme integration - Standard bridges
        mgr = ThemeManager()

        # Bridge for the main window (QSS + Palette + Titlebar)
        self._theme_bridge = WindowThemeBridge(mgr, self, TOOL_SHEET)

        # Bridge for the WebEngine view (CSS variables injection)
        # We specify alpha variants to match what style.css expects
        alphas = {
            "accent-bg": ("accent", 0.12),
            "amber-bg":  ("warning", 0.12),
            "warning-dim": ("warning", 0.22),
            "warning-glow": ("warning", 0.10),
            "amber-glow": ("warning", 0.20),
        }
        self._web_theme_bridge = WebThemeBridge(mgr, self._view, alpha_variants=alphas)

    def _on_find_request(self, text: str, forward: bool):
        # Case-insensitive search by default
        self._view.findText(text)


def start_text_summarizer(parent=None) -> TextSummarizerWindow:
    win = TextSummarizerWindow(parent)
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = TextSummarizerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
