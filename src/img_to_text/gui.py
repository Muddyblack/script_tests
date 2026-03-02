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
    QSize,
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
    QIcon,
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
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.common.config import APPDATA as _APPDATA
from src.common.config import OCR_ICON_PATH
from src.common.theme import ThemeManager, apply_win32_titlebar

from .extractor import ocr_qimage_with_meta

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

_OCR_SETTINGS_FILE = Path(_APPDATA) / "nexus_ocr_settings.json"

# Mutable globals — modified by _LangBar at runtime
_ocr_langs: list[str] = ["en", "de"]
_ocr_code_mode: bool = False
_ocr_symbol_priority: bool = False
_ocr_code_fix: bool = False


def _load_ocr_settings() -> None:
    global _ocr_langs, _ocr_code_mode, _ocr_symbol_priority, _ocr_code_fix
    with contextlib.suppress(Exception):
        data = json.loads(_OCR_SETTINGS_FILE.read_text(encoding="utf-8"))
        _ocr_langs = data.get("languages", ["en", "de"])
        _ocr_code_mode = bool(data.get("code_mode", False))
        _ocr_symbol_priority = bool(data.get("symbol_priority", False))
        _ocr_code_fix = bool(data.get("code_fix", False))


def _save_ocr_settings() -> None:
    with contextlib.suppress(Exception):
        _OCR_SETTINGS_FILE.write_text(
            json.dumps(
                {
                    "languages": _ocr_langs,
                    "code_mode": _ocr_code_mode,
                    "symbol_priority": _ocr_symbol_priority,
                    "code_fix": _ocr_code_fix,
                }
            ),
            encoding="utf-8",
        )


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
        self._set_theme_style()
        ThemeManager().theme_changed.connect(self._set_theme_style)
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

        self._fix_btn = QPushButton("Fix", self)
        self._fix_btn.setFixedSize(36, 24)
        self._fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fix_btn.setToolTip(
            "Apply code-focused OCR fixes (l/1, O/0, symbol spacing)"
        )
        self._fix_btn.clicked.connect(self._toggle_code_fix)
        lay.addWidget(self._fix_btn)

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

    def _toggle_code_fix(self) -> None:
        global _ocr_code_fix
        _ocr_code_fix = not _ocr_code_fix
        self._refresh_styles()
        _save_ocr_settings()

    @staticmethod
    def _prewarm() -> None:
        from .extractor import pre_warm

        pre_warm(["en"] if _ocr_code_mode else _ocr_langs)

    # ------------------------------------------------------------------
    def _refresh_styles(self) -> None:
        mgr = ThemeManager()
        is_dark = mgr.is_dark

        # Base colors for inactive state
        inactive_bg = _c_rgba(mgr, "text_primary", 15 if is_dark else 10)
        inactive_fg = _c_rgba(mgr, "text_primary", 120 if is_dark else 140)
        inactive_bd = _c_rgba(mgr, "text_primary", 25 if is_dark else 20)
        hover_bg = _c_rgba(mgr, "text_primary", 35 if is_dark else 30)

        for code, btn in self._btns.items():
            active = code in _ocr_langs and not _ocr_code_mode
            btn.setStyleSheet(
                _LANG_BTN_BASE.format(
                    bg="#6366f1" if active else inactive_bg,
                    fg="#ffffff" if active else inactive_fg,
                    bd="#6366f1" if active else inactive_bd,
                    hv="#7c7ff1" if active else hover_bg,
                )
            )
        ca = _ocr_code_mode
        self._code_btn.setStyleSheet(
            _LANG_BTN_BASE.format(
                bg="#06b6d4" if ca else inactive_bg,
                fg="#ffffff" if ca else inactive_fg,
                bd="#06b6d4" if ca else inactive_bd,
                hv="#22d3ee" if ca else hover_bg,
            )
        )
        sa = _ocr_symbol_priority
        self._sym_btn.setStyleSheet(
            _LANG_BTN_BASE.format(
                bg="#f59e0b" if sa else inactive_bg,
                fg="#ffffff" if sa else inactive_fg,
                bd="#f59e0b" if sa else inactive_bd,
                hv="#fbbf24" if sa else hover_bg,
            )
        )
        fa = _ocr_code_fix
        self._fix_btn.setStyleSheet(
            _LANG_BTN_BASE.format(
                bg="#10b981" if fa else inactive_bg,
                fg="#ffffff" if fa else inactive_fg,
                bd="#10b981" if fa else inactive_bd,
                hv="#34d399" if fa else hover_bg,
            )
        )

    def _set_theme_style(self) -> None:
        mgr = ThemeManager()
        self.setStyleSheet(
            f"background: {mgr['bg_elevated'] if mgr.is_dark else mgr['bg_base']};"
            " border-radius: 7px;"
            f" border: 1px solid {mgr['border']};"
        )


_TOOLBAR_BTN_STYLE = """
QPushButton {{
    background: {bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: 7px;
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
        ("🧷", "3: OCR 1L", "text_one_line", "#7c3aed"),
        ("🖼️", "4: Image", "image", "#8b5cf6"),
        ("💾", "5: Save", "save", "#3b82f6"),
        ("📤", "6: Share", "share", "#06b6d4"),
        ("❌", "7: Cancel", "cancel", "#ef4444"),
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
        mgr = ThemeManager()
        bg = mgr["bg_elevated"]
        fg = mgr["text_primary"]
        border = mgr["border"]

        if not self._toolbar_btns:
            for icon, label, action, color in self._TOOLBAR:
                btn = QPushButton(f"{icon}  {label}", self)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedHeight(30)
                btn.setStyleSheet(
                    _TOOLBAR_BTN_STYLE.format(color=color, bg=bg, fg=fg, border=border)
                )
                btn.clicked.connect(lambda _, a=action: self._on_action(a))
                self._toolbar_btns.append(btn)
        else:
            # Update existing buttons in case theme changed
            for btn, (_, _, _, color) in zip(
                self._toolbar_btns, self._TOOLBAR, strict=True
            ):
                btn.setStyleSheet(
                    _TOOLBAR_BTN_STYLE.format(color=color, bg=bg, fg=fg, border=border)
                )

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
        p.drawText(20, 23, "Drag to select region  ·  1-7: Shortcuts  ·  Esc: Cancel")

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


# Transparent padding around the visible box (for glow bleed).
_TOAST_GLOW = 10


class Toast(QWidget):
    def __init__(
        self,
        message: str,
        icon: str = "✓",
        color: QColor = None,
        duration_ms: int = 2500,
    ):
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

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = _TOAST_GLOW
        box = self.rect().adjusted(g, g, -g, -g)  # visible card rect

        # ── glass card background ──────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        # dark base layer
        p.setBrush(QColor(15, 12, 28, 175))
        p.drawRoundedRect(box, 12, 12)
        # white frost layer (glass illusion)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(box, 12, 12)
        # subtle accent tint overlay
        tint = QColor(self._color)
        tint.setAlpha(30)
        p.setBrush(tint)
        p.drawRoundedRect(box, 12, 12)

        # ── border ────────────────────────────────────────────────────────
        border = QColor(self._color)
        border.setAlpha(220)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(border, 1.8))
        p.drawRoundedRect(box.adjusted(1, 1, -1, -1), 11, 11)

        # ── left accent stripe ─────────────────────────────────────────────
        stripe_h = box.height() - 20
        stripe = QRectF(box.left() + 7, box.top() + 10, 3.5, stripe_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawRoundedRect(stripe, 2, 2)

        p.end()

    @staticmethod
    def show_toast(
        msg: str, icon: str = "✓", color: QColor = None, duration_ms: int = 2500
    ):
        t = Toast(msg, icon, color or C.ACCENT, duration_ms)
        t.show()
        t._ref = t


_TT_GLOW = 10


class OcrPreviewTooltip(QWidget):
    def __init__(self, anchor: QPoint):
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
        # Keep a stable width to avoid aggressive reflow/geometry warnings on Win32.
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

    def paintEvent(self, event):  # noqa: N802
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
        # Re-clamp in case updated text changed tooltip height.
        x = min(self.x(), self._screen_geo.right() - self.width() - 8)
        x = max(self._screen_geo.left() + 8, x)
        y = min(self.y(), self._screen_geo.bottom() - self.height() - 8)
        y = max(self._screen_geo.top() + 8, y)
        self.move(x, y)
        QTimer.singleShot(4000, self.close)


class _Signals(QObject):
    success = pyqtSignal(object)
    error = pyqtSignal(str)


class _OcrWorker(QRunnable):
    def __init__(
        self,
        image: QImage,
        raw_output: bool = False,
        languages: list[str] | None = None,
        symbol_priority: bool = False,
        one_line_output: bool = False,
        code_fix: bool = False,
    ):
        super().__init__()
        self.image = image
        self.raw_output = raw_output
        self.languages = languages or list(_ocr_langs)
        self.symbol_priority = symbol_priority
        self.one_line_output = one_line_output
        self.code_fix = code_fix
        self.signals = _Signals()

    def run(self):
        try:
            self.signals.success.emit(
                ocr_qimage_with_meta(
                    self.image,
                    languages=self.languages,
                    raw_output=self.raw_output,
                    symbol_priority=self.symbol_priority,
                    one_line_output=self.one_line_output,
                    code_fix=self.code_fix,
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
        one_line_mode = action == "text_one_line"
        # Snapshot language selection at the moment of capture
        langs = ["en"] if _ocr_code_mode else list(_ocr_langs)
        symbol_mode = _ocr_symbol_priority
        code_fix_mode = _ocr_code_fix
        mode_label = "(code)" if _ocr_code_mode else f"({'+'.join(langs)})"
        if symbol_mode:
            mode_label = f"{mode_label}+sym"
        if code_fix_mode:
            mode_label = f"{mode_label}+fix"
        _status(f"⏳ Recognising {mode_label}…")
        tip = OcrPreviewTooltip(anchor)
        tip.show()
        w = _OcrWorker(
            image,
            raw_output=raw_mode,
            languages=langs,
            symbol_priority=symbol_mode,
            one_line_output=one_line_mode,
            code_fix=code_fix_mode,
        )

        def _ok(payload: object):
            if isinstance(payload, dict):
                text = str(payload.get("text", ""))
                confidence = float(payload.get("confidence", 0.0))
            else:
                text = str(payload or "")
                confidence = 0.0

            tip.set_text(text, confidence)
            if not text:
                _status("⚠️ No text")
                Toast.show_toast("No text", "⚠️", C.ERROR)
                return
            _recent_snips.appendleft(_SnipRecord(datetime.now(), text, image))
            _copy_text(text)
            if confidence > 0:
                _status(f"✓ Text copied ({int(confidence * 100)}%)")
            else:
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


# ══════════════════════════════════════════════════════════════════════════════
#  Image-upload OCR  (drag-drop / file-open / clipboard-paste)
# ══════════════════════════════════════════════════════════════════════════════


def _c_rgba(mgr, key: str, alpha: int) -> str:
    """Helper to get theme color with specific alpha."""
    hex_col = mgr[key]
    h = hex_col.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_col


_UPLOAD_BTN_STYLE = """
QPushButton {{
    background: {bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 0 14px;
    font: 9pt 'Segoe UI';
}}
QPushButton:hover {{
    background: {hover};
    border-color: {hover};
    color: #fff;
}}
QPushButton:disabled {{
    background: {bg_dis};
    color: {fg_dis};
    border-color: {border_dis};
}}
"""


class _DropImageArea(QLabel):
    """Click-to-open / drag-drop / paste image zone with live preview."""

    image_ready = pyqtSignal(QImage)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._current_image: QImage | None = None
        self._IDLE_STYLE = ""
        self._HOVER_STYLE = ""
        self._LOADED_STYLE = ""
        self._set_idle()

    # ------------------------------------------------------------------
    def _set_idle(self) -> None:
        self._current_image = None
        self.setText(
            "📂  Drop image here\n   or click to open file\n   or Ctrl+V to paste"
        )
        self.setStyleSheet(self._IDLE_STYLE)
        self.setPixmap(QPixmap())  # clear any pixmap

    def set_image(self, image: QImage) -> None:
        self._current_image = image
        self._refresh_preview()
        self.setStyleSheet(self._LOADED_STYLE)

    def current_image(self) -> QImage | None:
        return self._current_image

    def _refresh_preview(self) -> None:
        if self._current_image is None:
            return
        avail = self.size() - QSize(20, 20)
        if avail.width() <= 0 or avail.height() <= 0:
            return
        pm = QPixmap.fromImage(self._current_image).scaled(
            avail,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pm)

    # ------------------------------------------------------------------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._open_file_dialog()

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif *.webp)",
        )
        if not path:
            return
        img = QImage(path)
        if not img.isNull():
            self.set_image(img)
            self.image_ready.emit(img)

    # ------------------------------------------------------------------
    def dragEnterEvent(self, ev):
        md = ev.mimeData()
        if md.hasUrls() or md.hasImage():
            ev.acceptProposedAction()
            self.setStyleSheet(self._HOVER_STYLE)

    def dragLeaveEvent(self, ev):
        if self._current_image:
            self.setStyleSheet(self._LOADED_STYLE)
        else:
            self.setStyleSheet(self._IDLE_STYLE)

    def dragMoveEvent(self, ev):
        ev.acceptProposedAction()

    def dropEvent(self, ev):
        md = ev.mimeData()
        img: QImage | None = None

        if md.hasUrls():
            for url in md.urls():
                local = url.toLocalFile()
                if local:
                    candidate = QImage(local)
                    if not candidate.isNull():
                        img = candidate
                        break

        if img is None and md.hasImage():
            raw = md.imageData()
            if raw:
                candidate = QImage(raw)
                if not candidate.isNull():
                    img = candidate

        if img:
            self.set_image(img)
            self.image_ready.emit(img)
            ev.acceptProposedAction()
        else:
            if self._current_image:
                self.setStyleSheet(self._LOADED_STYLE)
            else:
                self._set_idle()

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._refresh_preview()

    def _apply_theme(self) -> None:
        mgr = ThemeManager()
        bg_val = mgr["bg_overlay"] if mgr.is_dark else mgr["bg_elevated"]
        accent = mgr["accent"]
        text_dim = mgr["text_secondary"]
        border = mgr["border"]

        self._IDLE_STYLE = (
            f"background: {bg_val};"
            f" border: 2px dashed {border};"
            " border-radius: 10px;"
            f" color: {text_dim};"
            " font: 11pt 'Segoe UI';"
        )
        self._HOVER_STYLE = (
            f"background: {bg_val}; border: 2px solid {accent}; border-radius: 10px;"
        )
        self._LOADED_STYLE = (
            f"background: {mgr['bg_base']}; border: 2px solid {border};"
            " border-radius: 10px;"
        )
        if not self._current_image:
            self.setStyleSheet(self._IDLE_STYLE)
        else:
            self.setStyleSheet(self._LOADED_STYLE)
            self._refresh_preview()


# ══════════════════════════════════════════════════════════════════════════════
#  ImageOcrDialog
# ══════════════════════════════════════════════════════════════════════════════

_DIALOG_BG = "rgba(13,13,23,0.98)"


class ImageOcrDialog(QWidget):
    """Standalone OCR window — open any image file, drag-drop, or paste to extract text."""

    def __init__(self, *, nexus=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._nexus = nexus
        self._current_image: QImage | None = None
        self._ocr_running = False

        self.setWindowTitle("Image → Text  (OCR)")
        if os.path.exists(OCR_ICON_PATH):
            self.setWindowIcon(QIcon(OCR_ICON_PATH))

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(980, 640)

        self._build_ui()
        self._apply_theme()

        # Listen for theme changes
        ThemeManager().theme_changed.connect(self._apply_theme)

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Re-apply Win32 caption color once the window is actually visible
        mgr = ThemeManager()
        apply_win32_titlebar(int(self.winId()), mgr["bg_base"], mgr.is_dark)

    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        mgr = ThemeManager()
        bg = mgr["bg_base"]
        text_col = mgr["text_primary"]
        text_sec = mgr["text_secondary"]
        border = mgr["border"]
        is_dark = mgr.is_dark

        # Translucent overlays based on mode
        ov_sm = _c_rgba(mgr, "text_primary", 15 if is_dark else 10)
        ov_md = _c_rgba(mgr, "text_primary", 25 if is_dark else 20)
        scrl = _c_rgba(mgr, "text_primary", 30 if is_dark else 40)
        scrl_h = _c_rgba(mgr, "text_primary", 60 if is_dark else 80)

        # Main window style
        self.setStyleSheet(
            f"ImageOcrDialog {{ background: {bg}; color: {text_col}; }}"
            f"QLabel {{ background: transparent; color: {text_col}; }}"
        )

        # Update Win32 titlebar
        apply_win32_titlebar(int(self.winId()), bg, is_dark)

        # Button style parameters
        btn_bg = ov_sm
        btn_fg = text_sec
        btn_border = ov_md
        btn_dis_bg = _c_rgba(mgr, "text_primary", 8)
        btn_dis_fg = _c_rgba(mgr, "text_primary", 40)

        common_params = {
            "bg": btn_bg,
            "fg": btn_fg,
            "border": btn_border,
            "bg_dis": btn_dis_bg,
            "fg_dis": btn_dis_fg,
            "border_dis": btn_dis_bg,
        }

        self._open_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["accent"], **common_params)
        )
        self._paste_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["accent_pressed"], **common_params)
        )
        self._run_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["success"], **common_params)
        )
        self._copy_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["accent"], **common_params)
        )
        self._save_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["accent_pressed"], **common_params)
        )
        self._clear_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["danger"], **common_params)
        )

        self._text_edit.setStyleSheet(
            f"QTextEdit {{"
            f" background: {ov_sm};"
            f" border: 1px solid {border};"
            f" border-radius: 8px;"
            f" color: {text_col}; font: 10pt 'Consolas', 'Courier New';"
            f" padding: 8px;"
            f"}}"
            f"QScrollBar:vertical {{ background: transparent; width: 6px; }}"
            f"QScrollBar::handle:vertical {{ background: {scrl}; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {scrl_h}; }}"
        )

        # Update lang bar if it has its own style
        self._lang_bar.setStyleSheet(
            f"background: {mgr['bg_elevated']}; border-radius: 7px;"
            f" border: 1px solid {border};"
        )

        # Update drop area
        self._img_area._apply_theme()

        # Update header
        self._result_hdr.setStyleSheet(
            f"font: bold 9pt 'Segoe UI'; color: {mgr['text_secondary']};"
        )

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(10)

        # ── Top toolbar ──────────────────────────────────────────────
        tbar = QHBoxLayout()
        tbar.setSpacing(6)

        self._open_btn = QPushButton("📂  Open File")
        self._open_btn.setFixedHeight(32)
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self._open_file)

        self._paste_btn = QPushButton("📋  Paste  (Ctrl+V)")
        self._paste_btn.setFixedHeight(32)
        self._paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paste_btn.clicked.connect(self._paste_image)

        self._run_btn = QPushButton("▶  Run OCR")
        self._run_btn.setFixedHeight(32)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_ocr)

        # Compact lang buttons inline
        self._lang_bar = _LangBar(self)

        tbar.addWidget(self._open_btn)
        tbar.addWidget(self._paste_btn)
        tbar.addSpacing(8)
        tbar.addWidget(self._lang_bar)
        tbar.addStretch()
        tbar.addWidget(self._run_btn)
        root.addLayout(tbar)

        # ── Main split: image ◀ | ▶ text ────────────────────────────
        split = QHBoxLayout()
        split.setSpacing(12)

        # Left — image drop zone
        self._img_area = _DropImageArea(self)
        self._img_area.image_ready.connect(self._on_image_loaded)
        split.addWidget(self._img_area, 1)

        right_root = QVBoxLayout()
        right_root.setSpacing(6)

        self._result_hdr = QLabel("Extracted Text")
        right_root.addWidget(self._result_hdr)

        self._text_edit = QTextEdit(self)
        self._text_edit.setPlaceholderText("OCR result will appear here…")
        self._text_edit.setMinimumWidth(300)
        right_root.addWidget(self._text_edit, 1)

        # Action buttons under text area
        act_row = QHBoxLayout()
        act_row.setSpacing(6)

        self._copy_btn = QPushButton("📋  Copy Text")
        self._copy_btn.setFixedHeight(30)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(self._copy_text)

        self._save_btn = QPushButton("💾  Save Text")
        self._save_btn.setFixedHeight(30)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.clicked.connect(self._save_text)

        self._clear_btn = QPushButton("✕  Clear")
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_all)

        act_row.addWidget(self._copy_btn)
        act_row.addWidget(self._save_btn)
        act_row.addStretch()
        act_row.addWidget(self._clear_btn)
        right_root.addLayout(act_row)

        right_container = QWidget(self)
        right_container.setLayout(right_root)
        right_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        split.addWidget(right_container, 1)

        root.addLayout(split, 1)

        # ── Status bar ───────────────────────────────────────────────
        self._status = QLabel(
            "Open or drop an image to begin  ·  supports PNG, JPG, BMP, TIFF, WebP"
        )
        self._status.setStyleSheet(
            "color: rgba(255,255,255,0.28); font: 8pt 'Segoe UI';"
        )
        root.addWidget(self._status)

    # ------------------------------------------------------------------
    def keyPressEvent(self, ev):
        key, mods = ev.key(), ev.modifiers()
        ctrl = Qt.KeyboardModifier.ControlModifier
        if key == Qt.Key.Key_V and mods == ctrl:
            self._paste_image()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and mods == ctrl:
            self._run_ocr()
        elif key == Qt.Key.Key_O and mods == ctrl:
            self._open_file()
        else:
            super().keyPressEvent(ev)

    # ------------------------------------------------------------------
    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.repaint()

    def _open_file(self) -> None:
        self._img_area._open_file_dialog()

    def _paste_image(self) -> None:
        img = QApplication.clipboard().image()
        if img and not img.isNull():
            self._img_area.set_image(img)
            self._on_image_loaded(img)
        else:
            Toast.show_toast("No image in clipboard", "⚠️", C.WARNING)

    def _on_image_loaded(self, img: QImage) -> None:
        self._current_image = img
        self._run_btn.setEnabled(True)
        w, h = img.width(), img.height()
        self._set_status(f"Image loaded  ·  {w} × {h} px  ·  Ctrl+Enter to run OCR")
        # Auto-run immediately
        self._run_ocr()

    def _run_ocr(self) -> None:
        if self._current_image is None or self._ocr_running:
            return
        self._ocr_running = True
        self._run_btn.setEnabled(False)

        langs = ["en"] if _ocr_code_mode else list(_ocr_langs)
        mode_label = "(code)" if _ocr_code_mode else f"({'+'.join(langs)})"
        self._set_status(f"⏳  Recognising {mode_label}…")

        pool = (
            self._nexus.thread_pool
            if self._nexus and hasattr(self._nexus, "thread_pool")
            else QThreadPool.globalInstance()
        )
        worker = _OcrWorker(
            self._current_image,
            languages=langs,
            symbol_priority=_ocr_symbol_priority,
            code_fix=_ocr_code_fix,
        )

        def _ok(payload):
            self._ocr_running = False
            self._run_btn.setEnabled(True)
            if isinstance(payload, dict):
                text = str(payload.get("text", ""))
                conf = float(payload.get("confidence", 0.0))
            else:
                text = str(payload or "")
                conf = 0.0
            self._text_edit.setPlainText(text)
            if text:
                conf_str = f"  ·  confidence {int(conf * 100)}%" if conf > 0 else ""
                self._set_status(
                    f"✓  OCR complete{conf_str}  ·  text copied to clipboard"
                )
                _copy_text(text)
                Toast.show_toast("Text copied", "📋")
            else:
                self._set_status("⚠️  No text detected")
                Toast.show_toast("No text detected", "⚠️", C.WARNING)

        def _err(e: str):
            self._ocr_running = False
            self._run_btn.setEnabled(True)
            self._set_status(f"❌  {e}")
            Toast.show_toast(f"OCR error: {e}", "❌", C.ERROR)

        worker.signals.success.connect(_ok)
        worker.signals.error.connect(_err)
        pool.start(worker)

    def _copy_text(self) -> None:
        text = self._text_edit.toPlainText()
        if text.strip():
            _copy_text(text)
            Toast.show_toast("Text copied", "📋")
        else:
            Toast.show_toast("Nothing to copy", "⚠️", C.WARNING)

    def _save_text(self) -> None:
        text = self._text_edit.toPlainText()
        if not text.strip():
            Toast.show_toast("Nothing to save", "⚠️", C.WARNING)
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save OCR Text",
            str(Path.home() / f"ocr_{ts}.txt"),
            "Text files (*.txt);;All files (*)",
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            Toast.show_toast("Saved", "💾", C.SUCCESS)

    def _clear_all(self) -> None:
        self._current_image = None
        self._img_area._set_idle()
        self._img_area.clear()
        self._img_area._set_idle()
        self._text_edit.clear()
        self._run_btn.setEnabled(False)
        self._set_status(
            "Open or drop an image to begin  ·  supports PNG, JPG, BMP, TIFF, WebP"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Public entry-point
# ══════════════════════════════════════════════════════════════════════════════


def start_file_to_text(*, nexus=None) -> ImageOcrDialog:
    """Open the Image OCR dialog (file-open / drag-drop / paste mode)."""
    dlg = ImageOcrDialog(nexus=nexus)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    dlg._ref = dlg  # keep alive
    return dlg
