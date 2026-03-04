"""Ghost Typist — global keyboard watcher.

Uses ``pynput`` to intercept every keystroke system-wide, maintain a rolling
text buffer and fire text replacements when a snippet trigger is detected.
pynput works without administrator / sudo privileges on Windows and Linux
(X11/Wayland), unlike the ``keyboard`` library.

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


# Maximum characters we keep in the rolling buffer.
# Triggers longer than this will never match.
_BUFFER_MAXLEN = 64

# Delimiters that reset the buffer (end of "word" boundary detection).
# We intentionally do NOT reset on Space so multi-word expansions work;
# reset only on real delimiters that indicate "this word is finished".
_RESET_KEYS = {
    "esc", "delete", "left", "right", "up", "down",
    "home", "end", "page up", "page down",
}


def _resolve_expansion(text: str) -> str:
    """Substitute magic tokens with live values."""
    now = datetime.datetime.now()
    text = text.replace("__DATE__", now.strftime("%Y-%m-%d"))
    text = text.replace("__TIME__", now.strftime("%H:%M"))
    return text


class SnippetWatcher:
    """
    Singleton-style watcher.  Call `start()` / `stop()` to toggle.
    Call `reload_snippets()` to pick up DB changes without restarting.
    """

    def __init__(self) -> None:
        self._buffer: str = ""
        self._snippets: dict[str, str] = {}   # trigger → expansion
        self._lock = threading.Lock()
        self._running = False
        self._listener = None                 # pynput Listener
        self._suppressing = False             # avoid reacting to own keystrokes
        self._reload_thread: threading.Thread | None = None
        self._last_db_mtime: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def reload_snippets(self) -> None:
        """Refresh the in-memory trigger→expansion map from the DB."""
        rows = get_all_snippets()
        with self._lock:
            self._snippets = {r["trigger"]: r["expansion"] for r in rows}
        # Update mtime stamp so the polling thread doesn't double-reload
        try:
            if _DB_PATH and os.path.exists(_DB_PATH):
                self._last_db_mtime = os.path.getmtime(_DB_PATH)
        except Exception:
            pass

    def start(self) -> None:
        """Attach global keyboard listener + start background DB-change watcher."""
        if self._running:
            return
        if not _PYNPUT_AVAILABLE:
            print("[GhostTypist] pynput not available — watcher disabled.")
            return
        self.reload_snippets()
        self._buffer = ""
        self._listener = _kb.Listener(on_press=self._on_key_press)
        self._listener.start()
        self._running = True
        # Background thread: reload snippets automatically when DB file changes
        self._reload_thread = threading.Thread(
            target=self._db_reload_loop, daemon=True, name="gt-db-watcher"
        )
        self._reload_thread.start()

    def stop(self) -> None:
        """Stop the global keyboard listener."""
        if not self._running:
            return
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._running = False
        self._buffer = ""

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Internal ──────────────────────────────────────────────────────────────

    def _db_reload_loop(self) -> None:
        """Daemon thread: reload snippets whenever the DB file is modified."""
        while self._running:
            time.sleep(_AUTO_RELOAD_INTERVAL)
            if not self._running:
                break
            try:
                if _DB_PATH and os.path.exists(_DB_PATH):
                    mtime = os.path.getmtime(_DB_PATH)
                    if mtime != self._last_db_mtime:
                        self._last_db_mtime = mtime
                        self.reload_snippets()
            except Exception:
                pass

    def _on_key_press(self, key) -> None:
        """Called by pynput for every key-down event system-wide."""
        if self._suppressing:
            return

        # Resolve a normalised name: special Key enum → string, char → string
        if isinstance(key, _kb.Key):
            # key.name is e.g. "page_up", "esc", "ctrl_l" — normalise to spaced form
            name: str = key.name.replace("_", " ")
        elif hasattr(key, "char") and key.char:
            name = key.char
        else:
            return  # dead key or unresolvable

        if name == "backspace":
            with self._lock:
                self._buffer = self._buffer[:-1]
            return

        if not name or name in _RESET_KEYS or len(name) > 1:
            # Special / multi-char names (ctrl, alt, f1, enter …)
            # "enter" / "tab" / "space" → word boundary → reset buffer
            if name in ("enter", "tab", "space"):
                with self._lock:
                    self._buffer = ""
            return

        # Single printable character
        with self._lock:
            self._buffer = (self._buffer + name)[-_BUFFER_MAXLEN:]
            buf = self._buffer

        # Check every trigger
        matched_trigger: str | None = None
        matched_expansion: str | None = None
        with self._lock:
            for trigger, expansion in self._snippets.items():
                if buf.endswith(trigger):
                    matched_trigger = trigger
                    matched_expansion = expansion
                    break

        if matched_trigger and matched_expansion:
            # Clear buffer before we start emitting synthetic keys
            with self._lock:
                self._buffer = ""
            self._fire_replacement(matched_trigger, matched_expansion)

    def _fire_replacement(self, trigger: str, expansion: str) -> None:
        """Delete typed trigger characters and type the expansion.

        Plain text segments are sent via ``_controller.type()``; ``{key}``
        tokens are sent via ``_pynput_press_and_release()``.
        """
        if not _PYNPUT_AVAILABLE or _controller is None:
            return
        expansion = _resolve_expansion(expansion)
        parts = _parse_expansion(expansion)

        self._suppressing = True
        try:
            # Erase the trigger (it was already typed into whatever app is focused)
            for _ in range(len(trigger)):
                _controller.tap(_kb.Key.backspace)

            # Type the replacement, honouring {key} tokens
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

        # Track usage (non-blocking)
        with contextlib.suppress(Exception):
            increment_use(trigger)


# Module-level singleton
_watcher = SnippetWatcher()


def get_watcher() -> SnippetWatcher:
    return _watcher
