import json
import os
import sys

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "color_config.json")
ICON_PATH = ""
MAX_SAVED_COLORS = 32

THEMES = {
    "dark": {
        "bg_base": "#070B14",
        "bg_surface": "#0D1526",
        "bg_elevated": "#141E35",
        "bg_card": "#1A2540",
        "border": "#1F2E4A",
        "border_active": "#3D6FFF",
        "text_primary": "#EDF2FF",
        "text_secondary": "#7A90B8",
        "text_muted": "#3D5070",
        "accent": "#3D6FFF",
        "success_bg": "#003D28",
        "success_fg": "#00F5A0",
        "success_border": "#00A06A",
        "divider": "#1F2E4A",
        "checker_a": "#2A3550",
        "checker_b": "#1A2540",
        "toggle_icon": "☀",
    },
    "light": {
        "bg_base": "#F0F4FF",
        "bg_surface": "#FFFFFF",
        "bg_elevated": "#E8EEFF",
        "bg_card": "#FFFFFF",
        "border": "#D0D8F0",
        "border_active": "#3D6FFF",
        "text_primary": "#0D1526",
        "text_secondary": "#4A5880",
        "text_muted": "#8A9CC0",
        "accent": "#3D6FFF",
        "success_bg": "#E6FFF5",
        "success_fg": "#00875A",
        "success_border": "#00C87A",
        "divider": "#D0D8F0",
        "checker_a": "#C8D0E8",
        "checker_b": "#E8EEFF",
        "toggle_icon": "☾",
    },
}


def make_stylesheet(t):
    return f"""
    * {{ font-family: 'SF Pro Display', 'Helvetica Neue', 'Segoe UI', sans-serif; }}
    QWidget#root_bg {{ background-color: {t["bg_base"]}; }}
    QWidget {{ background-color: transparent; color: {t["text_primary"]}; }}
    QLabel#section_label {{ font-size: 10px; font-weight: 600; letter-spacing: 2px; color: {t["text_muted"]}; }}
    QLabel#value_label {{ font-size: 19px; font-weight: 700; color: {t["text_primary"]}; letter-spacing: -0.5px; }}
    QLabel#sub_label {{ font-size: 11px; color: {t["text_secondary"]}; font-weight: 400; }}
    QLabel#channel_label {{ font-size: 9px; font-weight: 700; letter-spacing: 1.5px; color: {t["text_muted"]}; }}
    QLabel#app_title {{ font-size: 10px; font-weight: 700; letter-spacing: 3px; color: {t["text_muted"]}; }}
    QLineEdit {{
        background-color: {t["bg_card"]}; border: 1px solid {t["border"]};
        padding: 8px 32px 8px 10px; border-radius: 8px; color: {t["text_primary"]};
        font-size: 13px; font-weight: 500; selection-background-color: {t["accent"]};
    }}
    QLineEdit:focus {{ border: 1px solid {t["border_active"]}; background-color: {t["bg_elevated"]}; }}
    QLineEdit#channel_input {{ padding: 5px 4px; font-size: 12px; border-radius: 7px; font-weight: 600; }}
    QPushButton#primary {{
        background-color: {t["accent"]}; color: white; border: none;
        padding: 10px 16px; border-radius: 10px; font-weight: 600; font-size: 12px;
    }}
    QPushButton#primary:hover {{ background-color: #5585FF; }}
    QPushButton#primary:pressed {{ background-color: #2A56DD; }}
    QPushButton#ghost {{
        background-color: {t["bg_card"]}; color: {t["text_secondary"]};
        border: 1px solid {t["border"]}; padding: 10px 16px;
        border-radius: 10px; font-weight: 600; font-size: 12px;
    }}
    QPushButton#ghost:hover {{
        background-color: {t["bg_elevated"]}; color: {t["text_primary"]};
        border: 1px solid {t["border_active"]};
    }}
    QPushButton#toggle {{
        background-color: {t["bg_card"]}; color: {t["text_secondary"]};
        border: 1px solid {t["border"]}; padding: 6px 10px;
        border-radius: 8px; font-size: 14px; min-width: 32px; max-width: 32px;
    }}
    QPushButton#toggle:hover {{ background-color: {t["bg_elevated"]}; border: 1px solid {t["border_active"]}; }}
    QPushButton#expand_btn {{
        background-color: transparent; color: {t["text_muted"]};
        border: none; padding: 0px; font-size: 10px; font-weight: 700; letter-spacing: 1px;
    }}
    QPushButton#expand_btn:hover {{ color: {t["text_secondary"]}; }}
    QPushButton#inline_copy {{
        background-color: transparent; color: {t["text_muted"]};
        border: none; padding: 0px 6px;
        font-size: 13px; min-width: 24px; max-width: 24px;
    }}
    QPushButton#inline_copy:hover {{ color: {t["accent"]}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 4px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {t["border"]}; border-radius: 2px; min-height: 20px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


# ── Flow layout ────────────────────────────────────────────────────────────────


class FlowLayout(QLayout):
    def __init__(self, parent=None, h_spacing=5, v_spacing=5):
        super().__init__(parent)
        self._items = []
        self._h = h_spacing
        self._v = v_spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), dry=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, dry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect, dry):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, lh = r.x(), r.y(), 0
        for it in self._items:
            w, h = it.sizeHint().width(), it.sizeHint().height()
            if x + w > r.right() + 1 and lh:
                x = r.x()
                y += lh + self._v
                lh = 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), it.sizeHint()))
            x += w + self._h
            lh = max(lh, h)
        return y + lh - rect.y() + m.bottom()


# ── Widgets ────────────────────────────────────────────────────────────────────


class SVSquare(QWidget):
    colorChanged = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hue = 0.0
        self.sat = 1.0
        self.val = 1.0
        self.setFixedSize(240, 180)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._pressed = False

    def set_hue(self, h):
        self.hue = h
        self.update()

    def set_sv(self, s, v):
        self.sat = s
        self.val = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            0.0, 0.0, float(self.width()), float(self.height()), 12.0, 12.0
        )
        p.setClipPath(path)
        hg = QLinearGradient(0, 0, self.width(), 0)
        hg.setColorAt(0, QColor(255, 255, 255))
        hg.setColorAt(
            1, QColor.fromHsvF(max(0.0, min(0.999, self.hue / 360.0)), 1.0, 1.0)
        )
        p.fillRect(self.rect(), QBrush(hg))
        vg = QLinearGradient(0, 0, 0, self.height())
        vg.setColorAt(0, QColor(0, 0, 0, 0))
        vg.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(self.rect(), QBrush(vg))
        p.setClipping(False)
        x = self.sat * self.width()
        y = (1.0 - self.val) * self.height()
        h = max(0.0, min(0.999, self.hue / 360.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 210))
        p.drawEllipse(int(x - 9), int(y - 9), 18, 18)
        p.setBrush(
            QColor.fromHsvF(
                h, max(0.0, min(1.0, self.sat)), max(0.0, min(1.0, self.val))
            )
        )
        p.drawEllipse(int(x - 7), int(y - 7), 14, 14)

    def mousePressEvent(self, e):
        self._pressed = True
        self._handle(e)

    def mouseReleaseEvent(self, _):
        self._pressed = False

    def mouseMoveEvent(self, e):
        if self._pressed:
            self._handle(e)

    def _handle(self, e):
        x = max(0.0, min(e.position().x(), float(self.width())))
        y = max(0.0, min(e.position().y(), float(self.height())))
        self.sat = x / self.width()
        self.val = 1.0 - y / self.height()
        self.colorChanged.emit(self.sat, self.val)
        self.update()


class ThinSlider(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, mode="hue", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.val = 0.0
        self.base_color = QColor(Qt.GlobalColor.blue)
        self.checker_a = QColor("#2A3550")
        self.checker_b = QColor("#1A2540")
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pressed = False

    def set_val(self, v):
        self.val = max(0.0, min(1.0, v))
        self.update()

    def set_base_color(self, c):
        self.base_color = c
        self.update()

    def set_checker_colors(self, a, b):
        self.checker_a = a
        self.checker_b = b
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th = 10
        ty = (self.height() - th) // 2
        tw = self.width()
        path = QPainterPath()
        path.addRoundedRect(
            0.0, float(ty), float(tw), float(th), float(th // 2), float(th // 2)
        )
        p.setClipPath(path)
        if self.mode == "hue":
            g = QLinearGradient(0, 0, tw, 0)
            for i in range(360):
                g.setColorAt(i / 359.0, QColor.fromHsv(i, 255, 255))
            p.fillRect(0, ty, tw, th, QBrush(g))
        else:
            block = 5
            for by in range(ty, ty + th, block):
                for bx in range(0, tw, block):
                    col = (
                        self.checker_a
                        if ((bx // block + by // block) % 2 == 0)
                        else self.checker_b
                    )
                    p.fillRect(bx, by, block, block, col)
            g = QLinearGradient(0, 0, tw, 0)
            c0 = QColor(self.base_color)
            c0.setAlpha(0)
            c1 = QColor(self.base_color)
            c1.setAlpha(255)
            g.setColorAt(0, c0)
            g.setColorAt(1, c1)
            p.fillRect(0, ty, tw, th, QBrush(g))
        p.setClipping(False)
        tx = int(self.val * tw)
        cy = self.height() // 2
        r = 9
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(tx - r + 1, cy - r + 2, r * 2, r * 2)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(tx - r, cy - r, r * 2, r * 2)
        fill = (
            QColor.fromHsv(min(359, int(self.val * 360)), 255, 255)
            if self.mode == "hue"
            else QColor(self.base_color)
        )
        if self.mode == "alpha":
            fill.setAlpha(int(self.val * 255))
        p.setBrush(fill)
        p.drawEllipse(tx - r + 2, cy - r + 2, (r - 2) * 2, (r - 2) * 2)

    def mousePressEvent(self, e):
        self._pressed = True
        self._handle(e)

    def mouseReleaseEvent(self, _):
        self._pressed = False

    def mouseMoveEvent(self, e):
        if self._pressed:
            self._handle(e)

    def _handle(self, e):
        x = max(0.0, min(e.position().x(), float(self.width())))
        self.val = x / self.width()
        self.valueChanged.emit(self.val)
        self.update()


class ColorPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = QColor(61, 111, 255, 255)
        self.checker_a = QColor(180, 180, 180)
        self.checker_b = QColor(230, 230, 230)
        self.setFixedSize(56, 56)

    def set_color(self, c):
        self.color = c
        self.update()

    def set_checker_colors(self, a, b):
        self.checker_a = a
        self.checker_b = b
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QRadialGradient(28.0, 28.0, 34.0)
        gc = QColor(self.color)
        gc.setAlpha(55)
        glow.setColorAt(0, gc)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 56, 56)
        path = QPainterPath()
        path.addEllipse(4.0, 4.0, 48.0, 48.0)
        p.setClipPath(path)
        block = 6
        for by in range(4, 52, block):
            for bx in range(4, 52, block):
                col = (
                    self.checker_a
                    if ((bx // block + by // block) % 2 == 0)
                    else self.checker_b
                )
                p.fillRect(bx, by, block, block, col)
        p.setBrush(self.color)
        p.drawEllipse(4, 4, 48, 48)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(4, 4, 48, 48)


class ColorSwatch(QWidget):
    clicked = pyqtSignal(str)
    removed = pyqtSignal(str)

    def __init__(self, hex_str, theme_name="dark", parent=None):
        super().__init__(parent)
        self.hex_str = hex_str
        self.theme_name = theme_name
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False
        self.setMouseTracking(True)

    def enterEvent(self, _):
        self._hovered = True
        self.update()

    def leaveEvent(self, _):
        self._hovered = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.removed.emit(self.hex_str)
        elif e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.hex_str)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.hex_str)
        t = THEMES[self.theme_name]
        if color.alpha() < 255:
            block = 5
            ca, cb = QColor(t["checker_a"]), QColor(t["checker_b"])
            path = QPainterPath()
            path.addRoundedRect(3.0, 3.0, 30.0, 30.0, 6.0, 6.0)
            p.setClipPath(path)
            for by in range(3, 33, block):
                for bx in range(3, 33, block):
                    p.fillRect(
                        bx,
                        by,
                        block,
                        block,
                        ca if ((bx // block + by // block) % 2 == 0) else cb,
                    )
            p.setClipping(False)
        path = QPainterPath()
        path.addRoundedRect(3.0, 3.0, 30.0, 30.0, 6.0, 6.0)
        p.setClipPath(path)
        p.fillRect(3, 3, 30, 30, color)
        p.setClipping(False)
        border = QColor(t["border_active"]) if self._hovered else QColor(t["border"])
        p.setPen(QPen(border, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(3, 3, 30, 30, 6, 6)
        if self._hovered:
            p.setPen(QPen(QColor(255, 80, 80, 220), 1.8))
            cx, cy = 30, 6
            p.drawLine(cx - 3, cy - 3, cx + 3, cy + 3)
            p.drawLine(cx + 3, cy - 3, cx - 3, cy + 3)


class FlowWidget(QWidget):
    colorRequested = pyqtSignal(str)
    removeRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(FlowLayout(self, h_spacing=5, v_spacing=5))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def set_colors(self, colors, theme_name):
        layout = self.layout()
        while layout.count():
            it = layout.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        for hex_str in colors:
            sw = ColorSwatch(hex_str, theme_name)
            sw.clicked.connect(self.colorRequested)
            sw.removed.connect(self.removeRequested)
            layout.addWidget(sw)
        self.updateGeometry()
        self.update()


class ScreenPicker(QWidget):
    colorSelected = pyqtSignal(QColor)
    pickerClosed = pyqtSignal()

    def __init__(self, theme_name="dark", parent=None):
        super().__init__(None)
        self.theme_name = theme_name
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        screen = QApplication.primaryScreen()
        vg = screen.virtualGeometry()
        self.setGeometry(vg)
        self.pixmap = screen.grabWindow(0, vg.x(), vg.y(), vg.width(), vg.height())
        self.image = self.pixmap.toImage()
        self.mouse_pos = QCursor.pos()

    def mouseMoveEvent(self, e):
        self.mouse_pos = e.globalPosition().toPoint()
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            lp = e.globalPosition().toPoint() - self.geometry().topLeft()
            if self.image.rect().contains(lp):
                self.colorSelected.emit(self.image.pixelColor(lp))
        self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(0, 0, self.pixmap)
        mag = 160
        zoom = 10
        hm = mag // 2
        lp = self.mouse_pos - self.geometry().topLeft()
        src = QRect(lp.x() - hm // zoom, lp.y() - hm // zoom, mag // zoom, mag // zoom)
        magnified = self.pixmap.copy(src).scaled(mag, mag)
        dx = lp.x() + 25
        dy = lp.y() + 25
        if dx + mag > self.width():
            dx = lp.x() - mag - 25
        if dy + mag > self.height():
            dy = lp.y() - mag - 25
        t = THEMES[self.theme_name]
        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor(t["bg_surface"])
        bg.setAlpha(210)
        p.setBrush(bg)
        p.drawEllipse(dx - 5, dy - 5, mag + 10, mag + 10)
        path = QPainterPath()
        path.addEllipse(float(dx), float(dy), float(mag), float(mag))
        p.setClipPath(path)
        p.drawPixmap(dx, dy, magnified)
        p.setClipping(False)
        p.setPen(QPen(QColor(t["accent"]), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(dx, dy, mag, mag)
        cx, cy = dx + hm, dy + hm
        p.setPen(QPen(QColor(0, 0, 0, 130), 3))
        p.drawLine(cx - 12, cy, cx + 12, cy)
        p.drawLine(cx, cy - 12, cx, cy + 12)
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawLine(cx - 12, cy, cx + 12, cy)
        p.drawLine(cx, cy - 12, cx, cy + 12)
        if self.image.rect().contains(lp):
            c = self.image.pixelColor(lp)
            bx, by = dx + 8, dy + mag + 14
            p.setPen(Qt.PenStyle.NoPen)
            box = QColor(t["bg_base"])
            box.setAlpha(220)
            p.setBrush(box)
            p.drawRoundedRect(bx - 6, by - 15, 102, 22, 6, 6)
            p.setPen(QColor(t["text_primary"]))
            p.drawText(bx, by, c.name().upper())

    def closeEvent(self, e):
        self.pickerClosed.emit()
        super().closeEvent(e)


def make_channel_field(label_text):
    container = QWidget()
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(3)
    lbl = QLabel(label_text)
    lbl.setObjectName("channel_label")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    inp = QLineEdit()
    inp.setObjectName("channel_input")
    inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
    inp.setFixedHeight(32)
    vbox.addWidget(lbl)
    vbox.addWidget(inp)
    return container, inp


class InputWithCopy(QWidget):
    """A QLineEdit with an inline copy icon button overlaid on the right."""

    textEdited = pyqtSignal(str)

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.textEdited.connect(self.textEdited)
        self._layout.addWidget(self.line_edit)

        # Overlay copy button
        self.copy_btn = QPushButton("⎘", self)
        self.copy_btn.setObjectName("inline_copy")
        self.copy_btn.setFixedSize(28, 28)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setToolTip("Copy")
        self.copy_btn.clicked.connect(self._copy)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._reset_icon)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = self.line_edit.height() if self.line_edit.height() > 0 else 36
        btn_h = 28
        self.copy_btn.move(self.width() - 30, (h - btn_h) // 2)

    def setText(self, text):
        self.line_edit.setText(text)

    def text(self):
        return self.line_edit.text()

    def setPlaceholderText(self, t):
        self.line_edit.setPlaceholderText(t)

    def _copy(self):
        txt = self.line_edit.text()
        if txt:
            QApplication.clipboard().setText(txt)
            self.copy_btn.setText("✓")
            self._flash_timer.start(1400)

    def _reset_icon(self):
        self.copy_btn.setText("⎘")


# ── Main app ───────────────────────────────────────────────────────────────────


class ColorPickerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Color")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.theme_name = "dark"
        self.hue, self.sat, self.val, self.alpha = 210.0, 0.8, 0.9, 1.0
        self.updating = False
        self.saved_colors = []
        self._channels_expanded = False
        self.setFixedWidth(320)
        self._build_ui()
        self.load_config()
        self.apply_theme(self.theme_name)
        self.sync_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.bg_frame = QWidget()
        self.bg_frame.setObjectName("root_bg")
        self.bg_layout = QVBoxLayout(self.bg_frame)
        self.bg_layout.setContentsMargins(16, 16, 16, 16)
        self.bg_layout.setSpacing(11)
        root.addWidget(self.bg_frame)

        # ── Header ──────────────────────────────────────────────────────────
        # Compact: preview circle | hex value + sub info | spacer | toggle
        header = QHBoxLayout()
        header.setSpacing(10)
        header.setContentsMargins(0, 0, 0, 0)

        self.preview_widget = ColorPreview()
        header.addWidget(self.preview_widget, alignment=Qt.AlignmentFlag.AlignVCenter)

        info = QVBoxLayout()
        info.setSpacing(1)
        info.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        top_row.setContentsMargins(0, 0, 0, 0)
        self.hex_display = QLabel("#3D6FFF")
        self.hex_display.setObjectName("value_label")
        top_row.addWidget(self.hex_display)
        top_row.addStretch()
        info.addLayout(top_row)

        self.info_label = QLabel("Alpha 100%  ·  HSV 210° 80% 90%")
        self.info_label.setObjectName("sub_label")
        info.addWidget(self.info_label)

        header.addLayout(info, 1)

        self.toggle_btn = QPushButton("☀")
        self.toggle_btn.setObjectName("toggle")
        self.toggle_btn.setFixedSize(32, 32)
        self.toggle_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.toggle_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.bg_layout.addLayout(header)

        # Divider
        self.divider = QFrame()
        self.divider.setFixedHeight(1)
        self.bg_layout.addWidget(self.divider)

        # SV Square
        sq_row = QHBoxLayout()
        sq_row.setContentsMargins(0, 0, 0, 0)
        self.sv_square = SVSquare()
        self.sv_square.colorChanged.connect(self.on_sv_changed)
        sq_row.addWidget(self.sv_square, alignment=Qt.AlignmentFlag.AlignCenter)
        self.bg_layout.addLayout(sq_row)

        # Hue slider
        hue_lbl = QLabel("HUE")
        hue_lbl.setObjectName("section_label")
        self.bg_layout.addWidget(hue_lbl)
        self.hue_slider = ThinSlider(mode="hue")
        self.hue_slider.valueChanged.connect(self.on_hue_slider_changed)
        self.bg_layout.addWidget(self.hue_slider)

        # Alpha slider
        alpha_lbl = QLabel("OPACITY")
        alpha_lbl.setObjectName("section_label")
        self.bg_layout.addWidget(alpha_lbl)
        self.alpha_slider = ThinSlider(mode="alpha")
        self.alpha_slider.valueChanged.connect(self.on_alpha_slider_changed)
        self.bg_layout.addWidget(self.alpha_slider)

        # HEX / RGB inputs with inline copy icons
        inputs_row = QHBoxLayout()
        inputs_row.setSpacing(8)

        hex_col = QVBoxLayout()
        hex_col.setSpacing(4)
        hex_lbl = QLabel("HEX")
        hex_lbl.setObjectName("section_label")
        hex_col.addWidget(hex_lbl)
        self.hex_input = InputWithCopy(placeholder="#RRGGBB")
        self.hex_input.textEdited.connect(self.on_hex_edited)
        hex_col.addWidget(self.hex_input)
        inputs_row.addLayout(hex_col, 3)

        rgb_col = QVBoxLayout()
        rgb_col.setSpacing(4)
        rgb_lbl = QLabel("RGB / RGBA")
        rgb_lbl.setObjectName("section_label")
        rgb_col.addWidget(rgb_lbl)
        self.rgb_input = InputWithCopy(placeholder="r, g, b")
        self.rgb_input.textEdited.connect(self.on_rgb_edited)
        rgb_col.addWidget(self.rgb_input)
        inputs_row.addLayout(rgb_col, 4)

        self.bg_layout.addLayout(inputs_row)

        # Channels collapsible
        chan_header = QHBoxLayout()
        chan_header.setContentsMargins(0, 0, 0, 0)
        chan_lbl = QLabel("CHANNELS")
        chan_lbl.setObjectName("section_label")
        chan_header.addWidget(chan_lbl)
        chan_header.addStretch()
        self.expand_btn = QPushButton("▸ EXPAND")
        self.expand_btn.setObjectName("expand_btn")
        self.expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_btn.clicked.connect(self.toggle_channels)
        chan_header.addWidget(self.expand_btn)
        self.bg_layout.addLayout(chan_header)

        self.channels_widget = QWidget()
        chan_vbox = QVBoxLayout(self.channels_widget)
        chan_vbox.setContentsMargins(0, 0, 0, 0)
        chan_vbox.setSpacing(8)

        rgba_row = QHBoxLayout()
        rgba_row.setSpacing(6)
        c_r, self.inp_r = make_channel_field("R")
        c_g, self.inp_g = make_channel_field("G")
        c_b, self.inp_b = make_channel_field("B")
        c_a, self.inp_a = make_channel_field("A")
        for w in (c_r, c_g, c_b, c_a):
            rgba_row.addWidget(w)
        chan_vbox.addLayout(rgba_row)

        hsv_row = QHBoxLayout()
        hsv_row.setSpacing(6)
        c_h, self.inp_h = make_channel_field("H°")
        c_s, self.inp_s = make_channel_field("S%")
        c_v, self.inp_v = make_channel_field("V%")
        spacer_w = QWidget()
        spacer_w.setFixedWidth(c_a.sizeHint().width())
        for w in (c_h, c_s, c_v):
            hsv_row.addWidget(w)
        hsv_row.addWidget(spacer_w)
        chan_vbox.addLayout(hsv_row)

        self.channels_widget.setVisible(False)
        self.bg_layout.addWidget(self.channels_widget)

        for inp, fn in (
            (self.inp_r, self.on_channel_rgba),
            (self.inp_g, self.on_channel_rgba),
            (self.inp_b, self.on_channel_rgba),
            (self.inp_a, self.on_channel_rgba),
            (self.inp_h, self.on_channel_hsv),
            (self.inp_s, self.on_channel_hsv),
            (self.inp_v, self.on_channel_hsv),
        ):
            inp.textEdited.connect(fn)

        # Pick Screen button (full width)
        self.pick_btn = QPushButton("⊕  Pick from Screen")
        self.pick_btn.setObjectName("primary")
        self.pick_btn.clicked.connect(self.start_screen_picker)
        self.bg_layout.addWidget(self.pick_btn)

        # Divider
        self.divider2 = QFrame()
        self.divider2.setFixedHeight(1)
        self.bg_layout.addWidget(self.divider2)

        # Saved palette
        pal_header = QHBoxLayout()
        pal_header.setContentsMargins(0, 0, 0, 0)
        pal_lbl = QLabel("SAVED PALETTE")
        pal_lbl.setObjectName("section_label")
        pal_header.addWidget(pal_lbl)
        pal_header.addStretch()
        self.palette_count_lbl = QLabel("0")
        self.palette_count_lbl.setObjectName("section_label")
        pal_header.addWidget(self.palette_count_lbl)
        self.save_color_btn = QPushButton("＋ Save")
        self.save_color_btn.setObjectName("ghost")
        self.save_color_btn.setFixedHeight(24)
        self.save_color_btn.setStyleSheet(
            "font-size: 11px; padding: 2px 10px; border-radius: 6px;"
        )
        self.save_color_btn.clicked.connect(self.save_current_color)
        pal_header.addWidget(self.save_color_btn)
        self.bg_layout.addLayout(pal_header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setFixedHeight(86)
        self.flow_widget = FlowWidget()
        self.flow_widget.colorRequested.connect(self.load_saved_color)
        self.flow_widget.removeRequested.connect(self.remove_saved_color)
        self.scroll_area.setWidget(self.flow_widget)
        self.bg_layout.addWidget(self.scroll_area)

        self.palette_hint = QLabel("No saved colors yet — hit ＋ Save to add current")
        self.palette_hint.setObjectName("sub_label")
        self.palette_hint.setWordWrap(True)
        self.palette_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bg_layout.addWidget(self.palette_hint)

        self.bg_layout.addStretch()

    def toggle_channels(self):
        self._channels_expanded = not self._channels_expanded
        self.channels_widget.setVisible(self._channels_expanded)
        self.expand_btn.setText("▾ COLLAPSE" if self._channels_expanded else "▸ EXPAND")
        self.adjustSize()

    def on_channel_rgba(self):
        if self.updating:
            return
        try:
            r = int(float(self.inp_r.text()))
            g = int(float(self.inp_g.text()))
            b = int(float(self.inp_b.text()))
            a_text = self.inp_a.text().strip()
            if "." in a_text:
                a = int(float(a_text) * 255)
            else:
                a = int(float(a_text)) if a_text else 255
            c = QColor(
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
                max(0, min(255, a)),
            )
            self.hue = c.hueF() * 360.0 if c.hueF() >= 0 else 0
            self.sat = c.saturationF()
            self.val = c.valueF()
            self.alpha = c.alphaF()
            self.sync_ui(source="channel_rgba")
        except (ValueError, TypeError):
            pass

    def on_channel_hsv(self):
        if self.updating:
            return
        try:
            h = float(self.inp_h.text())
            s = float(self.inp_s.text()) / 100.0
            v = float(self.inp_v.text()) / 100.0
            self.hue = max(0.0, min(360.0, h))
            self.sat = max(0.0, min(1.0, s))
            self.val = max(0.0, min(1.0, v))
            self.sync_ui(source="channel_hsv")
        except (ValueError, TypeError):
            pass

    def _refresh_palette_ui(self):
        has = bool(self.saved_colors)
        self.scroll_area.setVisible(has)
        self.palette_hint.setVisible(not has)
        self.palette_count_lbl.setText(str(len(self.saved_colors)))
        self.flow_widget.set_colors(self.saved_colors, self.theme_name)

    def save_current_color(self):
        hex_str = self.hex_input.text().lower()
        if not hex_str:
            return
        if hex_str in self.saved_colors:
            self.saved_colors.remove(hex_str)
        self.saved_colors.insert(0, hex_str)
        self.saved_colors = self.saved_colors[:MAX_SAVED_COLORS]
        self._refresh_palette_ui()
        self._flash_save_btn()

    def remove_saved_color(self, hex_str):
        h = hex_str.lower()
        if h in self.saved_colors:
            self.saved_colors.remove(h)
        self._refresh_palette_ui()

    def load_saved_color(self, hex_str):
        if QColor.isValidColor(hex_str):
            c = QColor(hex_str)
            self.hue = c.hueF() * 360.0 if c.hueF() >= 0 else 0
            self.sat = c.saturationF()
            self.val = c.valueF()
            self.alpha = c.alphaF()
            self.sync_ui()

    def apply_theme(self, name):
        self.theme_name = name
        t = THEMES[name]
        self.setStyleSheet(make_stylesheet(t))
        self.bg_frame.setStyleSheet(
            f"QWidget#root_bg {{ background-color: {t['bg_base']}; }}"
        )
        self.divider.setStyleSheet(f"background-color: {t['divider']};")
        self.divider2.setStyleSheet(f"background-color: {t['divider']};")
        self.toggle_btn.setText(t["toggle_icon"])
        ca, cb = QColor(t["checker_a"]), QColor(t["checker_b"])
        self.preview_widget.set_checker_colors(ca, cb)
        self.alpha_slider.set_checker_colors(ca, cb)
        self._refresh_palette_ui()

    def toggle_theme(self):
        self.apply_theme("light" if self.theme_name == "dark" else "dark")
        self.sync_ui()

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                self.hue = data.get("hue", 210.0)
                self.sat = data.get("sat", 0.8)
                self.val = data.get("val", 0.9)
                self.alpha = data.get("alpha", 1.0)
                self.theme_name = data.get("theme", "dark")
                self.saved_colors = data.get("saved_colors", [])
            except Exception:
                pass
        self._refresh_palette_ui()

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(
                    {
                        "hue": self.hue,
                        "sat": self.sat,
                        "val": self.val,
                        "alpha": self.alpha,
                        "theme": self.theme_name,
                        "saved_colors": self.saved_colors,
                    },
                    f,
                )
        except Exception:
            pass

    def closeEvent(self, e):
        self.save_config()
        super().closeEvent(e)

    def sync_ui(self, source=None):
        if self.updating:
            return
        self.updating = True
        h = max(0.0, min(0.999, self.hue / 360.0))
        s = max(0.0, min(1.0, self.sat))
        v = max(0.0, min(1.0, self.val))
        a = max(0.0, min(1.0, self.alpha))
        color = QColor.fromHsvF(h, s, v, a)
        r, g, b, ai = color.red(), color.green(), color.blue(), int(a * 255)
        self.preview_widget.set_color(color)
        hex_str = (
            color.name(QColor.NameFormat.HexArgb).upper()
            if a < 1.0
            else color.name(QColor.NameFormat.HexRgb).upper()
        )
        self.hex_display.setText(hex_str)
        self.info_label.setText(
            f"Alpha {int(a * 100)}%  ·  HSV {int(self.hue)}° {int(s * 100)}% {int(v * 100)}%"
        )
        if source != "sv":
            self.sv_square.set_hue(self.hue)
            self.sv_square.set_sv(s, v)
        if source != "hue":
            self.hue_slider.set_val(self.hue / 360.0)
        if source != "alpha":
            self.alpha_slider.set_val(a)
            self.alpha_slider.set_base_color(QColor.fromHsvF(h, s, v))
        if source != "hex":
            self.hex_input.setText(hex_str)
        rgb_str = f"{r}, {g}, {b}" + (f", {ai}" if a < 1.0 else "")
        if source != "rgb":
            self.rgb_input.setText(rgb_str)
        if source != "channel_rgba":
            self.inp_r.setText(str(r))
            self.inp_g.setText(str(g))
            self.inp_b.setText(str(b))
            self.inp_a.setText(str(ai))
        if source != "channel_hsv":
            self.inp_h.setText(f"{self.hue:.1f}")
            self.inp_s.setText(f"{s * 100:.1f}")
            self.inp_v.setText(f"{v * 100:.1f}")
        self.updating = False

    def on_sv_changed(self, s, v):
        self.sat, self.val = s, v
        self.sync_ui(source="sv")

    def on_hue_slider_changed(self, h):
        self.hue = h * 360.0
        self.sync_ui(source="hue")

    def on_alpha_slider_changed(self, a):
        self.alpha = a
        self.sync_ui(source="alpha")

    def on_hex_edited(self, text):
        if QColor.isValidColor(text):
            c = QColor(text)
            self.hue = c.hueF() * 360.0 if c.hueF() >= 0 else 0
            self.sat = c.saturationF()
            self.val = c.valueF()
            self.alpha = c.alphaF()
            self.sync_ui(source="hex")

    def on_rgb_edited(self, text):
        try:
            parts = [
                float(p.strip())
                for p in text.replace("rgba", "")
                .replace("rgb", "")
                .replace("(", "")
                .replace(")", "")
                .split(",")
            ]
            if len(parts) >= 3:
                r, g, b = parts[:3]
                a_f = parts[3] / 255.0 if len(parts) > 3 else 1.0
                c = QColor(int(r), int(g), int(b), int(a_f * 255))
                self.hue = c.hueF() * 360.0 if c.hueF() >= 0 else 0
                self.sat = c.saturationF()
                self.val = c.valueF()
                self.alpha = c.alphaF()
                self.sync_ui(source="rgb")
        except (ValueError, IndexError):
            pass

    def start_screen_picker(self):
        self.hide()
        QTimer.singleShot(150, self._open_picker)

    def _open_picker(self):
        self.sp = ScreenPicker(theme_name=self.theme_name)
        self.sp.colorSelected.connect(self.on_screen_picked)
        self.sp.pickerClosed.connect(self.show)
        self.sp.show()

    def on_screen_picked(self, color):
        self.hue = color.hueF() * 360.0 if color.hueF() >= 0 else 0
        self.sat = color.saturationF()
        self.val = color.valueF()
        self.alpha = 1.0
        self.sync_ui()

    def _flash_save_btn(self):
        t = THEMES[self.theme_name]
        self.save_color_btn.setText("✓ Saved")
        self.save_color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {t['success_bg']}; color: {t['success_fg']}; border: 1px solid {t['success_border']}; padding: 2px 10px; border-radius: 6px; font-weight: 600; font-size: 11px; }}"
        )
        QTimer.singleShot(
            1500,
            lambda: (
                self.save_color_btn.setText("＋ Save"),
                self.save_color_btn.setStyleSheet(""),
            ),
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ColorPickerApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
