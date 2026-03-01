from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any

from PyQt6.QtCore import (
    QMimeData,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QClipboard,
    QColor,
    QCursor,
    QFont,
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
        return QColor(0, 0, 0, 160)


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
# OCR language settings (persisted)
# ---------------------------------------------------------------------------

_OCR_SETTINGS_FILE = Path(os.getenv("APPDATA", Path.home())) / "nexus_ocr_settings.json"

# Mutable globals — modified by _LangBar at runtime
_ocr_langs: list[str] = ["en", "de"]
_ocr_code_mode: bool = False
_ocr_symbol_priority: bool = False


def _load_ocr_settings() -> None:
    global _ocr_langs, _ocr_code_mode, _ocr_symbol_priority
    try:
        data = json.loads(_OCR_SETTINGS_FILE.read_text(encoding="utf-8"))
        _ocr_langs = data.get("languages", ["en", "de"])
        _ocr_code_mode = bool(data.get("code_mode", False))
        _ocr_symbol_priority = bool(data.get("symbol_priority", False))
    except Exception:
        pass


def _save_ocr_settings() -> None:
    try:
        _OCR_SETTINGS_FILE.write_text(
            json.dumps(
                {
                    "languages": _ocr_langs,
                    "code_mode": _ocr_code_mode,
                    "symbol_priority": _ocr_symbol_priority,
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


_load_ocr_settings()

# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------


def _is_wayland() -> bool:
    import sys

    if sys.platform != "linux":
        return False
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    display = os.environ.get("WAYLAND_DISPLAY", "")
    return session == "wayland" or bool(display)


def _capture_wayland() -> tuple[QPixmap, QRect] | None:
    """Try to capture the screen on Wayland using grim or spectacle CLI."""
    import shutil
    import subprocess
    import tempfile

    screens = QGuiApplication.screens()
    virtual_geo = QRect(
        min(s.geometry().left() for s in screens),
        min(s.geometry().top() for s in screens),
        max(s.geometry().right() for s in screens)
        - min(s.geometry().left() for s in screens),
        max(s.geometry().bottom() for s in screens)
        - min(s.geometry().top() for s in screens),
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name

    try:
        # grim: wlroots/KDE Wayland screenshooter (most reliable)
        if shutil.which("grim"):
            ret = subprocess.run(["grim", tmp], timeout=5)
            if ret.returncode == 0:
                px = QPixmap(tmp)
                if not px.isNull():
                    return px, virtual_geo

        # spectacle (KDE) — background fullscreen capture
        if shutil.which("spectacle"):
            ret = subprocess.run(
                [
                    "spectacle",
                    "--background",
                    "--nonotify",
                    "--fullscreen",
                    "--output",
                    tmp,
                ],
                timeout=8,
            )
            if ret.returncode == 0:
                px = QPixmap(tmp)
                if not px.isNull():
                    return px, virtual_geo

        # gnome-screenshot fallback
        if shutil.which("gnome-screenshot"):
            ret = subprocess.run(["gnome-screenshot", "-f", tmp], timeout=5)
            if ret.returncode == 0:
                px = QPixmap(tmp)
                if not px.isNull():
                    return px, virtual_geo
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            os.unlink(tmp)

    return None


def _capture_virtual_desktop() -> tuple[QPixmap, QRect]:
    """Capture the virtual desktop with robust handling for Linux/KDE/Wayland."""
    # Aggressive event pump and delay to ensure launcher is hidden
    for _ in range(12):
        QApplication.processEvents()
        time.sleep(0.04)

    screens = QGuiApplication.screens()
    if not screens:
        raise RuntimeError("No screens detected")

    # On Wayland, grabWindow(0) returns black — use native tools instead
    if _is_wayland():
        result = _capture_wayland()
        if result is not None:
            return result

    # Calculate virtual geometry
    v_left = min(s.geometry().left() for s in screens)
    v_top = min(s.geometry().top() for s in screens)
    v_right = max(s.geometry().right() for s in screens)
    v_bottom = max(s.geometry().bottom() for s in screens)
    virtual_geo = QRect(v_left, v_top, v_right - v_left, v_bottom - v_top)

    canvas = QPixmap(virtual_geo.size())
    canvas.fill(Qt.GlobalColor.black)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    for screen in screens:
        geo = screen.geometry()
        shot = screen.grabWindow(0)
        if not shot.isNull():
            painter.drawPixmap(
                geo.x() - virtual_geo.x(), geo.y() - virtual_geo.y(), shot
            )
    painter.end()

    # If the capture is somehow still black/empty, try primary screen direct grab
    if canvas.isNull() or (canvas.width() < 10 and canvas.height() < 10):
        primary = QGuiApplication.primaryScreen()
        canvas = primary.grabWindow(0)
        virtual_geo = primary.geometry()

    return canvas, virtual_geo


# ══════════════════════════════════════════════════════════════════════════════
#  Snip Overlay  (Spectacle-style handles + Resizable Toolbar)
# ══════════════════════════════════════════════════════════════════════════════

_LOUPE_PX = 200
_LOUPE_ZOOM = 6
_HANDLE_SIZE = 10

# ══════════════════════════════════════════════════════════════════════════════
#  Language selector bar (always-on, top-right of overlay)
# ══════════════════════════════════════════════════════════════════════════════

_LANG_BTN_BASE = (
    "QPushButton {{ background: {bg}; color: {fg}; "
    "border: 1px solid {bd}; border-radius: 4px; "
    "font: bold 8pt 'Segoe UI'; }}"
    "QPushButton:hover {{ background: {hv}; }}"
)

_AVAILABLE_LANGS = [("EN", "en"), ("DE", "de"), ("FR", "fr"), ("ES", "es")]


class _LangBar(QWidget):
    """Persistent language toggle strip shown in the overlay top-right corner."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "background: rgba(12,12,22,0.92); border-radius: 7px;"
            " border: 1px solid rgba(255,255,255,0.12);"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(4)

        lbl = QLabel("Lang:")
        lbl.setStyleSheet(
            "color: rgba(255,255,255,0.45); font: 8pt 'Segoe UI';"
            " border: none; background: transparent;"
        )
        lay.addWidget(lbl)

        self._btns: dict[str, QPushButton] = {}
        for display, code in _AVAILABLE_LANGS:
            btn = QPushButton(display, self)
            btn.setFixedSize(34, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self._toggle_lang(c))
            lay.addWidget(btn)
            self._btns[code] = btn

        sep = QLabel("|", self)
        sep.setStyleSheet(
            "color: rgba(255,255,255,0.2); border: none; background: transparent;"
        )
        lay.addWidget(sep)

        self._code_btn = QPushButton("Code", self)
        self._code_btn.setFixedSize(44, 24)
        self._code_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._code_btn.setToolTip("English-only mode optimised for programming symbols")
        self._code_btn.clicked.connect(self._toggle_code)
        lay.addWidget(self._code_btn)

        self._sym_btn = QPushButton("Sym", self)
        self._sym_btn.setFixedSize(40, 24)
        self._sym_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sym_btn.setToolTip("Boost punctuation/symbol detection (. : / \\ _ @)")
        self._sym_btn.clicked.connect(self._toggle_symbol_priority)
        lay.addWidget(self._sym_btn)

        self.adjustSize()
        self._refresh_styles()

    # ------------------------------------------------------------------
    def _toggle_lang(self, code: str) -> None:
        global _ocr_langs, _ocr_code_mode
        if _ocr_code_mode:
            _ocr_code_mode = False
        if code in _ocr_langs:
            if len(_ocr_langs) > 1:
                _ocr_langs = [c for c in _ocr_langs if c != code]
        else:
            _ocr_langs = [*_ocr_langs, code]
        self._refresh_styles()
        _save_ocr_settings()
        self._prewarm()

    def _toggle_code(self) -> None:
        global _ocr_langs, _ocr_code_mode
        _ocr_code_mode = not _ocr_code_mode
        if _ocr_code_mode:
            _ocr_langs = ["en"]
        self._refresh_styles()
        _save_ocr_settings()
        self._prewarm()

    def _toggle_symbol_priority(self) -> None:
        global _ocr_symbol_priority
        _ocr_symbol_priority = not _ocr_symbol_priority
        self._refresh_styles()
        _save_ocr_settings()

    @staticmethod
    def _prewarm() -> None:
        from .extractor import pre_warm
        pre_warm(["en"] if _ocr_code_mode else _ocr_langs)

    # ------------------------------------------------------------------
    def _refresh_styles(self) -> None:
        for code, btn in self._btns.items():
            active = code in _ocr_langs and not _ocr_code_mode
            btn.setStyleSheet(
                _LANG_BTN_BASE.format(
                    bg="#6366f1" if active else "rgba(255,255,255,0.08)",
                    fg="#ffffff" if active else "rgba(255,255,255,0.50)",
                    bd="#6366f1" if active else "rgba(255,255,255,0.10)",
                    hv="#7c7ff1" if active else "rgba(255,255,255,0.15)",
                )
            )
        ca = _ocr_code_mode
        self._code_btn.setStyleSheet(
            _LANG_BTN_BASE.format(
                bg="#06b6d4" if ca else "rgba(255,255,255,0.08)",
                fg="#ffffff" if ca else "rgba(255,255,255,0.50)",
                bd="#06b6d4" if ca else "rgba(255,255,255,0.10)",
                hv="#22d3ee" if ca else "rgba(255,255,255,0.15)",
            )
        )
        sa = _ocr_symbol_priority
        self._sym_btn.setStyleSheet(
            _LANG_BTN_BASE.format(
                bg="#f59e0b" if sa else "rgba(255,255,255,0.08)",
                fg="#ffffff" if sa else "rgba(255,255,255,0.50)",
                bd="#f59e0b" if sa else "rgba(255,255,255,0.10)",
                hv="#fbbf24" if sa else "rgba(255,255,255,0.15)",
            )
        )


_TOOLBAR_BTN_STYLE = """
QPushButton {{
    background: rgba(15, 15, 25, 0.96);
    color: rgba(255,255,255,0.88);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 5px;
    padding: 0 12px;
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


class OverlayState(Enum):
    IDLE = auto()
    DRAWING = auto()
    SELECTED = auto()
    RESIZING = auto()
    MOVING = auto()


class SnipOverlay(QWidget):
    snip_taken = pyqtSignal(QRect, str)
    snip_cancelled = pyqtSignal()

    _TOOLBAR = [
        ("📋", "1: OCR", "text", "#6366f1"),
        ("🧾", "2: OCR Raw", "text_raw", "#7c3aed"),
        ("🖼️", "3: Image", "image", "#8b5cf6"),
        ("💾", "4: Save", "save", "#3b82f6"),
        ("📤", "5: Share", "share", "#06b6d4"),
        ("❌", "6: Cancel", "cancel", "#ef4444"),
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

        self._state = OverlayState.IDLE
        self._rect = QRect()
        self._drag_start = QPoint()
        self._mouse_pos = self.mapFromGlobal(QCursor.pos())
        self._active_handle: str | None = None
        self._toolbar_btns: list[QPushButton] = []

        # Language bar — always visible in top-right corner
        self._lang_bar = _LangBar(self)
        self._lang_bar.adjustSize()
        self._lang_bar.move(virtual_geo.width() - self._lang_bar.width() - 12, 12)
        self._lang_bar.raise_()
        self._lang_bar.show()

    def keyPressEvent(self, ev):
        key = ev.key()
        # Shortcuts
        if (
            key == Qt.Key.Key_C
            and ev.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            if not self._rect.isNull():
                self._on_action("image")
            return
        if key == Qt.Key.Key_Escape:
            self.snip_cancelled.emit()
            self.close()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self._rect.isNull():
                self._on_action("text")
        elif Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            idx = key - Qt.Key.Key_1
            if idx < len(self._TOOLBAR):
                self._on_action(self._TOOLBAR[idx][2])
        else:
            super().keyPressEvent(ev)

    def _get_handle_at(self, pos: QPoint) -> str | None:
        if self._rect.isNull():
            return None
        r, s = self._rect, _HANDLE_SIZE + 10
        handles = {
            "tl": QRect(r.left() - s // 2, r.top() - s // 2, s, s),
            "tr": QRect(r.right() - s // 2, r.top() - s // 2, s, s),
            "bl": QRect(r.left() - s // 2, r.bottom() - s // 2, s, s),
            "br": QRect(r.right() - s // 2, r.bottom() - s // 2, s, s),
            "t": QRect(r.center().x() - s // 2, r.top() - s // 2, s, s),
            "b": QRect(r.center().x() - s // 2, r.bottom() - s // 2, s, s),
            "l": QRect(r.left() - s // 2, r.center().y() - s // 2, s, s),
            "r": QRect(r.right() - s // 2, r.center().y() - s // 2, s, s),
        }
        for name, rect in handles.items():
            if rect.contains(pos):
                return name
        return None

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position().toPoint()
        handle = self._get_handle_at(pos)

        if handle:
            self._state, self._active_handle, self._drag_start = (
                OverlayState.RESIZING,
                handle,
                pos,
            )
            self._hide_toolbar()
        elif not self._rect.isNull() and self._rect.contains(pos):
            self._state, self._drag_start = OverlayState.MOVING, pos
            self._hide_toolbar()
        else:
            self._state, self._rect = OverlayState.DRAWING, QRect(pos, pos)
            self._hide_toolbar()
        self.update()

    def mouseMoveEvent(self, ev):
        pos = ev.position().toPoint()
        self._mouse_pos = pos
        if self._state == OverlayState.DRAWING:
            self._rect.setBottomRight(pos)
        elif self._state == OverlayState.MOVING:
            diff = pos - self._drag_start
            self._rect.translate(diff)
            self._drag_start = pos
        elif self._state == OverlayState.RESIZING:
            r, h = self._rect, self._active_handle
            if "t" in h:
                r.setTop(pos.y())
            if "b" in h:
                r.setBottom(pos.y())
            if "l" in h:
                r.setLeft(pos.x())
            if "r" in h:
                r.setRight(pos.x())
            self._rect = r.normalized()
        else:
            handle = self._get_handle_at(pos)
            if handle:
                if handle in ("tl", "br"):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif handle in ("tr", "bl"):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif handle in ("t", "b"):
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                elif handle in ("l", "r"):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif not self._rect.isNull() and self._rect.contains(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._state in (
                OverlayState.DRAWING,
                OverlayState.MOVING,
                OverlayState.RESIZING,
            ):
                self._rect = self._rect.normalized()
                if self._rect.width() < 5 or self._rect.height() < 5:
                    if self._state == OverlayState.DRAWING:
                        self.snip_cancelled.emit()
                        self.close()
                else:
                    self._state = OverlayState.SELECTED
                    self._show_toolbar(self._rect)
            self.update()

    def _hide_toolbar(self) -> None:
        for btn in self._toolbar_btns:
            btn.hide()

    def _show_toolbar(self, sel: QRect) -> None:
        if not self._toolbar_btns:
            for icon, label, action, color in self._TOOLBAR:
                btn = QPushButton(f"{icon}  {label}", self)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedHeight(30)
                btn.setStyleSheet(_TOOLBAR_BTN_STYLE.format(color=color))
                btn.clicked.connect(lambda _, a=action: self._on_action(a))
                self._toolbar_btns.append(btn)

        spacing = 6
        for btn in self._toolbar_btns:
            btn.adjustSize()
        total_w = sum(b.width() for b in self._toolbar_btns) + spacing * (
            len(self._toolbar_btns) - 1
        )
        x = max(4, min(sel.center().x() - total_w // 2, self.width() - total_w - 4))
        y = sel.bottom() + 14
        if y + 34 > self.height():
            y = sel.top() - 34 - 14
        cur_x = x
        for btn in self._toolbar_btns:
            btn.move(cur_x, max(4, y))
            btn.show()
            cur_x += btn.width() + spacing

    def _on_action(self, action: str) -> None:
        rect = self._rect.normalized()
        self._hide_toolbar()
        if action == "cancel":
            self.snip_cancelled.emit()
        else:
            self.snip_taken.emit(rect, action)
        self.close()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.drawPixmap(0, 0, self._desktop)

        if not self._rect.isNull():
            sel_rect = self._rect.normalized()
            path = QPainterPath()
            # USE QRectF explicitly to avoid TypeError in PyQt6
            path.addRect(QRectF(self.rect()))
            path.addRect(QRectF(sel_rect))
            p.fillPath(path, C.OVERLAY_DIM)

            p.drawPixmap(sel_rect, self._desktop, sel_rect)
            p.setPen(QPen(C.ACCENT_LITE, 2))
            p.drawRect(sel_rect)

            if self._state != OverlayState.DRAWING:
                self._draw_handles(p, sel_rect)
        else:
            p.fillRect(self.rect(), C.OVERLAY_DIM)

        if self._state in (OverlayState.IDLE, OverlayState.DRAWING):
            self._draw_loupe(p, self._mouse_pos)
            self._paint_hint_bar(p)
        p.end()

    def _draw_handles(self, p: QPainter, r: QRect):
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
        p.setBrush(C.ACCENT)
        s = _HANDLE_SIZE
        points = [
            r.topLeft(),
            r.topRight(),
            r.bottomLeft(),
            r.bottomRight(),
            QPoint(r.center().x(), r.top()),
            QPoint(r.center().x(), r.bottom()),
            QPoint(r.left(), r.center().y()),
            QPoint(r.right(), r.center().y()),
        ]
        for pt in points:
            p.drawEllipse(pt, s // 2, s // 2)

    def _draw_loupe(self, p: QPainter, pos: QPoint) -> None:
        sz, zoom = _LOUPE_PX, _LOUPE_ZOOM
        src_w = sz // zoom
        src = QRect(pos.x() - src_w // 2, pos.y() - src_w // 2, src_w, src_w)
        lx, ly = pos.x() + 35, pos.y() + 35
        if lx + sz > self.width():
            lx = pos.x() - sz - 35
        if ly + sz > self.height():
            ly = pos.y() - sz - 35
        dst = QRect(lx, ly, sz, sz)

        p.save()
        p.setClipRegion(QRegion(dst, QRegion.RegionType.Ellipse))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawPixmap(dst, self._desktop, src)
        p.setPen(QPen(QColor(255, 255, 255, 35), 0.5))
        cell = sz / src_w
        for i in range(1, src_w):
            p.drawLine(
                int(dst.left() + i * cell),
                dst.top(),
                int(dst.left() + i * cell),
                dst.bottom(),
            )
            p.drawLine(
                dst.left(),
                int(dst.top() + i * cell),
                dst.right(),
                int(dst.top() + i * cell),
            )
        p.restore()

        p.setPen(QPen(QColor(255, 255, 255, 200), 2))
        p.drawEllipse(dst)
        p.setPen(QPen(C.ACCENT_LITE, 1))
        p.drawLine(
            dst.center().x() - 12,
            dst.center().y(),
            dst.center().x() + 12,
            dst.center().y(),
        )
        p.drawLine(
            dst.center().x(),
            dst.center().y() - 12,
            dst.center().x(),
            dst.center().y() + 12,
        )

    def _paint_hint_bar(self, p: QPainter):
        p.fillRect(0, 0, self.width(), 36, QColor(0, 0, 0, 180))
        p.setPen(QColor(255, 255, 255, 220))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(20, 23, "Drag to select region  ·  1-6: Shortcuts  ·  Esc: Cancel")

    def crop_selection(self, rect: QRect) -> QImage:
        return self._desktop.copy(rect).toImage()


# ══════════════════════════════════════════════════════════════════════════════
#  Public Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _copy_text(text: str) -> None:
    mime = QMimeData()
    mime.setText(text)
    QApplication.clipboard().setMimeData(mime, QClipboard.Mode.Clipboard)


def _copy_image(image: QImage) -> None:
    QApplication.clipboard().setImage(image)


def _save_image_dialog(image: QImage) -> bool:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path, _ = QFileDialog.getSaveFileName(
        None,
        "Save Snip",
        str(Path.home() / "Pictures" / f"snip_{ts}.png"),
        "Images (*.png *.jpg)",
    )
    if path:
        image.save(path)
        return True
    return False


def _share_image(image: QImage) -> None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        image.save(tmp.name)
        tmp_path = tmp.name
    import subprocess
    import sys

    if sys.platform == "linux":
        _copy_image(image)
        with contextlib.suppress(Exception):
            subprocess.Popen(["xdg-open", tmp_path])
    else:
        os.startfile(tmp_path)


def _open_in_editor(text: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="snip_", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(text)
    import sys

    if sys.platform == "win32":
        os.startfile(tmp.name)
    else:
        import subprocess

        with contextlib.suppress(Exception):
            subprocess.Popen(["xdg-open", tmp.name])


# ══════════════════════════════════════════════════════════════════════════════
#  Toast & Worker
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
        self.setStyleSheet(
            f"Toast {{ background: rgba(12,12,22,0.95); border-radius: 8px; border: 1px solid {color.name()}; }}"
        )
        self.adjustSize()
        scr = QGuiApplication.primaryScreen().geometry()
        self.move(scr.right() - self.width() - 20, scr.bottom() - self.height() - 60)
        QTimer.singleShot(duration_ms, self.close)

    @staticmethod
    def show_toast(
        msg: str, icon: str = "✓", color: QColor = None, duration_ms: int = 2500
    ):
        t = Toast(msg, icon, color or C.ACCENT, duration_ms)
        t.show()
        t._ref = t


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
        self.setStyleSheet(
            f"OcrPreviewTooltip {{ background: rgba(12,12,22,0.95); border-radius: 8px; border: 1px solid {C.ACCENT.name()}; }}"
        )
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


class _Signals(QObject):
    success = pyqtSignal(str)
    error = pyqtSignal(str)


class _OcrWorker(QRunnable):
    def __init__(
        self,
        image: QImage,
        raw_output: bool = False,
        languages: list[str] | None = None,
        symbol_priority: bool = False,
    ):
        super().__init__()
        self.image = image
        self.raw_output = raw_output
        self.languages = languages or list(_ocr_langs)
        self.symbol_priority = symbol_priority
        self.signals = _Signals()

    def run(self):
        try:
            self.signals.success.emit(
                ocr_qimage(
                    self.image,
                    languages=self.languages,
                    raw_output=self.raw_output,
                    symbol_priority=self.symbol_priority,
                )
            )
        except Exception as e:
            self.signals.error.emit(str(e).strip() or e.__class__.__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  Main API
# ══════════════════════════════════════════════════════════════════════════════


def start_snip_to_text(
    *,
    nexus=None,
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    def _status(msg: str) -> None:
        if nexus is not None and hasattr(nexus, "status_lbl"):
            nexus.status_lbl.setText(msg)
            nexus.status_lbl.repaint()

    def _pool() -> QThreadPool:
        return (
            nexus.thread_pool
            if nexus and hasattr(nexus, "thread_pool")
            else QThreadPool.globalInstance()
        )

    def _handle(action: str, image: QImage, anchor: QPoint) -> None:
        if action == "cancel":
            return
        if action == "image":
            _copy_image(image)
            Toast.show_toast("Image Copied", "🖼️")
            return
        if action == "save":
            if _save_image_dialog(image):
                _status("✓ Saved")
                Toast.show_toast("Saved", "💾", C.SUCCESS)
            return
        if action == "share":
            _share_image(image)
            Toast.show_toast("Image Shared", "📤")
            return

        raw_mode = action == "text_raw"
        # Snapshot language selection at the moment of capture
        langs = ["en"] if _ocr_code_mode else list(_ocr_langs)
        symbol_mode = _ocr_symbol_priority
        mode_label = "(code)" if _ocr_code_mode else f"({'+'.join(langs)})"
        if symbol_mode:
            mode_label = f"{mode_label}+sym"
        _status(f"⏳ Recognising {mode_label}…")
        tip = OcrPreviewTooltip(anchor)
        tip.show()
        w = _OcrWorker(
            image,
            raw_output=raw_mode,
            languages=langs,
            symbol_priority=symbol_mode,
        )

        def _ok(text: str):
            tip.set_text(text)
            if not text:
                _status("⚠️ No text")
                Toast.show_toast("No text", "⚠️", C.ERROR)
                return
            _recent_snips.appendleft(_SnipRecord(datetime.now(), text, image))
            _copy_text(text)
            _status("✓ Text copied")
            Toast.show_toast("Text copied", "📋")

        w.signals.success.connect(_ok)
        w.signals.error.connect(
            lambda e: (
                tip.close(),
                _status(f"❌ {e}"),
                Toast.show_toast(f"Error: {e}", "❌", C.ERROR),
            )
        )
        _pool().start(w)

    def _on_taken(rect: QRect, action: str, overlay: SnipOverlay):
        img = overlay.crop_selection(rect)
        vgeo = (
            QGuiApplication.screens()[0].virtualGeometry()
            if QGuiApplication.screens()
            else QRect()
        )
        anchor = QPoint(rect.right() + vgeo.x(), rect.bottom() + vgeo.y())
        QTimer.singleShot(50, lambda: _handle(action, img, anchor))

    if nexus and hasattr(nexus, "hide"):
        nexus.hide()
    QTimer.singleShot(
        150,
        lambda: (
            data := _capture_virtual_desktop(),
            ov := SnipOverlay(data[0], data[1]),
            ov.snip_taken.connect(lambda r, a: _on_taken(r, a, ov)),
            ov.show(),
            ov.raise_(),
            ov.activateWindow(),
            setattr(ov, "_ref", ov),
        ),
    )


def get_recent_snips() -> list[_SnipRecord]:
    """Return up to the last 10 snip records (newest first)."""
    return list(_recent_snips)
