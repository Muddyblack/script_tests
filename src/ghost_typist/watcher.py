"""Ghost Typist — global keyboard watcher.

Uses the ``keyboard`` library (already a project dependency) to intercept
every keystroke system-wide, maintain a rolling text buffer and fire text
replacements when a snippet trigger is detected.

Special expansion tokens
------------------------
    __DATE__   → today's date  (YYYY-MM-DD)
    __TIME__   → current time  (HH:MM)
    __CLIP__   → current clipboard text (requires PyQt app running)
"""

import datetime
import threading

import keyboard  # type: ignore

from src.ghost_typist.db import get_all_snippets, increment_use

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
        self._hook_handle = None
        self._suppressing = False             # avoid reacting to own keystrokes

    # ── Public API ────────────────────────────────────────────────────────────

    def reload_snippets(self) -> None:
        """Refresh the in-memory trigger→expansion map from the DB."""
        rows = get_all_snippets()
        with self._lock:
            self._snippets = {r["trigger"]: r["expansion"] for r in rows}

    def start(self) -> None:
        """Attach global keyboard hook."""
        if self._running:
            return
        self.reload_snippets()
        self._buffer = ""
        self._hook_handle = keyboard.hook(self._on_key_event, suppress=False)
        self._running = True

    def stop(self) -> None:
        """Detach global keyboard hook."""
        if not self._running:
            return
        if self._hook_handle is not None:
            keyboard.unhook(self._hook_handle)
            self._hook_handle = None
        self._running = False
        self._buffer = ""

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_key_event(self, event: keyboard.KeyboardEvent) -> None:
        """Called for every key press/release system-wide."""
        if event.event_type != keyboard.KEY_DOWN:
            return
        if self._suppressing:
            return

        name: str = event.name or ""

        if name == "backspace":
            with self._lock:
                self._buffer = self._buffer[:-1]
            return

        if name in _RESET_KEYS or len(name) > 1:
            # Multi-char names like "ctrl", "alt", "f1", "enter" etc.
            # "enter" / "tab" / "space" → reset buffer (word boundary)
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
        """Delete typed trigger characters and type the expansion."""
        expansion = _resolve_expansion(expansion)

        self._suppressing = True
        try:
            # Erase the trigger (it was already typed into whatever app is focused)
            for _ in range(len(trigger)):
                keyboard.press_and_release("backspace")

            # Type the replacement
            keyboard.write(expansion, delay=0.004)
        finally:
            self._suppressing = False

        # Track usage (non-blocking)
        try:
            increment_use(trigger)
        except Exception:
            pass


# Module-level singleton
_watcher = SnippetWatcher()


def get_watcher() -> SnippetWatcher:
    return _watcher
