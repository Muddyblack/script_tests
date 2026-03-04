import os
import sys

# Prevent Intel OpenMP conflict (torch vs Qt) which causes DLL load errors
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from PyQt6.QtWidgets import QApplication

from src.common.config import CHRONOS_HOTKEY, IMG_TO_TEXT_HOTKEY, SUMMON_HOTKEY

from .hotkeys import _HotkeyWindow
from .search import NexusSearch
from .tray import create_tray_icon
from .widgets import NexusBridge


def main():
    """Entry point for Nexus Search."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.search")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    nexus = NexusSearch()
    bridge = NexusBridge()

    # Thread-safe toggle: hotkey thread -> Qt main thread
    bridge.toggle_signal.connect(
        lambda: nexus.summon() if not nexus.isVisible() else nexus.hide()
    )
    bridge.snip_to_text_signal.connect(nexus.start_img_to_text)
    bridge.chronos_signal.connect(nexus.start_chronos)

    # RegisterHotKey-based hotkeys (Win) or pynput (Linux)
    hw = _HotkeyWindow()
    hw.toggle_signal.connect(bridge.toggle_signal)
    hw.ocr_signal.connect(bridge.snip_to_text_signal)
    hw.chronos_signal.connect(bridge.chronos_signal)
    hw.theme_picker_signal.connect(nexus.open_theme_picker_global)
    hw.start(SUMMON_HOTKEY, IMG_TO_TEXT_HOTKEY, CHRONOS_HOTKEY)

    # Pre-warm OCR worker in background so model is ready before first use
    from src.img_to_text.extractor import pre_warm as _ocr_prewarm

    _ocr_prewarm()

    # Start Ghost Typist watcher in background (no UI required)
    try:
        from src.ghost_typist.db import get_setting, init_db
        from src.ghost_typist.watcher import get_watcher

        init_db()
        nexus.ghost_watcher = get_watcher()
        if get_setting("watcher_enabled", "1") == "1":
            nexus.ghost_watcher.start()
    except Exception:
        # Best-effort: if watcher can't start, don't crash the app
        pass

    # Global input redirect (Best effort, usually requires sudo/root on Linux)
    if sys.platform == "win32":
        try:
            import keyboard

            keyboard.on_press(nexus.on_global_key)
        except Exception:
            pass

    # System tray icon
    tray = create_tray_icon(app, nexus)  # noqa: F841 — prevent GC
    nexus.tray = tray

    # If launched with --summon, show immediately
    if "--summon" in sys.argv:
        nexus.summon()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
