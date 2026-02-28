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


STYLESHEET = """
/* ── Root ──────────────────────────────────────────────────────── */
QWidget#root {
    background-color: #080c14;
}

/* ── Card Panel ─────────────────────────────────────────────────── */
QFrame#card {
    background-color: #0e1524;
    border: 1px solid #1c2a42;
    border-radius: 16px;
}

/* ── Labels ─────────────────────────────────────────────────────── */
QLabel#app-title {
    font-family: 'DM Mono', 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 22px;
    font-weight: 700;
    color: #e8edf5;
    letter-spacing: 1px;
}
QLabel#app-subtitle {
    font-family: 'DM Mono', 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 11px;
    font-weight: 400;
    color: #3d5278;
    letter-spacing: 3px;
    text-transform: uppercase;
}
QLabel#field-label {
    font-family: 'DM Mono', 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 10px;
    font-weight: 600;
    color: #3d5278;
    letter-spacing: 3px;
}
QLabel#status-ok {
    font-family: 'DM Mono', 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #22d3a0;
    letter-spacing: 1px;
}
QLabel#status-err {
    font-family: 'DM Mono', 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #f43f5e;
    letter-spacing: 1px;
}

/* ── Text Editors ───────────────────────────────────────────────── */
QPlainTextEdit {
    background-color: #060a11;
    border: 1px solid #1c2a42;
    border-radius: 10px;
    padding: 14px 16px;
    color: #c8d8f0;
    font-family: 'DM Mono', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    line-height: 1.6;
    selection-background-color: #1e3a5f;
}
QPlainTextEdit:focus {
    border: 1px solid #2a4a7f;
    background-color: #07101e;
}
QPlainTextEdit[readOnly="true"] {
    background-color: #050810;
    color: #7a9ec8;
    border: 1px solid #131e30;
}
QScrollBar:vertical {
    background: #060a11;
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #1c2a42;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton {
    font-family: 'DM Mono', 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1.5px;
    border: none;
    border-radius: 8px;
    padding: 11px 22px;
}
QPushButton#btn-encode {
    background-color: #1a3a6e;
    color: #6db3ff;
    border: 1px solid #2a5599;
}
QPushButton#btn-encode:hover {
    background-color: #1e4480;
    color: #90caff;
    border: 1px solid #3a6bb5;
}
QPushButton#btn-encode:pressed { background-color: #162f5a; }

QPushButton#btn-decode {
    background-color: #0f3028;
    color: #34d399;
    border: 1px solid #1a5040;
}
QPushButton#btn-decode:hover {
    background-color: #133a30;
    color: #6ee7b7;
    border: 1px solid #22684d;
}
QPushButton#btn-decode:pressed { background-color: #0c2820; }

QPushButton#btn-copy {
    background-color: #0e1524;
    color: #3d5278;
    border: 1px solid #1c2a42;
}
QPushButton#btn-copy:hover {
    background-color: #0f1a2e;
    color: #6d8fbf;
    border: 1px solid #2a4060;
}
QPushButton#btn-copy:pressed { background-color: #0a1020; }

QPushButton#btn-clear {
    background-color: transparent;
    color: #3d5278;
    border: 1px solid #1c2a42;
}
QPushButton#btn-clear:hover {
    background-color: #1a0a10;
    color: #f43f5e;
    border: 1px solid #5a1a28;
}
QPushButton#btn-clear:pressed { background-color: #140710; }

/* ── Divider ────────────────────────────────────────────────────── */
QFrame#divider {
    background-color: #1c2a42;
    max-height: 1px;
    border: none;
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
        colors = ["#1e3a6e", "#2a5599", "#6db3ff"]
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
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0.0, QColor("#1e3a6e"))
        g.setColorAt(0.4, QColor("#6db3ff"))
        g.setColorAt(0.7, QColor("#22d3a0"))
        g.setColorAt(1.0, QColor("#1e3a6e"))
        p.fillRect(self.rect(), g)
        p.end()


class Base64App(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("Nexus · Base64")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(680, 620)
        self.setStyleSheet(STYLESHEET)
        self._build_ui()

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
        self.status_lbl.setStyleSheet("color: #22d3a0;" if ok else "color: #f43f5e;")
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
            "background-color: #0f3028; color: #22d3a0; border: 1px solid #22684d;"
        )
        QTimer.singleShot(1600, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self.copy_btn.setText("COPY OUTPUT")
        self.copy_btn.setStyleSheet("")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Base64App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
