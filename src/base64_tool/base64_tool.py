"""Base64 Encoder/Decoder utility for Nexus — redesigned."""

import base64
import os
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from src.common.config import ICON_PATH
except ImportError:
    ICON_PATH = ""


from src.common.theme import ThemeManager
from src.common.theme_template import TOOL_SHEET

STYLESHEET_BASE64 = """
/* Specific overrides for Base64 tool if needed, otherwise uses TOOL_SHEET */
QLabel#app-title {
    font-family: 'DM Mono', 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 22px;
    font-weight: 700;
    color: {{text_primary}};
    letter-spacing: 1px;
}
QLabel#app-subtitle {
    font-family: 'DM Mono', 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 11px;
    font-weight: 400;
    color: {{text_secondary}};
    letter-spacing: 3px;
    text-transform: uppercase;
}
"""


def make_shadow(blur=24, color="#000000", alpha=180, x=0, y=4):
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(blur)
    c = QColor(color)
    c.setAlpha(alpha)
    effect.setColor(c)
    effect.setOffset(x, y)
    return effect


class DotAccent(QWidget):
    """Tiny decorative dot row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 8)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        mgr = ThemeManager()
        colors = [mgr["accent_pressed"], mgr["border_focus"], mgr["accent"]]
        for i, c in enumerate(colors):
            p.setBrush(QColor(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(i * 14, 0, 8, 8)
        p.end()


class GradientHeader(QWidget):
    """Top gradient bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)

    def paintEvent(self, event):
        p = QPainter(self)
        mgr = ThemeManager()
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0.0, QColor(mgr["accent_pressed"]))
        g.setColorAt(0.4, QColor(mgr["accent"]))
        g.setColorAt(0.7, QColor(mgr["success"]))
        g.setColorAt(1.0, QColor(mgr["accent_pressed"]))
        p.fillRect(self.rect(), g)
        p.end()


class Base64App(QWidget):
    def __init__(self):
        super().__init__()
        self.mgr = ThemeManager()
        self.setObjectName("root")
        self.setWindowTitle("Nexus · Base64")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(680, 620)
        self.mgr.theme_changed.connect(self._apply_theme)
        self._build_ui()
        self._apply_theme()

    def _apply_theme(self):
        self.mgr.apply_to_widget(self, TOOL_SHEET + STYLESHEET_BASE64)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(0)

        # Card
        card = QFrame()
        card.setObjectName("card")
        card.setGraphicsEffect(make_shadow(blur=40, alpha=200, y=8))
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Gradient top bar
        card_layout.addWidget(GradientHeader())

        # Inner padding
        inner = QVBoxLayout()
        inner.setContentsMargins(28, 24, 28, 28)
        inner.setSpacing(20)

        # ── Header row ──────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(0)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        dots = DotAccent()
        title_lbl = QLabel("BASE64")
        title_lbl.setObjectName("app-title")
        sub_lbl = QLabel("ENCODER / DECODER")
        sub_lbl.setObjectName("app-subtitle")
        title_col.addWidget(dots)
        title_col.addSpacing(6)
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col)
        hdr.addStretch()

        self.clear_btn = QPushButton("CLEAR")
        self.clear_btn.setObjectName("btn-clear")
        self.clear_btn.setFixedWidth(80)
        self.clear_btn.clicked.connect(self.clear_all)
        hdr.addWidget(self.clear_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        inner.addLayout(hdr)

        # Divider
        div = QFrame()
        div.setObjectName("divider")
        div.setFrameShape(QFrame.Shape.HLine)
        inner.addWidget(div)

        # ── Input ───────────────────────────────────────────────────
        in_lbl = QLabel("INPUT")
        in_lbl.setObjectName("field-label")
        inner.addWidget(in_lbl)

        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText("Paste text or Base64 string here…")
        self.input_box.setMinimumHeight(160)
        inner.addWidget(self.input_box)

        # ── Action buttons ──────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.encode_btn = QPushButton("ENCODE  →")
        self.encode_btn.setObjectName("btn-encode")
        self.encode_btn.clicked.connect(self.do_encode)

        self.decode_btn = QPushButton("DECODE  →")
        self.decode_btn.setObjectName("btn-decode")
        self.decode_btn.clicked.connect(self.do_decode)

        self.copy_btn = QPushButton("COPY OUTPUT")
        self.copy_btn.setObjectName("btn-copy")
        self.copy_btn.clicked.connect(self.copy_output)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("status-ok")

        btn_row.addWidget(self.encode_btn)
        btn_row.addWidget(self.decode_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.status_lbl)
        btn_row.addStretch()
        btn_row.addWidget(self.copy_btn)
        inner.addLayout(btn_row)

        # ── Output ──────────────────────────────────────────────────
        out_lbl = QLabel("OUTPUT")
        out_lbl.setObjectName("field-label")
        inner.addWidget(out_lbl)

        self.output_box = QPlainTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setPlaceholderText("Result will appear here…")
        self.output_box.setMinimumHeight(160)
        inner.addWidget(self.output_box)

        card_layout.addLayout(inner)
        outer.addWidget(card)

    # ── Logic ──────────────────────────────────────────────────────

    def _set_status(self, text, ok=True):
        self.status_lbl.setObjectName("status-ok" if ok else "status-err")
        self.status_lbl.setStyleSheet(
            f"color: {self.mgr['success'] if ok else self.mgr['danger']};"
        )
        self.status_lbl.setText(text)

    def do_encode(self):
        text = self.input_box.toPlainText()
        if not text:
            self.output_box.clear()
            self._set_status("")
            return
        try:
            result = base64.b64encode(text.encode("utf-8")).decode("utf-8")
            self.output_box.setPlainText(result)
            self._set_status("✓  encoded")
        except Exception as e:
            self.output_box.setPlainText(f"Error: {e}")
            self._set_status("✗  encoding failed", ok=False)

    def do_decode(self):
        text = self.input_box.toPlainText()
        if not text:
            self.output_box.clear()
            self._set_status("")
            return
        try:
            cleaned = "".join(text.split())
            pad = len(cleaned) % 4
            if pad:
                cleaned += "=" * (4 - pad)
            result = base64.b64decode(cleaned.encode("utf-8")).decode("utf-8")
            self.output_box.setPlainText(result)
            self._set_status("✓  decoded")
        except Exception as e:
            self.output_box.setPlainText(f"Invalid Base64.\n{e}")
            self._set_status("✗  invalid input", ok=False)

    def clear_all(self):
        self.input_box.clear()
        self.output_box.clear()
        self._set_status("")

    def copy_output(self):
        text = self.output_box.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.copy_btn.setText("✓ COPIED")
        self.copy_btn.setStyleSheet(
            f"background-color: {self.mgr['bg_control']}; color: {self.mgr['success']}; border: 1px solid {self.mgr['success']};"
        )
        QTimer.singleShot(1600, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self.copy_btn.setText("COPY OUTPUT")
        self.copy_btn.setStyleSheet("")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    mgr = ThemeManager()
    app.setPalette(mgr.get_palette())
    window = Base64App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
