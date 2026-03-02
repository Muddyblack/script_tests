"""Auto-split module."""

import shutil

from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.xexplorer.icons import Icons
from src.xexplorer.theme import Theme


class RibbonBtn(QWidget):
    clicked = pyqtSignal()

    def __init__(self, pixmap: QPixmap, label: str, theme: Theme, parent=None):
        super().__init__(parent)
        self._px = pixmap
        self._label = label
        self._theme = theme
        self._hov = False
        self._pressed = False
        self.setFixedSize(56, 52)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def setPixmap(self, px):
        self._px = px
        self.update()

    def enterEvent(self, e):
        self._hov = True
        self.update()

    def leaveEvent(self, e):
        self._hov = False
        self._pressed = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(e.pos()):
                self.clicked.emit()

    def paintEvent(self, e):
        T = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        if self._pressed:
            p.setBrush(QBrush(QColor(T["bg_control_prs"])))
            p.setPen(QPen(QColor(T["border"]), 1))
            p.drawRoundedRect(r, 4, 4)
        elif self._hov:
            p.setBrush(QBrush(QColor(T["bg_control_hov"])))
            p.setPen(QPen(QColor(T["border"]), 1))
            p.drawRoundedRect(r, 4, 4)
        # Icon
        if self._px:
            ix = (self.width() - 20) // 2
            p.drawPixmap(ix, 6, 20, 20, self._px)
        # Label
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        p.setPen(QColor(T["text_secondary"]))
        p.drawText(
            QRect(0, 28, self.width(), 18),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._label,
        )
        p.end()


#  ICON-ONLY NAV BUTTON  (back / forward / up / refresh)


class NavBtn(QWidget):
    clicked = pyqtSignal()

    def __init__(self, pixmap: QPixmap, theme: Theme, tooltip="", parent=None):
        super().__init__(parent)
        self._px = pixmap
        self._theme = theme
        self._hov = False
        self._pressed = False
        self.setFixedSize(30, 30)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if tooltip:
            self.setToolTip(tooltip)

    def setPixmap(self, px):
        self._px = px
        self.update()

    def enterEvent(self, e):
        self._hov = True
        self.update()

    def leaveEvent(self, e):
        self._hov = False
        self._pressed = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(e.pos()):
                self.clicked.emit()

    def paintEvent(self, e):
        T = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        if self._pressed:
            p.setBrush(QBrush(QColor(T["bg_control_prs"])))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(r, 4, 4)
        elif self._hov:
            p.setBrush(QBrush(QColor(T["bg_control_hov"])))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(r, 4, 4)
        if self._px:
            ix = (self.width() - 16) // 2
            iy = (self.height() - 16) // 2
            p.drawPixmap(ix, iy, 16, 16, self._px)
        p.end()


class SearchBar(QWidget):
    textChanged = pyqtSignal(str)

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._focused = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(16, 16)
        self._update_icon()
        layout.addWidget(self._icon_lbl)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Search files, folders, content…")
        self.input.setFrame(False)
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self.textChanged)
        self.input.installEventFilter(self)
        layout.addWidget(self.input)

        self._hint_lbl = QLabel("Ctrl+K")
        self._hint_lbl.setObjectName("search_hint")
        self._hint_lbl.setFixedSize(44, 18)
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hint_lbl)

        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.apply_input_style()

    def eventFilter(self, obj, event):
        if obj == self.input and event.type() in (
            event.Type.FocusIn,
            event.Type.FocusOut,
        ):
            self.update()
            self._hint_lbl.setVisible(not self.input.hasFocus())
        return super().eventFilter(obj, event)

    def _update_icon(self):
        px = Icons.search(self._theme["text_secondary"], 16)
        self._icon_lbl.setPixmap(px)

    def update_theme(self):
        self._update_icon()
        self.apply_input_style()
        self.update()

    def paintEvent(self, e):
        T = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        focused = self.input.hasFocus()
        r = self.rect().adjusted(1, 3, -1, -3)

        bg = QColor(
            T["bg_overlay"]
            if focused
            else (T["bg_elevated"] if T.dark else T["bg_control"])
        )
        border = QColor(T["accent"] if focused else T["border_light"])

        if focused:
            # Subtle glow
            glow = QColor(T["accent"])
            glow.setAlpha(40)
            p.setPen(QPen(glow, 4))
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 6, 6)

        p.setBrush(QBrush(bg))
        p.setPen(QPen(border, 1.2 if focused else 1))
        p.drawRoundedRect(r, 6, 6)
        p.end()

    def apply_input_style(self):
        T = self._theme
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {T["text_primary"]};
                font-family: 'Segoe UI', system-ui;
                font-size: 13px;
                selection-background-color: {T["accent"]};
            }}
        """)
        self._hint_lbl.setStyleSheet(f"""
            QLabel#search_hint {{
                background: {T["bg_control"]};
                color: {T["text_secondary"]};
                border: 1px solid {T["border_light"]};
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
            }}
        """)


#  SIDEBAR ITEM  (with optional selection indicator bar)


class SidebarList(QListWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(1)
        self.setUniformItemSizes(False)
        self.setMouseTracking(True)
        self.itemSelectionChanged.connect(self._sync_widget_states)
        self.update_style()

    def _widget_at(self, item):
        w = self.itemWidget(item)
        if isinstance(w, (DriveWidget, IgnoreItemWidget)):
            return w
        return None

    def _sync_widget_states(self):
        for i in range(self.count()):
            item = self.item(i)
            w = self._widget_at(item)
            if w:
                w.set_selected(item.isSelected())

    def mouseMoveEvent(self, e):
        item = self.itemAt(e.pos())
        for i in range(self.count()):
            it = self.item(i)
            w = self._widget_at(it)
            if w:
                w.set_hovered(it is item)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        for i in range(self.count()):
            w = self._widget_at(self.item(i))
            if w:
                w.set_hovered(False)
        super().leaveEvent(e)

    def update_style(self):
        T = self._theme
        self.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
                padding: 2px 0;
            }}
            QListWidget::item {{
                border-radius: 6px;
                padding: 0;
                background: transparent;
            }}
            QListWidget::item:hover {{ background: transparent; }}
            QListWidget::item:selected {{ background: transparent; }}
            QListWidget::indicator {{ width: 0; height: 0; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {T["border"]}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)


#  CHIP FILTER BUTTON


class ChipBtn(QPushButton):
    def __init__(self, text, theme: Theme, parent=None):
        super().__init__(text, parent)
        self._theme = theme
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(26)
        self.update_style()

    def update_style(self):
        T = self._theme
        self.setStyleSheet(f"""
            QPushButton {{
                background: {T["bg_control"]};
                border: 1px solid {T["border"]};
                border-radius: 13px;
                padding: 0 14px;
                color: {T["text_secondary"]};
                font-family: 'Segoe UI';
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {T["bg_control_hov"]};
                color: {T["text_primary"]};
            }}
            QPushButton:checked {{
                background: {T["accent"]};
                border-color: {T["accent"]};
                color: {T["text_on_accent"]};
                font-weight: 600;
            }}
        """)


# ─────────────────────────────────────────────────────────────────────────────
#  TOGGLE SWITCH
# ─────────────────────────────────────────────────────────────────────────────


class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    _W, _H = 34, 18

    def __init__(self, checked: bool = True, theme=None, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._theme = theme
        self.setFixedSize(self._W, self._H)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool):
        self._checked = val
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)

    def paintEvent(self, e):
        T = self._theme
        if not T:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = QColor(T["accent"] if self._checked else T["bg_control"])
        p.setBrush(QBrush(acc))
        p.setPen(QPen(QColor(T["border"]), 1))
        p.drawRoundedRect(
            0, 2, self._W, self._H - 4, (self._H - 4) // 2, (self._H - 4) // 2
        )
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(Qt.PenStyle.NoPen)
        thumb_x = self._W - self._H + 2 if self._checked else 2
        p.drawEllipse(thumb_x, 1, self._H - 2, self._H - 2)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  IGNORE ITEM WIDGET
# ─────────────────────────────────────────────────────────────────────────────


class IgnoreItemWidget(QWidget):
    stateChanged = pyqtSignal(bool)

    def __init__(self, text: str, checked: bool = True, theme=None, parent=None):
        super().__init__(parent)
        self._text = text
        self._theme = theme
        self._hovered = False
        self._selected = False
        hl = QHBoxLayout(self)
        hl.setContentsMargins(10, 0, 8, 0)
        hl.setSpacing(10)

        # Toggle on the LEFT
        self._toggle = ToggleSwitch(checked, theme)
        self._toggle.toggled.connect(self.stateChanged)
        hl.addWidget(self._toggle)

        self._lbl = QLabel(text)
        self._lbl.setObjectName("ignore_item_lbl")
        hl.addWidget(self._lbl, 1)

        self.setFixedHeight(32)
        # Transparent so the sidebar_frame background shows through correctly
        self.setStyleSheet("background: transparent;")

    def set_hovered(self, val: bool):
        if self._hovered != val:
            self._hovered = val
            self.update()

    def set_selected(self, val: bool):
        if self._selected != val:
            self._selected = val
            self.update()

    def paintEvent(self, e):
        T = self._theme
        if T is None:
            return super().paintEvent(e)
        if self._selected or self._hovered:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if self._selected:
                color = QColor(T["accent"])
                color.setAlpha(34)
            else:
                color = QColor(T["sidebar_hover"])
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect().adjusted(2, 1, -2, -1), 6, 6)
            p.end()

    def isChecked(self) -> bool:
        return self._toggle.isChecked()

    def text(self) -> str:
        return self._text

    def update_theme(self, theme):
        self._theme = theme
        self._toggle._theme = theme
        self._toggle.update()
        if theme:
            self._lbl.setStyleSheet(
                f"background: transparent; color: {theme['text_primary']}; font-size: 12px;"
            )


# ─────────────────────────────────────────────────────────────────────────────
#  DRIVE ITEM WIDGET
# ─────────────────────────────────────────────────────────────────────────────


class _LetterBadge(QWidget):
    def __init__(self, letter: str, theme=None, parent=None):
        super().__init__(parent)
        self._letter = letter
        self._theme = theme
        self.setFixedSize(32, 32)

    def paintEvent(self, e):
        T = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acc = QColor(T["accent"] if T else "#00d4a8")
        p.setBrush(QBrush(acc))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 32, 32, 6, 6)
        p.setPen(QColor(T["text_on_accent"] if T else "#0a1020"))
        f = QFont("Segoe UI", 13, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._letter)
        p.end()


class DriveWidget(QWidget):
    def __init__(self, path: str, label: str, theme=None, parent=None):
        super().__init__(parent)
        self._path = path
        self._theme = theme
        self._hovered = False
        self._selected = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(10)

        # For UNC paths (\\server\share) use the first letter of the server
        # name; for normal drive letters use the drive letter itself.
        _np = path.replace("/", "\\") if path else ""
        if _np.startswith("\\\\"):
            _server = _np[2:].split("\\")[0]
            letter = _server[0].upper() if _server else "N"
        else:
            letter = _np[0].upper() if _np else "?"
        self._badge = _LetterBadge(letter, theme)
        hl.addWidget(self._badge)

        vl = QVBoxLayout()
        vl.setSpacing(2)
        vl.setContentsMargins(0, 0, 0, 0)

        self._name_lbl = QLabel(label)
        self._name_lbl.setObjectName("drive_name_lbl")
        vl.addWidget(self._name_lbl)

        try:
            total, used, _ = shutil.disk_usage(path)
        except Exception:
            total, used = 0, 0

        self._used = used
        self._total = total
        self._has_bar = total > 0
        if self._has_bar:
            used_gb = used / (1024**3)
            total_gb = total / (1024**3)
            self._size_lbl = QLabel(f"{used_gb:.1f} GB / {total_gb:.1f} GB")
        else:
            self._size_lbl = QLabel("")
        self._size_lbl.setObjectName("drive_size_lbl")
        vl.addWidget(self._size_lbl)

        # Reserve space for the drawn bar (no QProgressBar — it doesn't resize correctly)
        if self._has_bar:
            spacer = QWidget()
            spacer.setFixedHeight(6)
            vl.addWidget(spacer)

        hl.addLayout(vl, 1)
        self.setFixedHeight(66)
        self._apply_style()

    def set_hovered(self, val: bool):
        if self._hovered != val:
            self._hovered = val
            self.update()

    def set_selected(self, val: bool):
        if self._selected != val:
            self._selected = val
            self.update()

    def paintEvent(self, e):
        T = self._theme
        if T is None:
            return super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Hover / selection background
        if self._selected or self._hovered:
            if self._selected:
                color = QColor(T["accent"])
                color.setAlpha(34)
            else:
                color = QColor(T["sidebar_hover"])
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect().adjusted(2, 1, -2, -1), 6, 6)

        # Usage bar — drawn directly so it always matches the current widget width
        if self._has_bar and self._total > 0:
            # Position: same left/right margins as the layout, just above bottom edge
            ml, mr = 12 + 32 + 10, 12  # badge(32) + spacing(10) + left margin(12)
            bar_x = ml
            bar_w = self.width() - ml - mr
            bar_y = self.height() - 10
            bar_h = 3
            ratio = min(self._used / self._total, 1.0)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(T["border"])))
            p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 1, 1)
            if ratio > 0:
                p.setBrush(QBrush(QColor(T["accent"])))
                p.drawRoundedRect(bar_x, bar_y, max(4, int(bar_w * ratio)), bar_h, 1, 1)

        p.end()

    def _apply_style(self):
        T = self._theme
        if T is None:
            return
        # Transparent so the sidebar_frame background shows through correctly
        self.setStyleSheet("background: transparent;")
        self._name_lbl.setStyleSheet(
            f"background: transparent; color: {T['text_primary']}; font-size: 13px; font-weight: 600;"
        )
        self._size_lbl.setStyleSheet(f"background: transparent; color: {T['text_secondary']}; font-size: 11px;")

    def update_theme(self, theme):
        self._theme = theme
        self._badge._theme = theme
        self._badge.update()
        self._apply_style()


# ─────────────────────────────────────────────────────────────────────────────
#  EMPTY STATE WIDGET
# ─────────────────────────────────────────────────────────────────────────────


class EmptyStateWidget(QWidget):
    run_indexer = pyqtSignal()
    clear_db = pyqtSignal()

    def __init__(self, theme=None, parent=None):
        super().__init__(parent)
        self._theme = theme
        vl = QVBoxLayout(self)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.setSpacing(12)

        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setFixedSize(80, 80)
        vl.addWidget(self._icon_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._title = QLabel("Nothing indexed yet")
        self._title.setObjectName("empty_title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(self._title)

        self._sub = QLabel(
            "Index your drives to start searching.\n"
            "Results appear instantly as you type."
        )
        self._sub.setObjectName("empty_sub")
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(self._sub)

        btn_row = QWidget()
        btn_hl = QHBoxLayout(btn_row)
        btn_hl.setContentsMargins(0, 8, 0, 0)
        btn_hl.setSpacing(10)
        btn_hl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._btn_clear = QPushButton("  Clear DB")
        self._btn_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_clear.clicked.connect(self.clear_db)

        self._btn_index = QPushButton("  Run Indexer")
        self._btn_index.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_index.clicked.connect(self.run_indexer)

        btn_hl.addWidget(self._btn_clear)
        btn_hl.addWidget(self._btn_index)
        vl.addWidget(btn_row)

        self._apply_style()

    def _draw_icon(self):
        T = self._theme
        if T is None:
            return
        size = 80
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(T["border_light"]), 2))
        p.drawEllipse(4, 4, size - 8, size - 8)
        p.setPen(QPen(QColor(T["text_secondary"]), 2.5))
        cx, cy, r = 34, 34, 14
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.drawLine(cx + int(r * 0.7), cy + int(r * 0.7), cx + 20, cy + 20)
        p.end()
        self._icon_lbl.setPixmap(px)

    def _apply_style(self):
        T = self._theme
        if T is None:
            return
        self._draw_icon()
        self._title.setStyleSheet(
            f"color: {T['text_primary']}; font-size: 17px; font-weight: 600;"
        )
        self._sub.setStyleSheet(f"color: {T['text_secondary']}; font-size: 13px;")
        self._btn_clear.setStyleSheet(
            f"QPushButton {{ background: {T['bg_control']}; border: 1px solid {T['border_light']};"
            f" border-radius: 6px; padding: 6px 18px; color: {T['text_secondary']}; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {T['bg_control_hov']}; color: {T['text_primary']}; }}"
        )
        self._btn_index.setStyleSheet(
            f"QPushButton {{ background: {T['accent']}; border: none; border-radius: 6px;"
            f" padding: 6px 18px; color: {T['text_on_accent']}; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {T['accent_hover']}; }}"
        )

    def update_theme(self, theme):
        self._theme = theme
        self._apply_style()
