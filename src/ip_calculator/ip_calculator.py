"""IP Calculator with Subnetting Support."""

import ipaddress
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.config import ICON_PATH


class IPCalculatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus IP Calculator")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setMinimumSize(540, 560)
        self.setStyleSheet("""
            QWidget {
                background-color: #0f172a;
                color: #f8fafc;
                font-family: 'Outfit', 'Inter', 'Segoe UI', sans-serif;
            }
            QLabel {
                font-size: 13px;
                color: #e2e8f0;
                font-weight: 500;
            }
            QLabel#title_lbl {
                font-size: 20px;
                font-weight: bold;
                color: #0ea5e9;
                letter-spacing: 1px;
            }
            QLabel#result_label {
                color: #94a3b8;
                font-size: 13px;
                font-weight: bold;
            }
            QLabel#result_value {
                color: #f8fafc;
                font-size: 14px;
                background-color: #1e293b;
                padding: 8px;
                border-radius: 6px;
                border: 1px solid #334155;
            }
            QLineEdit {
                background-color: #1e293b;
                border: 2px solid #334155;
                padding: 12px;
                border-radius: 8px;
                color: white;
                font-size: 15px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QLineEdit:focus {
                border: 2px solid #0ea5e9;
                background-color: #0f172a;
            }
            QPushButton {
                background-color: #0284c7;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QFrame#results_frame {
                background-color: #151e2e;
                border-radius: 12px;
                border: 1px solid #1e293b;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # Title
        title_lbl = QLabel("IP Subnet Calculator 🌐")
        title_lbl.setObjectName("title_lbl")
        main_layout.addWidget(title_lbl)

        # Input Area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Enter IP/CIDR (e.g. 192.168.1.5/24)")
        self.ip_input.returnPressed.connect(self.calculate)
        input_layout.addWidget(self.ip_input, stretch=1)

        self.calc_btn = QPushButton("Calculate ➔")
        self.calc_btn.clicked.connect(self.calculate)
        input_layout.addWidget(self.calc_btn)
        main_layout.addLayout(input_layout)

        # Results Frame
        self.results_frame = QFrame()
        self.results_frame.setObjectName("results_frame")
        results_layout = QGridLayout(self.results_frame)
        results_layout.setContentsMargins(20, 20, 20, 20)
        results_layout.setSpacing(16)

        self.fields = {
            "IP Address": QLabel(""),
            "Network Address": QLabel(""),
            "Usable Host Range": QLabel(""),
            "Broadcast Address": QLabel(""),
            "Total Number of Hosts": QLabel(""),
            "Number of Usable Hosts": QLabel(""),
            "Subnet Mask": QLabel(""),
            "Wildcard Mask": QLabel(""),
        }

        for row, (label_text, value_lbl) in enumerate(self.fields.items()):
            name_lbl = QLabel(label_text + ":")
            name_lbl.setObjectName("result_label")
            value_lbl.setObjectName("result_value")
            value_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

            results_layout.addWidget(name_lbl, row, 0)
            results_layout.addWidget(value_lbl, row, 1)

        main_layout.addWidget(self.results_frame)
        main_layout.addStretch()

        # Initial state default
        self.ip_input.setText("192.168.1.0/24")
        self.calculate()

    def calculate(self):
        text = self.ip_input.text().strip()
        if not text:
            return

        # Support space instead of slash for mask if user types '192.168.1.1 255.255.255.0'
        text = text.replace(" ", "/")

        try:
            # Check if IPv6 or IPv4
            if ":" in text:
                net = ipaddress.IPv6Network(text, strict=False)
                interface = ipaddress.IPv6Interface(text)
            else:
                net = ipaddress.IPv4Network(text, strict=False)
                interface = ipaddress.IPv4Interface(text)

            self.fields["IP Address"].setText(str(interface.ip))
            self.fields["Network Address"].setText(
                f"{net.network_address}/{net.prefixlen}"
            )

            if net.version == 4:
                self.fields["Subnet Mask"].setText(str(net.netmask))
                self.fields["Wildcard Mask"].setText(str(net.hostmask))
                self.fields["Broadcast Address"].setText(str(net.broadcast_address))

                if net.prefixlen >= 31:
                    self.fields["Usable Host Range"].setText("None")
                else:
                    first = net.network_address + 1
                    last = net.broadcast_address - 1
                    self.fields["Usable Host Range"].setText(f"{first} - {last}")
            else:
                self.fields["Subnet Mask"].setText(f"/{net.prefixlen}")
                self.fields["Wildcard Mask"].setText("N/A for IPv6")
                self.fields["Broadcast Address"].setText(
                    "N/A for IPv6 (uses multicast)"
                )

                if net.prefixlen >= 127:
                    self.fields["Usable Host Range"].setText("None")
                else:
                    first = net.network_address + 1
                    self.fields["Usable Host Range"].setText(f"{first} - ...")

            self.fields["Total Number of Hosts"].setText(f"{net.num_addresses:,}")

            if net.version == 4:
                unusable = 2 if net.prefixlen < 31 else 0
                usable = max(0, net.num_addresses - unusable)
                self.fields["Number of Usable Hosts"].setText(f"{usable:,}")
            else:
                self.fields["Number of Usable Hosts"].setText(f"{net.num_addresses:,}")

            self.ip_input.setStyleSheet("border: 2px solid #0ea5e9;")

        except Exception as _e:
            self.ip_input.setStyleSheet("border: 2px solid #ef4444;")
            for _, v in self.fields.items():
                v.setText("Invalid IP or CIDR")


def main():
    app = QApplication(sys.argv)
    window = IPCalculatorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
