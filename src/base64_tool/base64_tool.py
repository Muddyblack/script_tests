"""Base64 Encoder/Decoder utility for Nexus."""

import base64
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.config import ICON_PATH


class Base64App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus Base64 Tool")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setMinimumSize(600, 500)
        self.setStyleSheet("""
            QWidget {
                background-color: #0f172a;
                color: #f8fafc;
                font-family: 'Outfit', 'Inter', 'Segoe UI', sans-serif;
            }
            QLabel {
                font-size: 14px;
                color: #94a3b8;
                font-weight: bold;
            }
            QPlainTextEdit {
                background-color: #1e293b;
                border: 2px solid #334155;
                border-radius: 8px;
                padding: 12px;
                color: #e2e8f0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 14px;
            }
            QPlainTextEdit:focus {
                border: 2px solid #6366f1;
            }
            QPushButton {
                background-color: #4f46e5;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4338ca;
            }
            QPushButton#danger {
                background-color: #e11d48;
            }
            QPushButton#danger:hover {
                background-color: #be123c;
            }
            QPushButton#secondary {
                background-color: #334155;
                color: #e2e8f0;
            }
            QPushButton#secondary:hover {
                background-color: #475569;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        header_layout = QHBoxLayout()
        title_lbl = QLabel("Base64 Encoder & Decoder")
        title_lbl.setStyleSheet("font-size: 20px; color: #818cf8;")
        header_layout.addWidget(title_lbl)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setObjectName("danger")
        self.clear_btn.clicked.connect(self.clear_all)
        header_layout.addWidget(self.clear_btn, alignment=Qt.AlignmentFlag.AlignRight)
        main_layout.addLayout(header_layout)

        # Upper Editor (Input)
        main_layout.addWidget(QLabel("Input:"))
        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText("Enter text to encode or decode...")
        main_layout.addWidget(self.input_box, stretch=1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.encode_btn = QPushButton("Encode ➔")
        self.encode_btn.clicked.connect(self.do_encode)

        self.decode_btn = QPushButton("Decode ➔")
        self.decode_btn.clicked.connect(self.do_decode)

        self.copy_btn = QPushButton("Copy Output")
        self.copy_btn.setObjectName("secondary")
        self.copy_btn.clicked.connect(self.copy_output)

        btn_layout.addWidget(self.encode_btn)
        btn_layout.addWidget(self.decode_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.copy_btn)
        main_layout.addLayout(btn_layout)

        # Lower Editor (Output)
        main_layout.addWidget(QLabel("Output:"))
        self.output_box = QPlainTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setStyleSheet(
            self.output_box.styleSheet() + "background-color: #151e2e;"
        )
        main_layout.addWidget(self.output_box, stretch=1)

    def do_encode(self):
        text = self.input_box.toPlainText()
        if not text:
            self.output_box.setPlainText("")
            return
        try:
            encoded_bytes = base64.b64encode(text.encode("utf-8"))
            self.output_box.setPlainText(encoded_bytes.decode("utf-8"))
            self.output_box.setStyleSheet(
                self.output_box.styleSheet().replace(
                    "border: 2px solid #ef4444;", "border: 2px solid #334155;"
                )
            )
        except Exception as e:
            self.output_box.setPlainText(f"Encoding Error: {str(e)}")
            self.output_box.setStyleSheet(
                self.output_box.styleSheet().replace(
                    "border: 2px solid #334155;", "border: 2px solid #ef4444;"
                )
            )

    def do_decode(self):
        text = self.input_box.toPlainText()
        if not text:
            self.output_box.setPlainText("")
            return
        try:
            # Clean up whitespace/newlines which might break decoding
            text = "".join(text.split())
            missing_padding = len(text) % 4
            if missing_padding:
                text += "=" * (4 - missing_padding)

            decoded_bytes = base64.b64decode(text.encode("utf-8"))
            self.output_box.setPlainText(decoded_bytes.decode("utf-8"))
            self.output_box.setStyleSheet(
                self.output_box.styleSheet().replace(
                    "border: 2px solid #ef4444;", "border: 2px solid #334155;"
                )
            )
        except Exception as e:
            self.output_box.setPlainText(
                f"Decoding Error: Invalid Base64 String.\n{str(e)}"
            )
            self.output_box.setStyleSheet(
                self.output_box.styleSheet().replace(
                    "border: 2px solid #334155;", "border: 2px solid #ef4444;"
                )
            )

    def clear_all(self):
        self.input_box.clear()
        self.output_box.clear()

    def copy_output(self):
        QApplication.clipboard().setText(self.output_box.toPlainText())
        self.copy_btn.setText("Copied!")
        self.copy_btn.setStyleSheet("background-color: #22c55e; color: white;")
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(1500, lambda: self._reset_btn(self.copy_btn, "Copy Output"))

    def _reset_btn(self, btn, text):
        btn.setText(text)
        btn.setStyleSheet("")


def main():
    app = QApplication(sys.argv)
    window = Base64App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
