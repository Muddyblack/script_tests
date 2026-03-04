"""Snip overlay: language bar, selection handles, loupe, toolbar."""
from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
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
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from src.common.theme import ThemeManager

from . import _settings as S
from ._colors import C, _c_rgba

# ── Constants ──────────────────────────────────────────────────────────────

_LOUPE_PX = 200
_LOUPE_ZOOM = 6
_HANDLE_SIZE = 10

# ── Language bar ───────────────────────────────────────────────────────────

_LANG_BTN_BASE = (
    "QPushButton {{ background: {bg}; color: {fg}; "
    "border: 1px solid {bd}; border-radius: 4px; "
    "font: bold 8pt 'Segoe UI'; }}"
    "QPushButton:hover {{ background: {hv}; }}"
)

_AVAILABLE_LANGS = [("EN", "en"), ("DE", "de"), ("FR", "fr"), ("ES", "es")]


class LangBar(QWidget):
    """Persistent language toggle strip shown in the overlay / dialog top-right."""

    def __init__(self, parent: QWidget) -> None:
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
        if S.ocr_code_mode:
            S.ocr_code_mode = False
        if code in S.ocr_langs:
            if len(S.ocr_langs) > 1:
                S.ocr_langs = [c for c in S.ocr_langs if c != code]
        else:
            S.ocr_langs = [*S.ocr_langs, code]
        self._refresh_styles()
        S.save_ocr_settings()
        self._prewarm()

    def _toggle_code(self) -> None:
        S.ocr_code_mode = not S.ocr_code_mode
        if S.ocr_code_mode:
            S.ocr_langs = ["en"]
        self._refresh_styles()
        S.save_ocr_settings()
        self._prewarm()

    def _toggle_symbol_priority(self) -> None:
        S.ocr_symbol_priority = not S.ocr_symbol_priority
        self._refresh_styles()
        S.save_ocr_settings()

    def _toggle_code_fix(self) -> None:
        S.ocr_code_fix = not S.ocr_code_fix
        self._refresh_styles()
        S.save_ocr_settings()

    @staticmethod
    def _prewarm() -> None:
        from .extractor import pre_warm

        pre_warm(["en"] if S.ocr_code_mode else S.ocr_langs)

    # ------------------------------------------------------------------
    def _refresh_styles(self) -> None:
        mgr = ThemeManager()
        is_dark = mgr.is_dark

        inactive_bg = _c_rgba(mgr, "text_primary", 15 if is_dark else 10)
        inactive_fg = _c_rgba(mgr, "text_primary", 120 if is_dark else 140)
        inactive_bd = _c_rgba(mgr, "text_primary", 25 if is_dark else 20)
        hover_bg = _c_rgba(mgr, "text_primary", 35 if is_dark else 30)

        for code, btn in self._btns.items():
            active = code in S.ocr_langs and not S.ocr_code_mode
            btn.setStyleSheet(
                _LANG_BTN_BASE.format(
                    bg="#6366f1" if active else inactive_bg,
                    fg="#ffffff" if active else inactive_fg,
                    bd="#6366f1" if active else inactive_bd,
                    hv="#7c7ff1" if active else hover_bg,
                )
            )
        ca = S.ocr_code_mode
        self._code_btn.setStyleSheet(
            _LANG_BTN_BASE.format(
                bg="#06b6d4" if ca else inactive_bg,
                fg="#ffffff" if ca else inactive_fg,
                bd="#06b6d4" if ca else inactive_bd,
                hv="#22d3ee" if ca else hover_bg,
            )
        )
        sa = S.ocr_symbol_priority
        self._sym_btn.setStyleSheet(
            _LANG_BTN_BASE.format(
                bg="#f59e0b" if sa else inactive_bg,
                fg="#ffffff" if sa else inactive_fg,
                bd="#f59e0b" if sa else inactive_bd,
                hv="#fbbf24" if sa else hover_bg,
            )
        )
        fa = S.ocr_code_fix
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


# ── Toolbar button style ───────────────────────────────────────────────────

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

# ── Overlay state ──────────────────────────────────────────────────────────


class OverlayState(Enum):
    IDLE = auto()
    DRAWING = auto()
    SELECTED = auto()
    RESIZING = auto()
    MOVING = auto()


# ── SnipOverlay ────────────────────────────────────────────────────────────


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

    def __init__(self, desktop: QPixmap, virtual_geo: QRect) -> None:
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

        # Language bar — place in the top-right of the active screen (under cursor)
        self._lang_bar = LangBar(self)
        self._lang_bar.adjustSize()
        try:
            cursor_pos = QCursor.pos()
            screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
            if screen is not None:
                s_geo = screen.geometry()
                x = s_geo.x() - virtual_geo.x() + (s_geo.width() - self._lang_bar.width() - 12)
                y = s_geo.y() - virtual_geo.y() + 12
            else:
                x = virtual_geo.width() - self._lang_bar.width() - 12
                y = 12
        except Exception:
            x = virtual_geo.width() - self._lang_bar.width() - 12
            y = 12

        self._lang_bar.move(int(x), int(y))
        self._lang_bar.raise_()
        self._lang_bar.show()

    def keyPressEvent(self, ev) -> None:
        key = ev.key()
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

    def mousePressEvent(self, ev) -> None:
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

    def mouseMoveEvent(self, ev) -> None:
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

    def mouseReleaseEvent(self, ev) -> None:
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

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.drawPixmap(0, 0, self._desktop)

        if not self._rect.isNull():
            sel_rect = self._rect.normalized()
            path = QPainterPath()
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

    def _draw_handles(self, p: QPainter, r: QRect) -> None:
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
                int(dst.left() + i * cell), dst.top(),
                int(dst.left() + i * cell), dst.bottom(),
            )
            p.drawLine(
                dst.left(), int(dst.top() + i * cell),
                dst.right(), int(dst.top() + i * cell),
            )
        p.restore()

        p.setPen(QPen(QColor(255, 255, 255, 200), 2))
        p.drawEllipse(dst)
        p.setPen(QPen(C.ACCENT_LITE, 1))
        p.drawLine(
            dst.center().x() - 12, dst.center().y(),
            dst.center().x() + 12, dst.center().y(),
        )
        p.drawLine(
            dst.center().x(), dst.center().y() - 12,
            dst.center().x(), dst.center().y() + 12,
        )

    def _paint_hint_bar(self, p: QPainter) -> None:
        p.fillRect(0, 0, self.width(), 36, QColor(0, 0, 0, 180))
        p.setPen(QColor(255, 255, 255, 220))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(20, 23, "Drag to select region  ·  1-7: Shortcuts  ·  Esc: Cancel")

    def crop_selection(self, rect: QRect) -> QImage:
        return self._desktop.copy(rect).toImage()
