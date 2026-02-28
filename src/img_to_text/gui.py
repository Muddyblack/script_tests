"""Desktop snip-to-text GUI and Overlay."""

from __future__ import annotations

import os
import tempfile
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QMimeData,
    QObject,
    QPoint,
    QRect,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QClipboard,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.theme import ThemeManager

from .extractor import ocr_qimage

# ══════════════════════════════════════════════════════════════════════════════
#  Theme / Colors
# ══════════════════════════════════════════════════════════════════════════════


class _C:
    def __init__(self):
        self._mgr = None

    @property
    def mgr(self):
        if self._mgr is None:
            self._mgr = ThemeManager()
        return self._mgr

    @property
    def ACCENT(self):
        return QColor(self.mgr["accent"])

    @property
    def ACCENT_LITE(self):
        return QColor(self.mgr["accent_pressed"])

    @property
    def SUCCESS(self):
        return QColor(self.mgr["success"])

    @property
    def WARNING(self):
        return QColor(self.mgr["warning"])

    @property
    def ERROR(self):
        return QColor(self.mgr["danger"])

    @property
    def BG(self):
        c = QColor(self.mgr["bg_base"])
        c.setAlpha(245)
        return c

    @property
    def TEXT(self):
        return QColor(self.mgr["text_primary"])

    @property
    def TEXT_DIM(self):
        return QColor(self.mgr["text_secondary"])

    @property
    def OVERLAY_DIM(self):
        return QColor(0, 0, 0, 100)


C = _C()


# ---------------------------------------------------------------------------
# Recent snips history
# ---------------------------------------------------------------------------


@dataclass
class _SnipRecord:
    timestamp: datetime
    text: str
    image: QImage


_recent_snips: deque[_SnipRecord] = deque(maxlen=10)

# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------


def _capture_virtual_desktop() -> tuple[QPixmap, QRect]:
    screens = QGuiApplication.screens()
    if not screens:
        raise RuntimeError("No screens detected")
    virtual_geo = screens[0].virtualGeometry()
    canvas = QPixmap(virtual_geo.size())
    canvas.fill(Qt.GlobalColor.black)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for screen in screens:
        geo = screen.geometry()
        shot = screen.grabWindow(0)
        painter.drawPixmap(
            geo.x() - virtual_geo.x(),
            geo.y() - virtual_geo.y(),
            geo.width(),
            geo.height(),
            shot,
        )
    painter.end()
    return canvas, virtual_geo


# ══════════════════════════════════════════════════════════════════════════════
#  Snip Overlay  (Flameshot-style inline toolbar)
# ══════════════════════════════════════════════════════════════════════════════

_LOUPE_PX = 200
_LOUPE_ZOOM = 6

_TOOLBAR_BTN_STYLE = """
QPushButton {{
    background: rgba(15, 15, 25, 0.96);
    color: rgba(255,255,255,0.88);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 5px;
    padding: 0 10px;
    font: 9pt 'Segoe UI';
}}
QPushButton:hover {{
    background: {color};
    border-color: {color};
    color: #ffffff;
}}
QPushButton:pressed {{
    background: {color};
}}
"""


class SnipOverlay(QWidget):
    # Now emits (rect, action) so the caller doesn't need a separate menu
    snip_taken = pyqtSignal(QRect, str)
    snip_cancelled = pyqtSignal()

    _TOOLBAR = [
        ("✓", "Accept", "text", "#22c55e"),
        ("✗", "Cancel", "cancel", "#ef4444"),
        ("💾", "Save", "save", "#3b82f6"),
        ("💾", "Save As", "save", "#2563eb"),
        ("📋", "Copy", "image", "#8b5cf6"),
        ("📝", "Copy Text", "text", "#6366f1"),
        ("📤", "Export", "editor", "#06b6d4"),
    ]

    def __init__(self, desktop: QPixmap, virtual_geo: QRect):
        super().__init__()
        self._desktop = desktop
        self._virtual_geo = virtual_geo
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(virtual_geo)
        self._dragging = False
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._mouse: QPoint = QPoint(0, 0)
        self._confirmed = False
        self._toolbar_btns: list[QPushButton] = []

    def _sel_rect(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized()

    def _reset_to_selecting(self) -> None:
        self._confirmed = False
        for btn in self._toolbar_btns:
            btn.deleteLater()
        self._toolbar_btns.clear()
        self.setCursor(Qt.CursorShape.CrossCursor)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            if self._confirmed:
                self._reset_to_selecting()
                self._origin = None
                self._current = None
                self.update()
            else:
                self.snip_cancelled.emit()
                self.close()
        elif ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._confirmed:
            self._on_action("text")
        else:
            super().keyPressEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._confirmed:
                # Click outside selection → restart draw
                if not self._sel_rect().contains(ev.position().toPoint()):
                    self._reset_to_selecting()
                    self._dragging = True
                    self._origin = self._current = ev.position().toPoint()
                    self.update()
            else:
                self._dragging = True
                self._origin = self._current = ev.position().toPoint()
                self.update()

    def mouseMoveEvent(self, ev):
        self._mouse = ev.position().toPoint()
        if self._dragging:
            self._current = self._mouse
        self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._current = ev.position().toPoint()
            rect = self._sel_rect()
            if rect.width() < 4 or rect.height() < 4:
                self.snip_cancelled.emit()
                self.close()
            else:
                self._confirmed = True
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self._show_toolbar(rect)
                self.update()

    def _show_toolbar(self, sel: QRect) -> None:
        for btn in self._toolbar_btns:
            btn.deleteLater()
        self._toolbar_btns.clear()

        for icon, label, action, color in self._TOOLBAR:
            btn = QPushButton(f"{icon}  {label}", self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet(_TOOLBAR_BTN_STYLE.format(color=color))
            btn.clicked.connect(lambda _, a=action: self._on_action(a))
            self._toolbar_btns.append(btn)

        spacing = 4
        for btn in self._toolbar_btns:
            btn.adjustSize()

        total_w = (
            sum(b.width() for b in self._toolbar_btns)
            + spacing * max(0, len(self._toolbar_btns) - 1)
        )

        # Right-align toolbar to selection's right edge, below selection
        x = sel.right() - total_w
        x = max(4, min(x, self.width() - total_w - 4))
        y = sel.bottom() + 8
        if y + 28 > self.height() - 4:
            y = sel.top() - 28 - 8
        y = max(4, y)

        cur_x = x
        for btn in self._toolbar_btns:
            btn.move(cur_x, y)
            btn.show()
            cur_x += btn.width() + spacing

    def _on_action(self, action: str) -> None:
        rect = self._sel_rect()
        for btn in self._toolbar_btns:
            btn.hide()
        if action == "cancel":
            self.snip_cancelled.emit()
        else:
            self.snip_taken.emit(rect, action)
        self.close()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.drawPixmap(0, 0, self._desktop)
        p.fillRect(self.rect(), C.OVERLAY_DIM)
        rect = self._sel_rect()
        if not rect.isNull():
            self._paint_selection(p, rect)
        if not self._confirmed:
            self._draw_loupe(p, self._mouse)
            self._paint_hint_bar(p)
        p.end()

    def _paint_selection(self, p: QPainter, r: QRect):
        # Clear dim, reveal desktop
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(r, Qt.GlobalColor.transparent)
        p.restore()
        p.drawPixmap(r, self._desktop, r)

        # Border
        p.setPen(QPen(C.ACCENT_LITE, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)

        # Corner dots
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 220))
        for cx, cy in [
            (r.left(), r.top()),
            (r.right(), r.top()),
            (r.left(), r.bottom()),
            (r.right(), r.bottom()),
        ]:
            p.drawEllipse(QPoint(cx, cy), 5, 5)

        # Dimension badge — only while dragging, toolbar replaces it when confirmed
        if not self._confirmed:
            badge = f"{r.width()} × {r.height()}"
            font = QFont("Segoe UI", 8)
            p.setFont(font)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(badge) + 16
            th = fm.height() + 8
            bx = r.center().x() - tw // 2
            by = r.bottom() + 8
            path = QPainterPath()
            path.addRoundedRect(float(bx), float(by), float(tw), float(th), 4, 4)
            p.fillPath(path, QColor(0, 0, 0, 180))
            p.setPen(C.TEXT)
            p.drawText(bx + 8, by + fm.ascent() + 4, badge)

    def _draw_loupe(self, p: QPainter, pos: QPoint) -> None:
        sz = _LOUPE_PX
        zoom = _LOUPE_ZOOM
        src_w = sz // zoom
        src = QRect(pos.x() - src_w // 2, pos.y() - src_w // 2, src_w, src_w)
        lx = pos.x() + 28
        ly = pos.y() + 28
        if lx + sz > self.width():
            lx = pos.x() - sz - 28
        if ly + sz > self.height():
            ly = pos.y() - sz - 28
        dst = QRect(lx, ly, sz, sz)
        sel = self._sel_rect()
        if not sel.isNull() and dst.intersects(sel):
            lx = pos.x() - sz - 28 if lx >= pos.x() else pos.x() + 28
            ly = pos.y() - sz - 28 if ly >= pos.y() else pos.y() + 28
            dst = QRect(lx, ly, sz, sz)

        # Circular clip
        p.save()
        p.setClipRegion(QRegion(dst, QRegion.RegionType.Ellipse))

        # Crisp pixel-perfect scaling (no smoothing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawPixmap(dst, self._desktop, src)

        # Pixel grid lines inside loupe
        grid_pen = QPen(QColor(255, 255, 255, 28), 0.5)
        p.setPen(grid_pen)
        cell = sz / src_w  # pixels per zoom cell
        x0, y0 = float(dst.left()), float(dst.top())
        for i in range(1, src_w):
            x = x0 + i * cell
            p.drawLine(int(x), dst.top(), int(x), dst.bottom())
        for i in range(1, src_w):
            y = y0 + i * cell
            p.drawLine(dst.left(), int(y), dst.right(), int(y))

        p.restore()

        # Outer ring
        p.setPen(QPen(QColor(255, 255, 255, 160), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(dst)

        # Inner accent ring
        p.setPen(QPen(C.ACCENT_LITE, 1))
        inner = dst.adjusted(4, 4, -4, -4)
        p.drawEllipse(inner)

        # Crosshair
        cx, cy = dst.center().x(), dst.center().y()
        p.setPen(QPen(C.ACCENT_LITE, 1))
        p.drawLine(cx - 10, cy, cx + 10, cy)
        p.drawLine(cx, cy - 10, cx, cy + 10)
        # Center dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C.ACCENT)
        p.drawEllipse(QPoint(cx, cy), 2, 2)

        # Coordinate badge below loupe
        coord = f"{pos.x()}, {pos.y()}"
        font = QFont("Segoe UI", 7)
        p.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(coord) + 12
        th = fm.height() + 6
        bx = dst.center().x() - tw // 2
        by = dst.bottom() + 6
        coord_path = QPainterPath()
        coord_path.addRoundedRect(float(bx), float(by), float(tw), float(th), 3, 3)
        p.fillPath(coord_path, QColor(0, 0, 0, 180))
        p.setPen(C.TEXT_DIM)
        p.drawText(bx + 6, by + fm.ascent() + 3, coord)

    def _paint_hint_bar(self, p: QPainter):
        bar_h = 36
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(bar_h), 0, 0)
        p.fillPath(path, QColor(0, 0, 0, 140))
        p.setPen(QColor(255, 255, 255, 160))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(20, 23, "Drag to select region  ·  Esc to cancel")

    def crop_selection(self, rect: QRect) -> QImage:
        return self._desktop.copy(rect).toImage()


# ══════════════════════════════════════════════════════════════════════════════
#  Toast Notification
# ══════════════════════════════════════════════════════════════════════════════


class Toast(QWidget):
    def __init__(
        self,
        message: str,
        icon: str = "✓",
        color: QColor = None,
        duration_ms: int = 2500,
    ):
        super().__init__()
        if color is None:
            color = C.ACCENT
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lbl = QLabel(f"{icon}  {message}")
        lbl.setStyleSheet("color: rgba(255,255,255,0.9); font: 9pt 'Segoe UI';")
        lay.addWidget(lbl)
        self.setStyleSheet(f"""
            Toast {{
                background: rgba(12,12,22,0.95);
                border-radius: 8px;
                border: 1px solid {color.name()};
            }}
        """)
        self.adjustSize()
        scr = QGuiApplication.primaryScreen().geometry()
        self.move(scr.right() - self.width() - 20, scr.bottom() - self.height() - 60)
        QTimer.singleShot(duration_ms, self.close)

    @staticmethod
    def show_toast(
        msg: str, icon: str = "✓", color: QColor = None, duration_ms: int = 2500
    ):
        if color is None:
            color = C.ACCENT
        t = Toast(msg, icon, color, duration_ms)
        t.show()
        t._ref = t


# ══════════════════════════════════════════════════════════════════════════════
#  OCR Preview Tooltip
# ══════════════════════════════════════════════════════════════════════════════


class OcrPreviewTooltip(QWidget):
    def __init__(self, anchor: QPoint):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self._lbl = QLabel("⏳  Recognizing text…")
        self._lbl.setWordWrap(True)
        self._lbl.setMaximumWidth(340)
        self._lbl.setStyleSheet(
            "color: rgba(255,255,255,0.9); font: 9pt 'Consolas', 'Courier New';"
        )
        layout.addWidget(self._lbl)
        self.setStyleSheet(f"""
            OcrPreviewTooltip {{
                background: rgba(12,12,22,0.95);
                border-radius: 8px;
                border: 1px solid {C.ACCENT.name()};
            }}
        """)
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        sg = screen.geometry()
        self.adjustSize()
        x = min(anchor.x(), sg.right() - self.width() - 8)
        y = max(anchor.y() - self.height() - 10, sg.top() + 8)
        self.move(x, y)

    def set_text(self, text: str) -> None:
        preview = text[:120].replace("\n", " ↵ ")
        if len(text) > 120:
            preview += " …"
        self._lbl.setText(preview or "⚠️  No text detected")
        self.adjustSize()
        QTimer.singleShot(4000, self.close)


# ══════════════════════════════════════════════════════════════════════════════
#  OCR Worker
# ══════════════════════════════════════════════════════════════════════════════


class _Signals(QObject):
    success = pyqtSignal(str)
    error = pyqtSignal(str)


class _OcrWorker(QRunnable):
    def __init__(self, image: QImage):
        super().__init__()
        self.image = image
        self.signals = _Signals()

    def run(self):
        try:
            self.signals.success.emit(ocr_qimage(self.image))
        except Exception as e:
            self.signals.error.emit(str(e).strip() or e.__class__.__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  Clipboard & File Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _copy_text(text: str) -> None:
    mime = QMimeData()
    mime.setText(text)
    QApplication.clipboard().setMimeData(mime, QClipboard.Mode.Clipboard)


def _copy_image(image: QImage) -> None:
    mime = QMimeData()
    mime.setImageData(image)
    QApplication.clipboard().setMimeData(mime, QClipboard.Mode.Clipboard)


def _save_image_dialog(image: QImage) -> str | None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default = str(Path.home() / "Pictures" / f"snip_{ts}.png")
    path, _ = QFileDialog.getSaveFileName(
        None, "Save Snip", default, "PNG Image (*.png);;JPEG Image (*.jpg)"
    )
    if path:
        image.save(path)
        return path
    return None


def _open_in_editor(text: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="snip_", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(text)
    os.startfile(tmp.name)


def _insert_at_cursor(text: str) -> None:
    _copy_text(text)
    time.sleep(0.15)
    import ctypes

    VK_CTRL, VK_V, KEY_UP = 0x11, 0x56, 0x0002

    class KBI(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INP(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ki", KBI), ("pad", ctypes.c_ubyte * 8)]

    def mk(vk, flags=0):
        i = INP()
        i.type = 1
        i.ki.wVk = vk
        i.ki.dwFlags = flags
        return i

    seq = (INP * 4)(mk(VK_CTRL), mk(VK_V), mk(VK_V, KEY_UP), mk(VK_CTRL, KEY_UP))
    ctypes.windll.user32.SendInput(4, seq, ctypes.sizeof(INP))


# ══════════════════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SnipResult:
    text: str
    image: QImage
    action: str


def start_snip_to_text(
    *,
    nexus=None,
    on_done: Callable[[SnipResult], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    """Start the snip → Flameshot-style toolbar → OCR/action flow."""

    def _status(msg: str) -> None:
        if nexus is not None and hasattr(nexus, "status_lbl"):
            nexus.status_lbl.setText(msg)
            nexus.status_lbl.repaint()

    def _pool() -> QThreadPool:
        if nexus is not None and hasattr(nexus, "thread_pool"):
            return nexus.thread_pool
        return QThreadPool.globalInstance()

    def _handle(action: str, image: QImage, anchor: QPoint) -> None:
        if action == "cancel":
            _status("Snip cancelled")
            Toast.show_toast("Cancelled", "—", C.TEXT_DIM, 1200)
            return

        if action == "image":
            _copy_image(image)
            _status("✓ Image copied")
            Toast.show_toast("Image copied", "🖼️", C.ACCENT)
            if on_done:
                on_done(SnipResult("", image, action))
            return

        if action == "save":
            path = _save_image_dialog(image)
            if path:
                _status(f"✓ Saved → {Path(path).name}")
                Toast.show_toast(f"Saved: {Path(path).name}", "💾", C.SUCCESS)
                _recent_snips.appendleft(_SnipRecord(datetime.now(), "", image))
                if on_done:
                    on_done(SnipResult("", image, action))
            else:
                _status("Save cancelled")
            return

        _status("⏳ Recognising text…")
        tip = OcrPreviewTooltip(anchor)
        tip.show()
        w = _OcrWorker(image)

        def _ok(text: str) -> None:
            tip.set_text(text)
            if not text:
                _status("⚠️ No text detected")
                Toast.show_toast("No text detected", "⚠️", C.ERROR)
                if on_error:
                    on_error("No text detected")
                return
            _recent_snips.appendleft(_SnipRecord(datetime.now(), text, image))
            if action == "text":
                _copy_text(text)
                _status("✓ Text copied")
                Toast.show_toast("Text copied", "📋", C.ACCENT)
            elif action == "both":
                _copy_text(text)
                _copy_image(image)
                _status("✓ Text & image copied")
                Toast.show_toast("Text & image copied", "📑", C.ACCENT)
            elif action == "insert":
                _insert_at_cursor(text)
                _status("✓ Text inserted")
                Toast.show_toast("Text inserted", "⌨️", C.SUCCESS)
            elif action == "editor":
                _open_in_editor(text)
                _status("✓ Opened in editor")
                Toast.show_toast("Opened in editor", "📝", C.SUCCESS)
            if on_done:
                on_done(SnipResult(text, image, action))

        def _err(err: str) -> None:
            tip.close()
            _status(f"❌ {err}")
            Toast.show_toast(f"OCR error: {err}", "❌", C.ERROR)
            if on_error:
                on_error(err)

        w.signals.success.connect(_ok)
        w.signals.error.connect(_err)
        _pool().start(w)

    def _on_taken(rect: QRect, action: str, overlay: SnipOverlay) -> None:
        image = overlay.crop_selection(rect)
        screens = QGuiApplication.screens()
        vgeo = screens[0].virtualGeometry() if screens else QRect()
        anchor = QPoint(rect.right() + vgeo.x(), rect.bottom() + vgeo.y())
        QTimer.singleShot(60, lambda: _handle(action, image, anchor))

    def _start_overlay(desktop: QPixmap, vgeo: QRect) -> None:
        ov = SnipOverlay(desktop, vgeo)
        ov.snip_cancelled.connect(
            lambda: (
                _status("Snip cancelled"),
                Toast.show_toast("Cancelled", "—", C.TEXT_DIM, 1200),
            )
        )
        ov.snip_taken.connect(lambda r, a: _on_taken(r, a, ov))
        ov.show()
        ov.raise_()
        ov.activateWindow()
        ov._ref = ov

    def _capture() -> None:
        try:
            desktop, vgeo = _capture_virtual_desktop()
        except Exception as e:
            _status(f"❌ Capture error: {e}")
            Toast.show_toast(f"Capture error: {e}", "❌", C.ERROR)
            if on_error:
                on_error(str(e))
            return
        QTimer.singleShot(30, lambda: _start_overlay(desktop, vgeo))

    if nexus is not None and hasattr(nexus, "hide"):
        nexus.hide()
    QTimer.singleShot(80, _capture)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def get_recent_snips() -> list[_SnipRecord]:
    """Return up to the last 10 snip records (newest first)."""
    return list(_recent_snips)
