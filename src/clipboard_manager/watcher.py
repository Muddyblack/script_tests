"""Always-on clipboard watcher — lives in the Nexus process forever.

Polls the system clipboard every 500 ms and persists every unique entry
to nexus_clipboard.db regardless of whether the Clipboard Manager GUI
is open.  The manager window is purely a *viewer* of this DB.
"""

import hashlib
import os
import sqlite3
import time

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication

try:
    from src.common.config import APPDATA
except ImportError:
    APPDATA = os.getenv("APPDATA", ".")

CLIP_DB = os.path.join(APPDATA, "nexus_clipboard.db")
MAX_HISTORY = 500
POLL_MS = 500

# ── module-level singleton so manager window can access it ────────────────────
_instance: "ClipboardWatcher | None" = None


def get_watcher() -> "ClipboardWatcher | None":
    """Return the running watcher (if Nexus created one)."""
    return _instance


def ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clips (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            content  TEXT NOT NULL,
            hash     TEXT NOT NULL,
            pinned   INTEGER NOT NULL DEFAULT 0,
            ts       REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON clips(hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts   ON clips(ts DESC)")
    conn.commit()


class ClipboardWatcher(QObject):
    """Lightweight always-on clipboard monitor.  Create once in app.py."""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        global _instance
        _instance = self

        self._conn = sqlite3.connect(CLIP_DB, check_same_thread=False)
        ensure_db(self._conn)
        self._last_hash = ""

        # Seed from whatever is already on the clipboard
        cb = QApplication.clipboard()
        txt = cb.text()
        if txt:
            self._last_hash = hashlib.sha256(txt.encode()).hexdigest()

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ── internal ──────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        try:
            cb = QApplication.clipboard()
            text = cb.text()
            if not text:
                return
            h = hashlib.sha256(text.encode()).hexdigest()
            if h == self._last_hash:
                return
            self._last_hash = h
            self._save(text, h)
        except Exception:
            pass

    def _save(self, content: str, h: str) -> None:
        row = self._conn.execute("SELECT id FROM clips WHERE hash=?", (h,)).fetchone()
        if row:
            self._conn.execute(
                "UPDATE clips SET ts=? WHERE id=?", (time.time(), row[0])
            )
        else:
            self._conn.execute(
                "INSERT INTO clips (content, hash, pinned, ts) VALUES (?,?,0,?)",
                (content, h, time.time()),
            )
            # Evict oldest unpinned beyond cap
            self._conn.execute(
                """DELETE FROM clips WHERE id IN (
                    SELECT id FROM clips WHERE pinned=0
                    ORDER BY ts DESC LIMIT -1 OFFSET ?
                )""",
                (MAX_HISTORY,),
            )
        self._conn.commit()

    # ── public (used by manager window when copying back) ─────────────────────

    def set_last_hash(self, h: str) -> None:
        """Tell the watcher that *we* just set the clipboard so it skips it."""
        self._last_hash = h
