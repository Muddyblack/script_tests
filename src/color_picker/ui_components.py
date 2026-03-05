from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.theme import ThemeManager
from src.img_to_text._capture import capture_virtual_desktop
from src.nexus.utils import copy_to_clipboard


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

    def __init__(self, hex_str, theme_mgr=None, parent=None):
        super().__init__(parent)
        self.hex_str = hex_str
        self.mgr = theme_mgr or ThemeManager()
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
        if color.alpha() < 255:
            block = 5
            ca, cb = QColor(self.mgr["border"]), QColor(self.mgr["bg_overlay"])
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
        border = (
            QColor(self.mgr["border_focus"])
            if self._hovered
            else QColor(self.mgr["border"])
        )
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
        self.setLayout(FlowLayout(h_spacing=4, v_spacing=4))

    def set_colors(self, colors, theme_mgr):
        layout = self.layout()
        while layout.count():
            it = layout.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        for hex_str in colors:
            sw = ColorSwatch(hex_str, theme_mgr)
            sw.clicked.connect(self.colorRequested)
            sw.removed.connect(self.removeRequested)
            layout.addWidget(sw)
        self.updateGeometry()
        self.update()


class ScreenPicker(QWidget):
    colorSelected = pyqtSignal(QColor)
    pickerClosed = pyqtSignal()

    def __init__(self, theme_mgr=None, parent=None):
        super().__init__(None)
        self.mgr = theme_mgr or ThemeManager()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.pixmap, vg = capture_virtual_desktop()
        self.setGeometry(vg)
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
        if dy + mag > self.height():
            dy = lp.y() - mag - 25
        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor(self.mgr["bg_overlay"])
        bg.setAlpha(210)
        p.setBrush(bg)
        p.drawEllipse(dx - 5, dy - 5, mag + 10, mag + 10)
        path = QPainterPath()
        path.addEllipse(float(dx), float(dy), float(mag), float(mag))
        p.setClipPath(path)
        p.drawPixmap(dx, dy, magnified)
        p.setClipping(False)
        p.setPen(QPen(QColor(self.mgr["accent"]), 2))
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
            box = QColor(self.mgr["bg_base"])
            box.setAlpha(220)
            p.setBrush(box)
            p.drawRoundedRect(bx - 6, by - 15, 102, 22, 6, 6)
            p.setPen(QColor(self.mgr["text_primary"]))
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
            copy_to_clipboard(txt)
            self.copy_btn.setText("✓")
            self._flash_timer.start(1400)

    def _reset_icon(self):
        self.copy_btn.setText("⎘")
