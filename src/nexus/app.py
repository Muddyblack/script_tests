import contextlib
import os
import sys

# Prevent Intel OpenMP conflict (torch vs Qt) which causes DLL load errors
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import keyboard
from PyQt6.QtWidgets import QApplication

from src.common.config import IMG_TO_TEXT_HOTKEY, SUMMON_HOTKEY

from .hotkeys import _HotkeyWindow
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

    # RegisterHotKey-based hotkeys — survive lock/unlock/hibernate without
    # any re-registration, unlike WH_KEYBOARD_LL hooks.
    hw = _HotkeyWindow()
    hw.toggle_signal.connect(bridge.toggle_signal)
    hw.ocr_signal.connect(bridge.snip_to_text_signal)
    hw.start(SUMMON_HOTKEY, IMG_TO_TEXT_HOTKEY)

    # keyboard.on_press for window-visible navigation redirect (best-effort)
    with contextlib.suppress(Exception):
        keyboard.on_press(nexus.on_global_key)

    # System tray icon
    tray = create_tray_icon(app, nexus)  # noqa: F841 — prevent GC
    nexus.tray = tray

    # If launched with --summon, show immediately
    if "--summon" in sys.argv:
        nexus.summon()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
