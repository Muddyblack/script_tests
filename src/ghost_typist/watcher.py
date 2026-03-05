"""Ghost Typist — global keyboard watcher.

On Wayland, pynput's X11 backend only intercepts keystrokes from XWayland
apps — it is blind to Wayland-native apps (browsers, most terminals, etc.).
This module therefore tries two backends in order:

  1. **evdev** (preferred on Linux): reads raw key events from
     ``/dev/input/event*`` directly, works for ALL apps regardless of display
     server.  Requires the user to be in the ``input`` group:
         sudo usermod -aG input $USER   (then log out/in)
     Uses libxkbcommon (via ctypes) to resolve keycodes → characters using the
     active keyboard layout.

  2. **pynput / X11** (fallback): works for XWayland apps only.  Used when
     evdev devices are not accessible.

Special expansion tokens
------------------------
    __DATE__        → today's date  (YYYY-MM-DD)
    __TIME__        → current time  (HH:MM)
    __CLIP__        → current clipboard text (requires PyQt app running)

Key tokens  (can be mixed with plain text)
------------------------------------------
    {tab}           → Tab key
    {enter}         → Enter / Return
    {space}         → Space
    {backspace}     → Backspace
    {up}/{down}/{left}/{right}  → arrow keys
    {home}/{end}/{pgup}/{pgdn}  → navigation
    {esc}           → Escape
    {del}           → Delete
    {f1} … {f12}    → function keys
    {ctrl+a}        → Ctrl+A  (any modifier+key combo)

    Example expansion:  John{tab}Doe{tab}jdoe@example.com{enter}
"""

import contextlib
import ctypes
import ctypes.util
import datetime
import os
import re
import threading
import time

try:
    from pynput import keyboard as _kb  # type: ignore

    _controller = _kb.Controller()
    _PYNPUT_AVAILABLE = True
except Exception:  # pragma: no cover
    _kb = None  # type: ignore
    _controller = None
    _PYNPUT_AVAILABLE = False

from src.ghost_typist.db import get_all_snippets, increment_use

try:
    from src.common.config import GHOST_TYPIST_DB as _DB_PATH
except Exception:
    _DB_PATH = None

# How often the background thread checks for DB changes (seconds)
_AUTO_RELOAD_INTERVAL = 2.0

# Regex that matches {key} tokens inside an expansion string.
_KEY_TOKEN_RE = re.compile(r"\{([^}]+)\}")

# Friendly aliases so users can type intuitive names
_KEY_ALIASES: dict[str, str] = {
    "pgup": "page up",
    "pgdn": "page down",
    "pgdown": "page down",
    "del": "delete",
    "ret": "enter",
    "return": "enter",
    "cr": "enter",
}

# Modifier key names — used to distinguish "hold this" from "tap this".
_MOD_NAMES = {"ctrl", "shift", "alt", "cmd"}

# ── Buffer / reset config ─────────────────────────────────────────────────────

# Maximum characters we keep in the rolling buffer.
_BUFFER_MAXLEN = 64

# Key names that reset the buffer (navigation / cursor movement).
_RESET_KEYS = {
    "esc", "delete", "left", "right", "up", "down",
    "home", "end", "page up", "page down",
}

# ── evdev backend ─────────────────────────────────────────────────────────────

def _try_evdev_backend():
    """Return (devices, xkb_state) if evdev + libxkbcommon are usable,
    else return (None, None).
    """
    # Only meaningful on Linux with Wayland or when pynput can't see all keys
    try:
        import evdev  # type: ignore
        import evdev.ecodes as ec  # type: ignore
    except ImportError:
        return None, None

    # Find keyboard devices we can open
    keyboards = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            if ec.EV_KEY in caps and ec.KEY_A in caps.get(ec.EV_KEY, []):
                keyboards.append(dev)
        except (PermissionError, OSError):
            pass

    if not keyboards:
        return None, None

    # Set up libxkbcommon for keycode → char resolution
    xkb = _load_xkb()
    if xkb is None:
        # evdev without char resolution — limited use, skip
        for d in keyboards:
            d.close()
        return None, None

    return keyboards, xkb


def _load_xkb():
    """Load libxkbcommon and return an opaque context dict, or None."""
    try:
        lib_name = ctypes.util.find_library("xkbcommon")
        if not lib_name:
            return None
        xkb = ctypes.CDLL(lib_name)

        # xkb_context_new
        xkb.xkb_context_new.restype = ctypes.c_void_p
        xkb.xkb_context_new.argtypes = [ctypes.c_uint]
        # xkb_keymap_new_from_names
        xkb.xkb_keymap_new_from_names.restype = ctypes.c_void_p
        xkb.xkb_keymap_new_from_names.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint
        ]
        # xkb_state_new
        xkb.xkb_state_new.restype = ctypes.c_void_p
        xkb.xkb_state_new.argtypes = [ctypes.c_void_p]
        # xkb_state_update_key
        xkb.xkb_state_update_key.restype = ctypes.c_int
        xkb.xkb_state_update_key.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int
        ]
        # xkb_state_key_get_utf8
        xkb.xkb_state_key_get_utf8.restype = ctypes.c_int
        xkb.xkb_state_key_get_utf8.argtypes = [
            ctypes.c_void_p, ctypes.c_uint,
            ctypes.c_char_p, ctypes.c_size_t,
        ]
        # xkb_state_key_get_one_sym
        xkb.xkb_state_key_get_one_sym.restype = ctypes.c_uint
        xkb.xkb_state_key_get_one_sym.argtypes = [
            ctypes.c_void_p, ctypes.c_uint
        ]

        ctx = xkb.xkb_context_new(0)
        if not ctx:
            return None
        keymap = xkb.xkb_keymap_new_from_names(ctx, None, 0)
        if not keymap:
            return None
        state = xkb.xkb_state_new(keymap)
        if not state:
            return None

        return {"lib": xkb, "state": state}
    except Exception:
        return None


# XKB key direction constants
_XKB_KEY_DOWN = 1
_XKB_KEY_UP   = 0

# XKB keysyms for special keys we care about
_XKB_SYM_BACKSPACE = 0xFF08
_XKB_SYM_ESCAPE    = 0xFF1B
_XKB_SYM_DELETE    = 0xFFFF
_XKB_SYM_RETURN    = 0xFF0D
_XKB_SYM_TAB       = 0xFF09
_XKB_SYM_SPACE     = 0x0020
_XKB_SYM_LEFT      = 0xFF51
_XKB_SYM_RIGHT     = 0xFF53
_XKB_SYM_UP        = 0xFF52
_XKB_SYM_DOWN      = 0xFF54
_XKB_SYM_HOME      = 0xFF50
_XKB_SYM_END       = 0xFF57
_XKB_SYM_PGUP      = 0xFF55
_XKB_SYM_PGDN      = 0xFF56

_XKB_RESET_SYMS = {
    _XKB_SYM_ESCAPE, _XKB_SYM_DELETE,
    _XKB_SYM_LEFT, _XKB_SYM_RIGHT, _XKB_SYM_UP, _XKB_SYM_DOWN,
    _XKB_SYM_HOME, _XKB_SYM_END, _XKB_SYM_PGUP, _XKB_SYM_PGDN,
}
_XKB_BUFFER_RESET_SYMS = {_XKB_SYM_RETURN, _XKB_SYM_TAB, _XKB_SYM_SPACE}


def _pynput_press_and_release(combo: str) -> None:
    """Press and release a key or modifier+key combo (e.g. 'ctrl+a', 'enter').

    Splits on '+' so 'ctrl+shift+z' → hold ctrl, hold shift, tap z, release.
    Multi-word names like 'page up' are converted to the underscore form
    pynput uses internally ('page_up').
    """
    if not _PYNPUT_AVAILABLE or _controller is None:
        return
    parts = [p.strip() for p in combo.lower().split("+")]
    modifiers: list = []
    key = None
    for part in parts:
        # Normalise aliases before lookup
        if part in ("control", "win", "windows"):
            part = "ctrl" if part == "control" else "cmd"
        if part in _MOD_NAMES:
            mod = getattr(_kb.Key, part, None)
            if mod is not None:
                modifiers.append(mod)
        else:
            # Try Key enum by name, then underscore form ("page up" → "page_up")
            pynput_key = getattr(_kb.Key, part, None) or getattr(_kb.Key, part.replace(" ", "_"), None)
            if pynput_key is None and len(part) == 1:
                pynput_key = _kb.KeyCode.from_char(part)
            if pynput_key is not None:
                key = pynput_key
    if key is None:
        return
    for mod in modifiers:
        _controller.press(mod)
    _controller.tap(key)
    for mod in reversed(modifiers):
        _controller.release(mod)


def _parse_expansion(text: str) -> list[tuple[str, str]]:
    """Split *text* into alternating plain-text and {key-token} segments.

    Returns a list of ``(kind, value)`` tuples where *kind* is either
    ``'text'`` or ``'key'``.
    """
    parts: list[tuple[str, str]] = []
    last = 0
    for m in _KEY_TOKEN_RE.finditer(text):
        if m.start() > last:
            parts.append(("text", text[last : m.start()]))
        raw = m.group(1).strip().lower()
        parts.append(("key", _KEY_ALIASES.get(raw, raw)))
        last = m.end()
    if last < len(text):
        parts.append(("text", text[last:]))
    return parts


def _resolve_expansion(text: str) -> str:
    """Substitute magic tokens with live values."""
    now = datetime.datetime.now()
    text = text.replace("__DATE__", now.strftime("%Y-%m-%d"))
    text = text.replace("__TIME__", now.strftime("%H:%M"))

    if "__CLIP__" in text:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            clip = app.clipboard().text()
            text = text.replace("__CLIP__", clip)

    return text


class SnippetWatcher:
    """
    Singleton-style watcher.  Call `start()` / `stop()` to toggle.
    Call `reload_snippets()` to pick up DB changes without restarting.

    Backend selection (Linux):
      - evdev  : tried first; works for ALL apps on X11 and Wayland.
                 Requires membership in the ``input`` group.
      - pynput : fallback; only intercepts keystrokes from XWayland apps.
    """

    def __init__(self) -> None:
        self._buffer: str = ""
        self._snippets: dict[str, str] = {}   # trigger → expansion
        self._lock = threading.Lock()
        self._running = False
        self._listener = None                 # pynput Listener (fallback)
        self._evdev_thread: threading.Thread | None = None
        self._evdev_devices: list | None = None
        self._xkb: dict | None = None
        self._suppressing = False             # avoid reacting to own keystrokes
        self._reload_thread: threading.Thread | None = None
        self._last_db_mtime: float = 0.0
        self._use_evdev = False

    # ── Public API ────────────────────────────────────────────────────────────

    def reload_snippets(self) -> None:
        """Refresh the in-memory trigger→expansion map from the DB."""
        rows = get_all_snippets()
        with self._lock:
            self._snippets = {r["trigger"]: r["expansion"] for r in rows}
        try:
            if _DB_PATH and os.path.exists(_DB_PATH):
                self._last_db_mtime = os.path.getmtime(_DB_PATH)
        except Exception:
            pass

    def start(self) -> None:
        """Attach global keyboard listener + start background DB-change watcher."""
        if self._running:
            return
        self.reload_snippets()
        self._buffer = ""

        # Try evdev first (works on Wayland + X11, requires input group)
        devices, xkb = _try_evdev_backend()
        if devices:
            self._evdev_devices = devices
            self._xkb = xkb
            self._use_evdev = True
            self._running = True
            self._evdev_thread = threading.Thread(
                target=self._evdev_loop, daemon=True, name="gt-evdev"
            )
            self._evdev_thread.start()
        elif _PYNPUT_AVAILABLE:
            self._use_evdev = False
            self._listener = _kb.Listener(on_press=self._on_key_press)
            self._listener.start()
            self._running = True
        else:
            print("[GhostTypist] No keyboard backend available — watcher disabled.")
            return

        self._reload_thread = threading.Thread(
            target=self._db_reload_loop, daemon=True, name="gt-db-watcher"
        )
        self._reload_thread.start()

    def stop(self) -> None:
        """Stop the global keyboard listener."""
        if not self._running:
            return
        self._running = False
        self._buffer = ""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._evdev_devices:
            for d in self._evdev_devices:
                with contextlib.suppress(Exception):
                    d.close()
            self._evdev_devices = None

    @property
    def is_running(self) -> bool:
        return self._running

    # ── evdev loop ────────────────────────────────────────────────────────────

    def _evdev_loop(self) -> None:
        """Read raw key events from all keyboard devices and process them."""
        try:
            import select

            import evdev.ecodes as ec  # type: ignore

            fds = {d.fd: d for d in self._evdev_devices}
            while self._running:
                try:
                    r, _, _ = select.select(list(fds.keys()), [], [], 0.5)
                except Exception:
                    break
                for fd in r:
                    dev = fds.get(fd)
                    if dev is None:
                        continue
                    try:
                        for event in dev.read():
                            if event.type != ec.EV_KEY:
                                continue
                            if self._suppressing:
                                continue
                            # event.value: 1=press, 2=repeat, 0=release
                            if event.value not in (1, 2):
                                # On release, update xkb state but don't process
                                if self._xkb:
                                    # evdev keycode → xkb keycode (evdev + 8)
                                    xkb_key = event.code + 8
                                    self._xkb["lib"].xkb_state_update_key(
                                        self._xkb["state"], xkb_key, _XKB_KEY_UP
                                    )
                                continue
                            self._process_evdev_key(event.code)
                    except (OSError, BlockingIOError):
                        pass
        except Exception:
            pass

    def _process_evdev_key(self, evdev_code: int) -> None:
        """Resolve an evdev keycode to a character and update the buffer."""
        xkb = self._xkb
        if xkb is None:
            return

        lib = xkb["lib"]
        state = xkb["state"]
        # evdev keycode → xkb keycode (xkb = evdev + 8)
        xkb_key = evdev_code + 8

        # Get the resolved keysym for the current modifier state
        sym = lib.xkb_state_key_get_one_sym(state, xkb_key)

        # Update modifier state (key down)
        lib.xkb_state_update_key(state, xkb_key, _XKB_KEY_DOWN)

        if sym == _XKB_SYM_BACKSPACE:
            with self._lock:
                self._buffer = self._buffer[:-1]
            return

        if sym in _XKB_RESET_SYMS:
            return

        if sym in _XKB_BUFFER_RESET_SYMS:
            with self._lock:
                self._buffer = ""
            return

        # Get the UTF-8 character(s) for this key + modifier state
        buf = ctypes.create_string_buffer(8)
        n = lib.xkb_state_key_get_utf8(state, xkb_key, buf, 8)
        if n <= 0:
            return
        try:
            char = buf.raw[:n].decode("utf-8")
        except UnicodeDecodeError:
            return

        # Only single printable characters go into the snippet buffer
        if len(char) != 1 or not char.isprintable():
            return

        with self._lock:
            self._buffer = (self._buffer + char)[-_BUFFER_MAXLEN:]
            current_buf = self._buffer

        self._check_triggers(current_buf)

    # ── pynput fallback ───────────────────────────────────────────────────────

    def _on_key_press(self, key) -> None:
        """Called by pynput for every key-down event system-wide."""
        if self._suppressing:
            return

        # Resolve a normalised name: special Key enum → string, char → string
        if isinstance(key, _kb.Key):
            name: str = key.name.replace("_", " ")
        elif hasattr(key, "char") and key.char is not None:
            name = key.char
        elif hasattr(key, "vk"):
            if 32 <= (key.vk or 0) <= 126:
                name = chr(key.vk)
            else:
                return
        else:
            return

        if name == "backspace":
            with self._lock:
                self._buffer = self._buffer[:-1]
            return

        if not name or name in _RESET_KEYS or len(name) > 1:
            if name in ("enter", "tab", "space"):
                with self._lock:
                    self._buffer = ""
            return

        with self._lock:
            self._buffer = (self._buffer + name)[-_BUFFER_MAXLEN:]
            buf = self._buffer

        self._check_triggers(buf)

    # ── shared trigger check ──────────────────────────────────────────────────

    def _check_triggers(self, buf: str) -> None:
        matched_trigger: str | None = None
        matched_expansion: str | None = None
        with self._lock:
            for trigger, expansion in self._snippets.items():
                if buf.endswith(trigger):
                    matched_trigger = trigger
                    matched_expansion = expansion
                    break

        if matched_trigger and matched_expansion:
            with self._lock:
                self._buffer = ""
            self._fire_replacement(matched_trigger, matched_expansion)

    # ── DB reload / enable-disable loop ──────────────────────────────────────

    def _db_reload_loop(self) -> None:
        while self._running:
            time.sleep(_AUTO_RELOAD_INTERVAL)
            if not self._running:
                break
            try:
                from src.ghost_typist.db import get_setting
                if get_setting("watcher_enabled", "1") != "1":
                    if self._listener is not None:
                        self._listener.stop()
                        self._listener = None
                    self._running = False
                    self._wait_for_reenable()
                    return

                if _DB_PATH and os.path.exists(_DB_PATH):
                    mtime = os.path.getmtime(_DB_PATH)
                    if mtime != self._last_db_mtime:
                        self._last_db_mtime = mtime
                        self.reload_snippets()
            except Exception:
                pass

    def _wait_for_reenable(self) -> None:
        from src.ghost_typist.db import get_setting
        while True:
            time.sleep(_AUTO_RELOAD_INTERVAL)
            try:
                if get_setting("watcher_enabled", "1") == "1":
                    self.start()
                    return
            except Exception:
                pass

    # ── expansion ─────────────────────────────────────────────────────────────

    def _fire_replacement(self, trigger: str, expansion: str) -> None:
        """Delete typed trigger characters and type the expansion."""
        if not _PYNPUT_AVAILABLE or _controller is None:
            return
        expansion = _resolve_expansion(expansion)
        parts = _parse_expansion(expansion)

        self._suppressing = True
        try:
            for _ in range(len(trigger)):
                _controller.tap(_kb.Key.backspace)
                time.sleep(0.008)

            for kind, value in parts:
                if kind == "key":
                    _pynput_press_and_release(value)
                else:
                    if value:
                        for char in value:
                            _controller.type(char)
                            time.sleep(0.004)
        finally:
            self._suppressing = False

        with contextlib.suppress(Exception):
            increment_use(trigger)


# Module-level singleton
_watcher = SnippetWatcher()


def get_watcher() -> SnippetWatcher:
    return _watcher
