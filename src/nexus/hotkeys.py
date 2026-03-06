import threading

from PyQt6.QtCore import QObject, pyqtSignal

try:
    from pynput import keyboard as _kb  # type: ignore
except ImportError:
    _kb = None

# --------------------------------------------------------------------------
# Hotkey handling — pynput GlobalHotKeys
# --------------------------------------------------------------------------


def _fmt(hotkey_str: str) -> str:
    """Convert 'ctrl+shift+q' to pynput GlobalHotKeys format '<ctrl>+<shift>+q'.

    Any part that maps to a named pynput Key (modifier, special key, …) gets
    wrapped in angle brackets; plain single characters stay bare.
    """
    parts = []
    for p in hotkey_str.lower().split("+"):
        p = p.strip()
        if p == "control":
            p = "ctrl"
        elif p in ("win", "windows"):
            p = "cmd"
        if _kb is not None and hasattr(_kb.Key, p):
            parts.append(f"<{p}>")
        else:
            parts.append(p)
    return "+".join(parts)


class _HotkeyWindow(QObject):
    """Global hotkey listener backed by pynput.GlobalHotKeys.

    Works on Windows and Linux without administrator / sudo privileges
    """

    toggle_signal = pyqtSignal()
    ocr_signal = pyqtSignal()
    chronos_signal = pyqtSignal()
    theme_picker_signal = pyqtSignal()

    def start(self, toggle_hotkey: str, ocr_hotkey: str, chronos_hotkey: str) -> None:
        if _kb is None:
            print("[Hotkeys] pynput not available — global hotkeys disabled.")
            return

        # State machine for sequences (e.g. Ctrl+K -> Ctrl+T)
        self._chord_context = False
        self._timer = None

        def _reset_context():
            self._chord_context = False

        def on_chord_k():
            self._chord_context = True
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(2.0, _reset_context)
            self._timer.start()

        def on_chord_t():
            if self._chord_context:
                self.theme_picker_signal.emit()
                self._chord_context = False
                if self._timer:
                    self._timer.cancel()

        hotkeys = {
            _fmt(toggle_hotkey): self.toggle_signal.emit,
            _fmt(ocr_hotkey): self.ocr_signal.emit,
            _fmt(chronos_hotkey): self.chronos_signal.emit,
            # Chord sequence: First press Ctrl+Shift+K, then Ctrl+Shift+T within 2s
            _fmt("ctrl+shift+k"): on_chord_k,
            _fmt("ctrl+shift+t"): on_chord_t,
        }

        def _run() -> None:
            try:
                with _kb.GlobalHotKeys(hotkeys) as listener:
                    listener.join()
            except Exception as exc:
                print(f"[Hotkeys] listener error: {exc}")

        threading.Thread(target=_run, daemon=True, name="PynputHotkeyListener").start()
