"""Nexus Search application bootstrap — wires together all components."""

import sys

import keyboard
from PyQt6.QtWidgets import QApplication

from src.common.config import IMG_TO_TEXT_HOTKEY, SUMMON_HOTKEY

from .search import NexusSearch
from .tray import create_tray_icon
from .widgets import NexusBridge


def main():
    """Entry point for Nexus Search."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    nexus = NexusSearch()
    bridge = NexusBridge()

    # Thread-safe toggle: hotkey thread -> Qt main thread
    bridge.toggle_signal.connect(
        lambda: nexus.summon() if not nexus.isVisible() else nexus.hide()
    )
    bridge.snip_to_text_signal.connect(nexus.start_img_to_text)

    def on_toggle():
        bridge.toggle_signal.emit()

    def on_snip_to_text():
        bridge.snip_to_text_signal.emit()

    # System tray icon
    tray = create_tray_icon(app, nexus)  # noqa: F841 — prevent GC
    nexus.tray = tray

    # Bind the fixed hotkey
    try:
        keyboard.add_hotkey(SUMMON_HOTKEY, on_toggle)
    except Exception as e:
        print(f"Hotkey bind failed: {e}")

    try:
        keyboard.add_hotkey(IMG_TO_TEXT_HOTKEY, on_snip_to_text)
    except Exception as e:
        print(f"OCR hotkey bind failed: {e}")

    # If launched with --summon, show immediately
    if "--summon" in sys.argv:
        nexus.summon()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
