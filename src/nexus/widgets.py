"""Reusable Qt widgets: custom input, icon loader, signal bridge."""

import os

from PyQt6.QtCore import (
    QFileInfo,
    QObject,
    QRunnable,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtWidgets import QLineEdit


# ---------------------------------------------------------------------------
# Custom search input that forwards navigation keys to the host NexusSearch
# ---------------------------------------------------------------------------
class NexusInput(QLineEdit):
    """Search input that intercepts arrow / enter / escape keys."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nexus = parent

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Down:
            self.nexus.navigate_results(1)
            event.accept()
        elif key == Qt.Key.Key_Up:
            self.nexus.navigate_results(-1)
            event.accept()
        elif key == Qt.Key.Key_PageDown:
            self.nexus.navigate_results(10)
            event.accept()
        elif key == Qt.Key.Key_PageUp:
            self.nexus.navigate_results(-10)
            event.accept()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.nexus.launch_selected()
            event.accept()
        elif key == Qt.Key.Key_Escape:
            self.nexus.hide()
            event.accept()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Background icon loader (runs on QThreadPool)
# ---------------------------------------------------------------------------
class IconWorker(QRunnable):
    """Loads a file icon off the main thread and updates the cache."""

    def __init__(self, path: str, cache_key: str, nexus):
        super().__init__()
        self.path = path
        self.cache_key = cache_key
        self.nexus = nexus

    def run(self):
        try:
            if not os.path.exists(self.path):
                return
            icon = self.nexus.icon_provider.icon(QFileInfo(self.path))
            pixmap = icon.pixmap(256, 256)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    42,
                    42,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.nexus.icon_cache[self.cache_key] = pixmap
                QTimer.singleShot(0, self.nexus.lazy_load_visible_icons)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Thread-safe signal bridge (hotkey thread -> Qt main thread)
# ---------------------------------------------------------------------------
class NexusBridge(QObject):
    """Emits a signal to toggle Nexus visibility from any thread."""

    toggle_signal = pyqtSignal()
