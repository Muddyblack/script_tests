import threading

from PyQt6.QtCore import QObject, pyqtSignal

try:
    from pynput import keyboard as _kb  # type: ignore
except ImportError:
    _kb = None


class _HotkeyWindow(QObject):
    """Global hotkey listener using pynput.keyboard.Listener.
    
    Uses manual state tracking (set of pressed keys) instead of GlobalHotKeys
    to provide stricter triggers on Windows and avoid ghost modifier-only firings.
    """

    toggle_signal = pyqtSignal()
    ocr_signal = pyqtSignal()
    chronos_signal = pyqtSignal()
    theme_picker_signal = pyqtSignal()

    def start(self, toggle_hotkey: str, ocr_hotkey: str, chronos_hotkey: str) -> None:
        if _kb is None:
            print("[Hotkeys] pynput not available — global hotkeys disabled.")
            return

        # Map string hotkeys to sets of virtual key codes or key objects
        self._summon_keys = self._parse_hotkey(toggle_hotkey)
        self._ocr_keys = self._parse_hotkey(ocr_hotkey)
        self._chronos_keys = self._parse_hotkey(chronos_hotkey)
        self._chord_k_keys = self._parse_hotkey("ctrl+shift+k")
        self._chord_t_keys = self._parse_hotkey("ctrl+shift+t")

        self.pressed_keys = set()
        self._chord_context = False
        self._timer = None

        def on_press(key):
            # Normalise the key object to a string representation we can compare
            key_name = self._get_key_name(key)
            if not key_name:
                return

            # Avoid repeated triggers on hold
            if key_name in self.pressed_keys:
                return
                
            self.pressed_keys.add(key_name)
            self._check_hotkeys(key_name)

        def on_release(key):
            key_name = self._get_key_name(key)
            if key_name in self.pressed_keys:
                self.pressed_keys.remove(key_name)

        def _run() -> None:
            try:
                with _kb.Listener(on_press=on_press, on_release=on_release) as listener:
                    listener.join()
            except Exception as exc:
                print(f"[Hotkeys] listener error: {exc}")

        threading.Thread(target=_run, daemon=True, name="PynputHotkeyListener").start()

    def _get_key_name(self, key) -> str:
        """Resolve a pynput key object to a canonical string name."""
        if isinstance(key, _kb.Key):
            return key.name.replace("_", " ").lower()
        if hasattr(key, "char") and key.char:
            return key.char.lower()
        if hasattr(key, "vk") and key.vk:
            # Fallback for some virtual keys
            return f"vk_{key.vk}"
        return ""

    def _parse_hotkey(self, hotkey_str: str) -> set[str]:
        """Convert 'ctrl+shift+space' to a set{'ctrl', 'shift', 'space'}."""
        parts = set()
        for p in hotkey_str.lower().split("+"):
            p = p.strip()
            if p in ("control", "ctrl"): parts.add("ctrl")
            elif p in ("win", "windows", "cmd"): parts.add("cmd")
            elif p == "alt": parts.add("alt")
            elif p == "shift": parts.add("shift")
            else: parts.add(p)
        return parts

    def _check_hotkeys(self, trigger_key: str) -> None:
        """Check if current pressed_keys matches any defined hotkey.
        
        Strictness: a hotkey ONLY fires if trigger_key is part of it.
        This prevents Ctrl firing when it was already held and you pressed Shift.
        """
        def matches(target_set):
            return target_set.issubset(self.pressed_keys) and trigger_key in target_set

        if matches(self._summon_keys):
            self.toggle_signal.emit()
        elif matches(self._ocr_keys):
            self.ocr_signal.emit()
        elif matches(self._chronos_keys):
            self.chronos_signal.emit()
        elif matches(self._chord_k_keys):
            self._start_chord()
        elif matches(self._chord_t_keys):
            if self._chord_context:
                self.theme_picker_signal.emit()
                self._stop_chord()

    def _start_chord(self):
        self._chord_context = True
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(2.0, self._stop_chord)
        self._timer.start()

    def _stop_chord(self):
        self._chord_context = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
