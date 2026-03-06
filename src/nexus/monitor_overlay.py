from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from src.common.monitor_kvm import set_monitor_input


class MonitorOverlay(QWidget):
    def __init__(self, screen, index, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.lbl = QLabel(str(index))
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet(
            "color: white; "
            "background-color: rgba(0, 0, 0, 180); "
            "border-radius: 40px; "
            "font-size: 140px; "
            "font-weight: bold;"
        )
        layout.addWidget(self.lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        sg = screen.geometry()
        self.setGeometry(sg)
        self.show()


class MonitorSelectDialog(QDialog):
    def __init__(self, nexus, source: str):
        super().__init__(nexus)
        self.nexus = nexus
        self.source = source
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(1, 1)

        self.overlays = []
        screens = QGuiApplication.screens()
        for i, s in enumerate(screens):
            ov = MonitorOverlay(s, i + 1)
            self.overlays.append(ov)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.nexus.status_lbl.setText(f"📺 Select Monitor [1-{len(screens)}] or [A]ll")
        self.nexus.status_lbl.setStyleSheet("color: #3b82f6; font-weight: bold;")

    def keyPressEvent(self, event):
        key = event.key()
        screens_count = len(self.overlays)

        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            num = key - Qt.Key.Key_0
            if num <= screens_count:
                self._switch_and_close(num)
        elif key == Qt.Key.Key_A:
            self._switch_and_close(None)
        elif key == Qt.Key.Key_Escape:
            self._close_all()
            self.nexus.status_lbl.setText("Canceled Monitor Switch.")

    def _switch_and_close(self, monitor_index: int | None):
        self._close_all()
        # hide nexus to make it ultra snappy
        if hasattr(self.nexus, "hide"):
            self.nexus.hide()

        if monitor_index is None:
            self.nexus.status_lbl.setText(f"📺 Switched ALL to {self.source.upper()}")
        else:
            self.nexus.status_lbl.setText(
                f"📺 Switched Monitor {monitor_index} to {self.source.upper()}"
            )

        set_monitor_input(self.source, monitor_index)

    def _close_all(self):
        for o in self.overlays:
            o.close()
        self.close()


def start_monitor_selection(nexus, source: str):
    dlg = MonitorSelectDialog(nexus, source)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    dlg.exec()
