import json
import os
import sys

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.config import ICON_PATH

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "color_config.json")

# ──────────────────────────────────────────────────────────────────────
# Custom Picker Widgets
# ──────────────────────────────────────────────────────────────────────


class SVSquare(QWidget):
    """Saturation-Value square selector."""

    colorChanged = pyqtSignal(float, float)  # S, V

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hue = 0.0  # 0-360
        self.sat = 1.0  # 0-1
        self.val = 1.0  # 0-1
        self.setFixedSize(220, 220)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_hue(self, hue):
        self.hue = hue
        self.update()

    def set_sv(self, s, v):
        self.sat = s
        self.val = v
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw SV Gradient
        # Horizontal: White -> Hue
        h_grad = QLinearGradient(0, 0, self.width(), 0)
        h_grad.setColorAt(0, Qt.GlobalColor.white)
        c = QColor.fromHsvF(self.hue / 360.0, 1.0, 1.0)
        h_grad.setColorAt(1, c)
        painter.fillRect(self.rect(), h_grad)

        # Vertical: Transparent -> Black
        v_grad = QLinearGradient(0, 0, 0, self.height())
        v_grad.setColorAt(0, QColor(0, 0, 0, 0))
        v_grad.setColorAt(1, Qt.GlobalColor.black)
        painter.fillRect(self.rect(), v_grad)

        # Draw handle
        x = self.sat * self.width()
        y = (1.0 - self.val) * self.height()

        painter.setPen(
            QPen(Qt.GlobalColor.white if self.val < 0.5 else Qt.GlobalColor.black, 2)
        )
        painter.drawEllipse(int(x - 6), int(y - 6), 12, 12)

    def mousePressEvent(self, event):
        self._handle_mouse(event)

    def mouseMoveEvent(self, event):
        self._handle_mouse(event)

    def _handle_mouse(self, event):
        x = max(0.0, min(event.position().x(), float(self.width())))
        y = max(0.0, min(event.position().y(), float(self.height())))
        self.sat = x / self.width()
        self.val = 1.0 - (y / self.height())
        self.colorChanged.emit(self.sat, self.val)
        self.update()


class ColorSlider(QWidget):
    """Generic vertical slider for Hue or Alpha."""

    valueChanged = pyqtSignal(float)

    def __init__(self, mode="hue", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.val = 0.0  # 0-1
        self.setFixedWidth(30)
        self.base_color = QColor(Qt.GlobalColor.blue)

    def set_val(self, val):
        self.val = val
        self.update()

    def set_base_color(self, color):
        self.base_color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect().adjusted(0, 0, -10, 0)

        if self.mode == "hue":
            grad = QLinearGradient(0, 0, 0, self.height())
            for i in range(360):
                grad.setColorAt(i / 359.0, QColor.fromHsv(i, 255, 255))
            painter.fillRect(rect, grad)
        else:
            # Alpha slider with checkerboard
            painter.setBrush(QBrush(QColor(100, 100, 100)))
            painter.drawRect(rect)
            block_size = 5
            for y in range(0, self.height(), block_size):
                for x in range(0, rect.width(), block_size):
                    if (x // block_size + y // block_size) % 2 == 0:
                        painter.fillRect(
                            x, y, block_size, block_size, Qt.GlobalColor.white
                        )

            grad = QLinearGradient(0, 0, 0, self.height())
            c_start = QColor(self.base_color)
            c_start.setAlpha(255)
            c_end = QColor(self.base_color)
            c_end.setAlpha(0)
            grad.setColorAt(0, c_start)
            grad.setColorAt(1, c_end)
            painter.fillRect(rect, grad)

        # Draw handle arrow
        y_pos = (
            (1.0 - self.val) * self.height()
            if self.mode == "alpha"
            else (self.val) * self.height()
        )
        painter.setPen(Qt.GlobalColor.white)
        painter.setBrush(QColor("#3b82f6"))
        poly = [
            QPoint(rect.width(), int(y_pos)),
            QPoint(self.width(), int(y_pos - 5)),
            QPoint(self.width(), int(y_pos + 5)),
        ]
        painter.drawPolygon(poly)

    def mousePressEvent(self, event):
        self._handle_mouse(event)

    def mouseMoveEvent(self, event):
        self._handle_mouse(event)

    def _handle_mouse(self, event):
        y_pos = max(0.0, min(event.position().y(), float(self.height())))
        self.val = y_pos / self.height()
        if self.mode == "alpha":
            self.val = 1.0 - self.val
        self.valueChanged.emit(self.val)
        self.update()


# ──────────────────────────────────────────────────────────────────────
# Main Apps
# ──────────────────────────────────────────────────────────────────────


class ScreenPicker(QWidget):
    colorSelected = pyqtSignal(QColor)
    pickerClosed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        screen = QApplication.primaryScreen()
        virtual_geometry = screen.virtualGeometry()
        self.setGeometry(virtual_geometry)

        self.pixmap = screen.grabWindow(
            0,
            virtual_geometry.x(),
            virtual_geometry.y(),
            virtual_geometry.width(),
            virtual_geometry.height(),
        )
        self.image = self.pixmap.toImage()
        self.mouse_pos = QCursor.pos()

    def mouseMoveEvent(self, event):
        self.mouse_pos = event.globalPosition().toPoint()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            local_pos = event.globalPosition().toPoint() - self.geometry().topLeft()
            if self.image.rect().contains(local_pos):
                color = self.image.pixelColor(local_pos)
                self.colorSelected.emit(color)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)

        # Magnifier
        mag_size = 180
        zoom = 10
        half_mag = mag_size // 2

        local_pos = self.mouse_pos - self.geometry().topLeft()
        src_rect = QRect(
            local_pos.x() - (half_mag // zoom),
            local_pos.y() - (half_mag // zoom),
            mag_size // zoom,
            mag_size // zoom,
        )

        magnified = self.pixmap.copy(src_rect).scaled(mag_size, mag_size)

        draw_x = local_pos.x() + 30
        draw_y = local_pos.y() + 30
        if draw_x + mag_size > self.width():
            draw_x = local_pos.x() - mag_size - 30
        if draw_y + mag_size > self.height():
            draw_y = local_pos.y() - mag_size - 30

        path = QPainterPath()
        path.addEllipse(draw_x, draw_y, mag_size, mag_size)
        painter.setClipPath(path)
        painter.drawPixmap(draw_x, draw_y, magnified)
        painter.setClipping(False)

        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawEllipse(draw_x, draw_y, mag_size, mag_size)

        cx, cy = draw_x + half_mag, draw_y + half_mag
        painter.setPen(QPen(Qt.GlobalColor.black, 3))
        painter.drawLine(cx - 10, cy, cx + 10, cy)
        painter.drawLine(cx, cy - 10, cx, cy + 10)
        painter.setPen(QPen(Qt.GlobalColor.cyan, 1))
        painter.drawLine(cx - 10, cy, cx + 10, cy)
        painter.drawLine(cx, cy - 10, cx, cy + 10)

        if self.image.rect().contains(local_pos):
            c = self.image.pixelColor(local_pos)
            hex_str = c.name().upper()
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(draw_x + 2, draw_y + mag_size + 22, hex_str)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(draw_x, draw_y + mag_size + 20, hex_str)

    def closeEvent(self, event):
        self.pickerClosed.emit()
        super().closeEvent(event)


class ColorPickerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus Color Picker")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setFixedSize(380, 620)
        self.setStyleSheet("""
            QWidget { background-color: #0f172a; color: #f8fafc; font-family: 'Outfit'; }
            QLabel { font-size: 13px; color: #e2e8f0; font-weight: 500; }
            QLineEdit {
                background-color: #1e293b; border: 2px solid #334155;
                padding: 10px; border-radius: 8px; color: white;
                font-size: 14px; font-weight: bold;
            }
            QLineEdit:focus { border: 2px solid #3b82f6; }
            QPushButton {
                background-color: #3b82f6; color: white; border: none;
                padding: 12px; border-radius: 8px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton#sec { background-color: #334155; }
            QPushButton#sec:hover { background-color: #475569; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QHBoxLayout()
        self.preview_container = QFrame()
        self.preview_container.setFixedSize(80, 80)
        self.preview_container.setObjectName("checkerboard")

        # Create a native checkerboard pixmap
        checker = QPixmap(20, 20)
        p = QPainter(checker)
        p.fillRect(0, 0, 10, 10, QColor(200, 200, 200))
        p.fillRect(10, 10, 10, 10, QColor(200, 200, 200))
        p.fillRect(10, 0, 10, 10, Qt.GlobalColor.white)
        p.fillRect(0, 10, 10, 10, Qt.GlobalColor.white)
        p.end()

        self.preview_container.setAutoFillBackground(True)
        palette = self.preview_container.palette()
        palette.setBrush(self.preview_container.backgroundRole(), QBrush(checker))
        self.preview_container.setPalette(palette)

        self.preview_container.setStyleSheet(
            """
            QFrame#checkerboard {
                border-radius: 40px; border: 3px solid #334155;
            }
        """
        )
        self.preview = QFrame(self.preview_container)
        self.preview.setFixedSize(80, 80)
        self.preview.setStyleSheet("border-radius: 40px;")
        header.addWidget(self.preview_container)

        info_col = QVBoxLayout()
        self.title_lbl = QLabel("Professional Color Picker")
        self.title_lbl.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #60a5fa;"
        )
        info_col.addWidget(self.title_lbl)
        self.alpha_display = QLabel("Transparency: 100%")
        info_col.addWidget(self.alpha_display)
        header.addLayout(info_col)
        layout.addLayout(header)

        picker_layout = QHBoxLayout()
        self.sv_square = SVSquare()
        self.sv_square.colorChanged.connect(self.on_sv_changed)
        picker_layout.addWidget(self.sv_square)

        self.hue_slider = ColorSlider(mode="hue")
        self.hue_slider.valueChanged.connect(self.on_hue_slider_changed)
        picker_layout.addWidget(self.hue_slider)

        self.alpha_slider = ColorSlider(mode="alpha")
        self.alpha_slider.valueChanged.connect(self.on_alpha_slider_changed)
        picker_layout.addWidget(self.alpha_slider)
        layout.addLayout(picker_layout)

        self.hex_input = QLineEdit()
        self.hex_input.setPlaceholderText("HEX #RRGGBBAA")
        self.hex_input.textEdited.connect(self.on_hex_edited)
        layout.addWidget(QLabel("HEX:"))
        layout.addWidget(self.hex_input)

        self.rgb_input = QLineEdit()
        self.rgb_input.setPlaceholderText("RGBA (r, g, b, a)")
        self.rgb_input.textEdited.connect(self.on_rgb_edited)
        layout.addWidget(QLabel("RGBA:"))
        layout.addWidget(self.rgb_input)

        btns = QHBoxLayout()
        self.pick_btn = QPushButton("🎯 Pick Anywhere")
        self.pick_btn.clicked.connect(self.start_screen_picker)
        btns.addWidget(self.pick_btn)

        self.palette_btn = QPushButton("🎨 Palette")
        self.palette_btn.setObjectName("sec")
        self.palette_btn.clicked.connect(self.open_color_picker)
        btns.addWidget(self.palette_btn)

        self.copy_btn = QPushButton("Copy HEX")
        self.copy_btn.setObjectName("sec")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        btns.addWidget(self.copy_btn)

        self.copy_rgb_btn = QPushButton("Copy RGB")
        self.copy_rgb_btn.setObjectName("sec")
        self.copy_rgb_btn.clicked.connect(self.copy_rgb_to_clipboard)
        btns.addWidget(self.copy_rgb_btn)
        
        layout.addLayout(btns)

        self.hue, self.sat, self.val, self.alpha = 210.0, 0.8, 0.9, 1.0
        self.updating = False
        self.load_config()
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
                    
                    custom_colors = data.get("custom_colors", [])
                    for i, color_str in enumerate(custom_colors):
                        if i < QColorDialog.customCount() and QColor.isValidColor(color_str):
                            QColorDialog.setCustomColor(i, QColor(color_str))
            except Exception:
                pass

    def save_config(self):
        try:
            custom_colors = []
            for i in range(QColorDialog.customCount()):
                color = QColorDialog.customColor(i)
                custom_colors.append(color.name(QColor.NameFormat.HexArgb))
                
            with open(CONFIG_PATH, "w") as f:
                json.dump(
                    {
                        "hue": self.hue,
                        "sat": self.sat,
                        "val": self.val,
                        "alpha": self.alpha,
                        "custom_colors": custom_colors,
                    },
                    f,
                )
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)

    def sync_ui(self, source=None):
        if self.updating:
            return
        self.updating = True
        # Clamp hue inside bounds
        h, s, v, a = (
            max(0.0, min(0.999, self.hue / 360.0)),
            max(0.0, min(1.0, self.sat)),
            max(0.0, min(1.0, self.val)),
            max(0.0, min(1.0, self.alpha)),
        )
        color = QColor.fromHsvF(h, s, v, a)
        r, g, b, a_int = (
            color.red(),
            color.green(),
            color.blue(),
            int(a * 255),
        )
        self.preview.setStyleSheet(f"background-color: rgba({r},{g},{b},{self.alpha});")
        self.alpha_display.setText(f"Transparency: {int(self.alpha * 100)}%")

        if source != "sv":
            self.sv_square.set_hue(self.hue)
            self.sv_square.set_sv(self.sat, self.val)
        if source != "hue":
            self.hue_slider.set_val(self.hue / 360.0)
        if source != "alpha":
            self.alpha_slider.set_val(a)
            self.alpha_slider.set_base_color(QColor.fromHsvF(h, s, v))

        hex_str = (
            color.name(QColor.NameFormat.HexArgb).upper()
            if a < 1.0
            else color.name(QColor.NameFormat.HexRgb).upper()
        )
        if source != "hex":
            self.hex_input.setText(hex_str)
        rgb_str = f"{r}, {g}, {b}" + (f", {a_int}" if a < 1.0 else "")
        if source != "rgb":
            self.rgb_input.setText(rgb_str)
        self.updating = False

    def on_sv_changed(self, s, v):
        self.sat, self.val = s, v
        self.sync_ui(source="sv")

    def on_hue_slider_changed(self, h_ratio):
        self.hue = h_ratio * 360.0
        self.sync_ui(source="hue")

    def on_alpha_slider_changed(self, a_val):
        self.alpha = a_val
        self.sync_ui(source="alpha")

    def on_hex_edited(self, text):
        if QColor.isValidColor(text):
            c = QColor(text)
            self.hue, self.sat, self.val, self.alpha = (
                (c.hueF() * 360.0 if c.hueF() >= 0 else 0),
                c.saturationF(),
                c.valueF(),
                c.alphaF(),
            )
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
                a_float = parts[3] / 255.0 if len(parts) > 3 else 1.0
                c = QColor(int(r), int(g), int(b), int(a_float * 255))
                self.hue, self.sat, self.val, self.alpha = (
                    (c.hueF() * 360.0 if c.hueF() >= 0 else 0),
                    c.saturationF(),
                    c.valueF(),
                    c.alphaF(),
                )
                self.sync_ui(source="rgb")
        except (ValueError, IndexError):
            pass

    def open_color_picker(self):
        opts = QColorDialog.ColorDialogOption.ShowAlphaChannel
        h, s, v, a = (
            max(0.0, min(0.999, self.hue / 360.0)),
            max(0.0, min(1.0, self.sat)),
            max(0.0, min(1.0, self.val)),
            max(0.0, min(1.0, self.alpha)),
        )
        color = QColorDialog.getColor(
            QColor.fromHsvF(h, s, v, a), self, "Nexus Color Palette", options=opts
        )
        if color.isValid():
            self.hue, self.sat, self.val, self.alpha = (
                (color.hueF() * 360.0 if color.hueF() >= 0 else 0),
                color.saturationF(),
                color.valueF(),
                color.alphaF(),
            )
            self.sync_ui()

    def start_screen_picker(self):
        self.hide()
        QTimer.singleShot(150, self._open_picker)

    def _open_picker(self):
        self.sp = ScreenPicker()
        self.sp.colorSelected.connect(self.on_screen_picked)
        self.sp.pickerClosed.connect(self.show)
        self.sp.show()

    def on_screen_picked(self, color):
        self.hue, self.sat, self.val = (
            (color.hueF() * 360.0 if color.hueF() >= 0 else 0),
            color.saturationF(),
            color.valueF(),
        )
        self.alpha = 1.0
        self.sync_ui()

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.hex_input.text())
        self.copy_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("Copy HEX"))

    def copy_rgb_to_clipboard(self):
        QApplication.clipboard().setText(self.rgb_input.text())
        self.copy_rgb_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.copy_rgb_btn.setText("Copy RGB"))


def main():
    app = QApplication(sys.argv)
    window = ColorPickerApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
