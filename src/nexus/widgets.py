"""Reusable Qt widgets: custom input, icon loader, signal bridge, rainbow frame."""

import contextlib
import os

from PyQt6.QtCore import (
    QFileInfo,
    QObject,
    QRectF,
    QRunnable,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QConicalGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QFrame, QLineEdit, QVBoxLayout


# ---------------------------------------------------------------------------
# Rainbow glow frame — wraps the input and paints a one-shot animated border
# ---------------------------------------------------------------------------
class RainbowFrame(QFrame):
    """Wraps a child widget with a one-time rainbow sweep animation.

    When ``trigger_animation()`` is called the frame paints a
    rotating conical gradient border that fades out after ~1.5 s.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rainbow_frame")
        self._angle = 0.0
        self._opacity = 0.0
        self._running = False
        self._border_radius = 16

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps
        self._timer.timeout.connect(self._tick)

        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._start_fade)

        self._content_layout = QVBoxLayout(self)
        self._content_layout.setContentsMargins(3, 3, 3, 3)
        self._content_layout.setSpacing(0)

    # -- public api ---------------------------------------------------------
    def trigger_animation(self):
        """Start (or restart) the rainbow sweep."""
        self._angle = 0.0
        self._opacity = 1.0
        self._running = True
        self._timer.start()
        self._fade_timer.start(1200)  # start fading after 1.2 s

    # -- internals ----------------------------------------------------------
    def _tick(self):
        self._angle = (self._angle + 4) % 360
        if self._opacity <= 0:
            self._running = False
            self._timer.stop()
            self._opacity = 0.0
        self.update()

    def _start_fade(self):
        self._fade_step = QTimer(self)
        self._fade_step.setInterval(16)
        self._fade_step.timeout.connect(self._do_fade)
        self._fade_step.start()

    def _do_fade(self):
        self._opacity -= 0.03
        if self._opacity <= 0:
            self._opacity = 0
            self._fade_step.stop()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._running and self._opacity <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Build rounded-rect path
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, self._border_radius, self._border_radius)

        # Conical gradient rotates
        cx, cy = rect.center().x(), rect.center().y()
        gradient = QConicalGradient(cx, cy, self._angle)

        # Google-AI style rainbow: blue -> purple -> pink -> orange -> yellow -> green -> blue
        colors = [
            (0.00, QColor(66, 133, 244)),  # Blue
            (0.15, QColor(102, 102, 241)),  # Indigo
            (0.30, QColor(171, 71, 188)),  # Purple
            (0.45, QColor(236, 64, 122)),  # Pink
            (0.60, QColor(255, 152, 0)),  # Orange
            (0.75, QColor(76, 175, 80)),  # Green
            (0.90, QColor(0, 188, 212)),  # Teal
            (1.00, QColor(66, 133, 244)),  # Blue (wrap)
        ]
        for stop, color in colors:
            c = QColor(color)
            c.setAlphaF(self._opacity * 0.85)
            gradient.setColorAt(stop, c)

        pen = QPen()
        pen.setWidthF(2.5)
        pen.setBrush(gradient)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()


# ---------------------------------------------------------------------------
# Custom search input that forwards navigation keys to the host NexusSearch
# ---------------------------------------------------------------------------
class NexusInput(QLineEdit):
    """Search input that intercepts arrow / enter / escape keys."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nexus = parent

    def _get_suggestion(self):
        text = self.text()
        if not text:
            return ""
        # Check history from nexus
        for h in getattr(self.nexus, "search_history", []):
            if h.lower().startswith(text.lower()) and len(h) > len(text):
                return h[len(text) :]
        return ""

    def _accept_suggestion(self):
        """Accept the inline ghost suggestion."""
        suggestion = self._get_suggestion()
        if suggestion:
            self.setText(self.text() + suggestion)
            return True
        return False

    def event(self, event):
        """Intercept Tab before Qt uses it for focus navigation."""
        from PyQt6.QtCore import QEvent

        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Tab
            and self._accept_suggestion()
        ):
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()

        if (
            event.modifiers() & Qt.KeyboardModifier.AltModifier
            and Qt.Key.Key_1 <= key <= Qt.Key.Key_9
        ):
            idx = key - Qt.Key.Key_1
            if idx < self.nexus.results_list.count():
                self.nexus.results_list.setCurrentRow(idx)
                self.nexus.launch_selected()
            event.accept()
            return

        if (
            key == Qt.Key.Key_Right
            and self.cursorPosition() == len(self.text())
            and self._accept_suggestion()
        ):
            event.accept()
            return
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

    def paintEvent(self, event):
        super().paintEvent(event)
        suggestion = self._get_suggestion()
        if not suggestion:
            return

        painter = QPainter(self)

        # Ghost color — derive from active theme
        from src.common.theme import ThemeManager as _TM

        _ghost_hex = _TM().theme_data.get("colors", {}).get("text_disabled", "#6b7280")
        _ghost = QColor(_ghost_hex)
        _ghost.setAlpha(160)
        painter.setPen(_ghost)

        painter.setFont(self.font())

        # Use cursorRect() — it already accounts for CSS padding,
        # margins, and scroll offset inside the QLineEdit.
        cr = self.cursorRect()
        x_pos = cr.right() + 1
        y_pos = cr.top() + self.fontMetrics().ascent()

        painter.drawText(x_pos, y_pos, suggestion)
        painter.end()


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
        finally:
            with contextlib.suppress(Exception):
                self.nexus.pending_icons.discard(self.cache_key)


# ---------------------------------------------------------------------------
# Thread-safe signal bridge (hotkey thread -> Qt main thread)
# ---------------------------------------------------------------------------
class NexusBridge(QObject):
    """Emits a signal to toggle Nexus visibility from any thread."""

    toggle_signal = pyqtSignal()
    snip_to_text_signal = pyqtSignal()
    chronos_signal = pyqtSignal()
