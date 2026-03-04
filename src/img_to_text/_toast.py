"""Transient notification widgets: Toast and OcrPreviewTooltip."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ._colors import C

# Transparent padding around the visible box (for glow bleed).
_TOAST_GLOW = 10
_TT_GLOW = 10


class Toast(QWidget):
    def __init__(
        self,
        message: str,
        icon: str = "✓",
        color: QColor | None = None,
        duration_ms: int = 2500,
    ) -> None:
        super().__init__()
        self._color = QColor(color) if color is not None else QColor(C.ACCENT)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Left margin = glow + stripe gap; right/top/bottom = glow pad
        lay = QHBoxLayout(self)
        lay.setContentsMargins(
            _TOAST_GLOW + 16, _TOAST_GLOW + 10, _TOAST_GLOW + 16, _TOAST_GLOW + 10
        )
        lay.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"background: transparent; color: {self._color.name()};"
            " font: 13pt 'Segoe UI Emoji';"
        )
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(icon_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet(
            "background: transparent; color: #ffffff;"
            " font: bold 11pt 'Segoe UI'; letter-spacing: 0.2px;"
        )
        lay.addWidget(msg_lbl)

        self.setMinimumWidth(220 + _TOAST_GLOW * 2)
        self.adjustSize()
        scr = QGuiApplication.primaryScreen().geometry()
        self.move(
            scr.right() - self.width() - 20 + _TOAST_GLOW,
            scr.bottom() - self.height() - 60 + _TOAST_GLOW,
        )
        QTimer.singleShot(duration_ms, self.close)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = _TOAST_GLOW
        box = self.rect().adjusted(g, g, -g, -g)

        # ── glass card ────────────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 12, 28, 175))
        p.drawRoundedRect(box, 12, 12)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(box, 12, 12)
        tint = QColor(self._color)
        tint.setAlpha(30)
        p.setBrush(tint)
        p.drawRoundedRect(box, 12, 12)

        # ── border ────────────────────────────────────────────────────
        border = QColor(self._color)
        border.setAlpha(220)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(border, 1.8))
        p.drawRoundedRect(box.adjusted(1, 1, -1, -1), 11, 11)

        # ── left accent stripe ────────────────────────────────────────
        from PyQt6.QtCore import QRectF

        stripe_h = box.height() - 20
        stripe = QRectF(box.left() + 7, box.top() + 10, 3.5, stripe_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawRoundedRect(stripe, 2, 2)

        p.end()

    @staticmethod
    def show_toast(
        msg: str,
        icon: str = "✓",
        color: QColor | None = None,
        duration_ms: int = 2500,
    ) -> None:
        t = Toast(msg, icon, color or C.ACCENT, duration_ms)
        t.show()
        t._ref = t  # keep alive


class OcrPreviewTooltip(QWidget):
    def __init__(self, anchor: QPoint) -> None:
        super().__init__()
        self._color = QColor(C.ACCENT)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout = QVBoxLayout(self)
        g = _TT_GLOW
        layout.setContentsMargins(g + 16, g + 10, g + 14, g + 10)
        self._lbl = QLabel("⏳  Recognizing text…")
        self._lbl.setWordWrap(True)
        self._lbl.setFixedWidth(320)
        self._lbl.setStyleSheet(
            "background: transparent; color: #ffffff;"
            " font: bold 10pt 'Consolas', 'Courier New';"
        )
        layout.addWidget(self._lbl)
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        self._screen_geo = screen.geometry()
        self.adjustSize()
        x = min(anchor.x(), self._screen_geo.right() - self.width() - 8)
        x = max(self._screen_geo.left() + 8, x)
        y = max(anchor.y() - self.height() - 10, self._screen_geo.top() + 8)
        y = min(self._screen_geo.bottom() - self.height() - 8, y)
        self.move(x, y)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = _TT_GLOW
        box = self.rect().adjusted(g, g, -g, -g)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 12, 28, 175))
        p.drawRoundedRect(box, 12, 12)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(box, 12, 12)
        tint = QColor(self._color)
        tint.setAlpha(30)
        p.setBrush(tint)
        p.drawRoundedRect(box, 12, 12)

        border = QColor(self._color)
        border.setAlpha(220)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(border, 1.8))
        p.drawRoundedRect(box.adjusted(1, 1, -1, -1), 11, 11)

        p.end()

    def set_text(self, text: str, confidence: float | None = None) -> None:
        preview = text[:120].replace("\n", " ↵ ")
        if len(text) > 120:
            preview += " …"
        if confidence is None:
            badge = ""
        elif confidence >= 0.85:
            badge = f"[HIGH {int(confidence * 100)}%] "
        elif confidence >= 0.70:
            badge = f"[MED {int(confidence * 100)}%] "
        else:
            badge = f"[LOW {int(confidence * 100)}%] "
        self._lbl.setText((badge + preview) if preview else "⚠️  No text detected")
        self.adjustSize()
        x = min(self.x(), self._screen_geo.right() - self.width() - 8)
        x = max(self._screen_geo.left() + 8, x)
        y = min(self.y(), self._screen_geo.bottom() - self.height() - 8)
        y = max(self._screen_geo.top() + 8, y)
        self.move(x, y)
        QTimer.singleShot(4000, self.close)
