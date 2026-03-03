import json
import os
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.color_picker.ui_components import (
    ColorPreview,
    FlowWidget,
    InputWithCopy,
    ScreenPicker,
    SVSquare,
    ThinSlider,
    make_channel_field,
    make_stylesheet,
)
from src.common.theme import ThemeManager, WindowThemeBridge

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "color_config.json")
try:
    from src.common.config import COLOR_PICKER_ICON_PATH as ICON_PATH
except ImportError:
    ICON_PATH = ""
MAX_SAVED_COLORS = 32


class ColorPickerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.mgr = ThemeManager()
        self.setWindowTitle("Color")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.hue, self.sat, self.val, self.alpha = 210.0, 0.8, 0.9, 1.0
        self.updating = False
        self.saved_colors = []
        self._channels_expanded = False
        self.setFixedWidth(320)
        self._build_ui()
        self.load_config()
        self.mgr.theme_changed.connect(self.apply_theme)
        self.apply_theme()
        self.sync_ui()
        self._theme_bridge = WindowThemeBridge(self.mgr, self)  # Win32 titlebar + palette

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
        self.flow_widget.set_colors(self.saved_colors, self.mgr)

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

    def apply_theme(self):
        self.setStyleSheet(make_stylesheet(self.mgr))
        self.preview_widget.set_checker_colors(
            QColor(self.mgr["border"]), QColor(self.mgr["bg_overlay"])
        )
        self.hue_slider.set_checker_colors(
            QColor(self.mgr["border"]), QColor(self.mgr["bg_overlay"])
        )
        self.alpha_slider.set_checker_colors(
            QColor(self.mgr["border"]), QColor(self.mgr["bg_overlay"])
        )
        self.flow_widget.set_colors(self.saved_colors, self.mgr)
        self.divider.setStyleSheet(f"background-color: {self.mgr['border']};")
        self.divider2.setStyleSheet(f"background-color: {self.mgr['border']};")
        self.update()

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                self.hue = data.get("hue", 210.0)
                self.sat = data.get("sat", 0.8)
                self.val = data.get("val", 0.9)
                self.alpha = data.get("alpha", 1.0)
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
                        "theme": self.mgr.current_theme_name,
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
        self.sp = ScreenPicker(theme_mgr=self.mgr)
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
        self.save_color_btn.setText("✓ Saved")
        self.save_color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self.mgr['success']}; color: {self.mgr['bg_base']}; border: 1px solid {self.mgr['success']}; padding: 2px 10px; border-radius: 6px; font-weight: 600; font-size: 11px; }}"
        )
        QTimer.singleShot(
            1500,
            lambda: (
                self.save_color_btn.setText("＋ Save"),
                self.save_color_btn.setStyleSheet(""),
            ),
        )


def main():
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "nexus.colorpicker"
        )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    mgr = ThemeManager()
    app.setPalette(mgr.get_palette())

    window = ColorPickerApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
