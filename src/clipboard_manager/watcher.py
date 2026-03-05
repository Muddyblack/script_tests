"""Always-on clipboard watcher — lives in the Nexus process forever.

Polls the system clipboard every 500 ms and persists every unique entry
to nexus_clipboard.db regardless of whether the Clipboard Manager GUI
is open.  The manager window is purely a *viewer* of this DB.

Supports both text and image clipboard content.
Images are stored as PNG bytes in the image_data BLOB column.
"""

import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time

# Detect Wayland — on Wayland the compositor won't deliver clipboard events to
# unfocused windows, so Qt's dataChanged / mimeData() return stale/empty data
# when Nexus has no focused window.  wl-paste reads the Wayland clipboard
# directly and bypasses this restriction.
_WL_PASTE = shutil.which("wl-paste") if os.environ.get("WAYLAND_DISPLAY") else None

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication

try:
    from src.common.config import CLIPBOARD_DB as CLIP_DB
    from src.common.config import CLIPBOARD_SETTINGS_FILE
except ImportError:
    import os as _os
    CLIP_DB = _os.path.join(_os.getenv("APPDATA", "."), "nexus_clipboard.db")
    CLIPBOARD_SETTINGS_FILE = _os.path.join(
        _os.getenv("APPDATA", "."), "nexus_clipboard.json"
    )

DEFAULT_HISTORY_LIMIT = 50
POLL_MS = 500

# The user can tweak the history cap in this JSON file or via
# `NEXUS_CLIPBOARD_HISTORY_LIMIT`.
def _ensure_settings_file(default: int) -> None:
    if os.path.exists(CLIPBOARD_SETTINGS_FILE):
        return
    os.makedirs(os.path.dirname(CLIPBOARD_SETTINGS_FILE), exist_ok=True)
    with open(CLIPBOARD_SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump({"history_limit": default}, fh, indent=2)


def _load_history_limit() -> int:
    env_limit = os.getenv("NEXUS_CLIPBOARD_HISTORY_LIMIT")
    if env_limit:
        try:
            limit = int(env_limit)
        except ValueError:
            limit = None
        else:
            if limit > 0:
                return limit

    _ensure_settings_file(DEFAULT_HISTORY_LIMIT)
    try:
        with open(CLIPBOARD_SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        data = {}
    limit = data.get("history_limit")
    if isinstance(limit, int) and limit > 0:
        return limit
    return DEFAULT_HISTORY_LIMIT


HISTORY_LIMIT = _load_history_limit()


def get_watcher_enabled() -> bool:
    """Return True if the clipboard watcher is enabled (default: True)."""
    _ensure_settings_file(DEFAULT_HISTORY_LIMIT)
    try:
        with open(CLIPBOARD_SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        data = {}
    return data.get("watcher_enabled", True)


def set_watcher_enabled(enabled: bool) -> None:
    """Persist the watcher_enabled flag to the clipboard settings JSON."""
    _ensure_settings_file(DEFAULT_HISTORY_LIMIT)
    try:
        with open(CLIPBOARD_SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        data = {}
    data["watcher_enabled"] = enabled
    with open(CLIPBOARD_SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ── module-level singleton so manager window can access it ────────────────────
_instance: "ClipboardWatcher | None" = None


def get_watcher() -> "ClipboardWatcher | None":
    """Return the running watcher (if Nexus created one)."""
    return _instance


def ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clips (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            content     TEXT NOT NULL DEFAULT '',
            hash        TEXT NOT NULL,
            pinned      INTEGER NOT NULL DEFAULT 0,
            ts          REAL NOT NULL,
            type        TEXT NOT NULL DEFAULT 'text',
            image_data  BLOB
        )
    """)
    # Migrate existing DB: add columns if absent
    existing = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}
    if "type" not in existing:
        conn.execute("ALTER TABLE clips ADD COLUMN type TEXT NOT NULL DEFAULT 'text'")
    if "image_data" not in existing:
        conn.execute("ALTER TABLE clips ADD COLUMN image_data BLOB")
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

        # dataChanged fires instantly when Qt sees the change (unreliable on
        # Wayland without window focus — compositor only notifies focused clients)
        cb = QApplication.clipboard()
        cb.dataChanged.connect(self._on_changed)

        # Poll timer: on Wayland use wl-paste so we catch copies from any app
        # even when Nexus has no focused window.
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(
            self._poll_wayland if _WL_PASTE else self._on_changed
        )
        self._timer.start()
        self._running = True

        # Background settings sync: pick up enable/disable written by the
        # clipboard GUI subprocess or the tray, keeping state across processes.
        self._settings_timer = QTimer(self)
        self._settings_timer.setInterval(2000)
        self._settings_timer.timeout.connect(self._sync_enabled_state)
        self._settings_timer.start()

    # ── enable / disable ─────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        """Pause clipboard monitoring without destroying the watcher."""
        if not self._running:
            return
        self._timer.stop()
        with contextlib.suppress(RuntimeError, TypeError):
            QApplication.clipboard().dataChanged.disconnect(self._on_changed)
        self._running = False

    def start(self) -> None:
        """Resume clipboard monitoring."""
        if self._running:
            return
        cb = QApplication.clipboard()
        cb.dataChanged.connect(self._on_changed)
        self._timer.start()
        self._running = True

    def _sync_enabled_state(self) -> None:
        """Called every 2 s (main thread) to honour enable/disable written by
        another process (e.g. the clipboard GUI subprocess or the tray)."""
        try:
            should_run = get_watcher_enabled()
        except Exception:
            return
        if should_run and not self._running:
            self.start()
        elif not should_run and self._running:
            self.stop()

    # ── internal ─────────────────────────────────────────────────────────────

    def _on_changed(self) -> None:
        try:
            cb = QApplication.clipboard()
            mime = cb.mimeData()
            if not mime:
                return

            # ── Image blob (hasImage covers Snipping Tool, img_to_text, etc.) ──
            if mime.hasImage():
                img = cb.image()
                if not img.isNull():
                    png_bytes = self._qimage_to_png(img)
                    if png_bytes:
                        h = hashlib.sha256(png_bytes).hexdigest()
                        if h != self._last_hash:
                            self._last_hash = h
                            self._save_image(png_bytes, h)
                    # Image was present — don't fall through to text
                    return
                # hasImage() true but image() returned null — retry once after 150 ms
                QTimer.singleShot(150, self._on_changed)
                return

            # ── File URLs (Explorer "Copy", drag from img_to_text, etc.) ─────
            if mime.hasUrls() or mime.hasFormat("text/uri-list"):
                self._handle_file_urls(mime)
                return

            # ── Plain text ────────────────────────────────────────────────────
            text = cb.text()
            if not text:
                return
            h = hashlib.sha256(text.encode()).hexdigest()
            if h == self._last_hash:
                return
            self._last_hash = h
            self._save_text(text, h)

        except KeyboardInterrupt:
            return
        except Exception:
            pass

    def _handle_file_urls(self, mime) -> None:
        """Save image files copied via file-URL MIME (Explorer copy / drag)."""
        import urllib.parse

        from PyQt6.QtCore import QUrl

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

        urls = list(mime.urls()) if mime.hasUrls() else []
        if not urls and mime.hasFormat("text/uri-list"):
            raw = bytes(mime.data("text/uri-list")).decode("utf-8", "ignore")
            for line in raw.splitlines():
                line = line.strip()
                if line:
                    urls.append(QUrl(line))

        for url in urls:
            path = url.toLocalFile()
            if not path:
                raw = url.toString()
                for prefix in ("file:///", "file://", "file:"):
                    if raw.lower().startswith(prefix):
                        path = urllib.parse.unquote(raw[len(prefix):])
                        break
            if not path or not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() not in IMAGE_EXTS:
                continue
            try:
                with open(path, "rb") as f:
                    data = f.read()
                h = hashlib.sha256(data).hexdigest()
                if h != self._last_hash:
                    self._last_hash = h
                    self._save_image(data, h)
            except Exception:
                pass
            break  # only first image file

    def _poll_wayland(self) -> None:
        """Poll clipboard via wl-paste on Wayland.

        wl-paste bypasses the compositor restriction that prevents unfocused
        clients from receiving clipboard updates via the Wayland protocol.
        Text only — images still go through _on_changed via dataChanged signal.
        """
        try:
            result = subprocess.run(
                [_WL_PASTE, "--no-newline", "--type", "text/plain"],
                capture_output=True, timeout=0.4,
            )
            if result.returncode != 0:
                return
            text = result.stdout.decode("utf-8", errors="replace")
            if not text:
                return
            h = hashlib.sha256(text.encode()).hexdigest()
            if h == self._last_hash:
                return
            self._last_hash = h
            self._save_text(text, h)
        except Exception:
            pass

    # Keep old name as alias so nothing breaks
    def _poll(self) -> None:
        self._on_changed()

    @staticmethod
    def _qimage_to_png(img) -> bytes | None:
        """Convert QImage to PNG bytes via PyQt6 buffer."""
        try:
            from PyQt6.QtCore import QBuffer, QIODevice

            buf = QBuffer()
            buf.open(QIODevice.OpenMode.WriteOnly)
            img.save(buf, "PNG")
            data = bytes(buf.data())
            buf.close()
            return data if data else None
        except Exception:
            return None

    def _save_text(self, content: str, h: str) -> None:
        row = self._conn.execute("SELECT id FROM clips WHERE hash=?", (h,)).fetchone()
        if row:
            self._conn.execute("UPDATE clips SET ts=? WHERE id=?", (time.time(), row[0]))
        else:
            self._conn.execute(
                "INSERT INTO clips (content, hash, pinned, ts, type) VALUES (?,?,?,?,?)",
                (content, h, 0, time.time(), "text"),
            )
            self._evict()
        self._conn.commit()

    def _save_image(self, png_bytes: bytes, h: str) -> None:
        row = self._conn.execute("SELECT id FROM clips WHERE hash=?", (h,)).fetchone()
        if row:
            self._conn.execute("UPDATE clips SET ts=? WHERE id=?", (time.time(), row[0]))
        else:
            self._conn.execute(
                "INSERT INTO clips (content, hash, pinned, ts, type, image_data) VALUES (?,?,0,?,?,?)",
                ("", h, time.time(), "image", png_bytes),
            )
            self._evict()
        self._conn.commit()

    def _evict(self) -> None:
        """Remove oldest unpinned entries beyond HISTORY_LIMIT."""
        self._conn.execute(
            """DELETE FROM clips WHERE id IN (
                SELECT id FROM clips WHERE pinned=0
                ORDER BY ts DESC LIMIT -1 OFFSET ?
            )""",
            (HISTORY_LIMIT,),
        )

    # ── _save kept for backward compat (text only callers) ───────────────────
    def _save(self, content: str, h: str) -> None:
        self._save_text(content, h)

    # ── public ───────────────────────────────────────────────────────────────

    def set_last_hash(self, h: str) -> None:
        """Tell the watcher that *we* just set the clipboard so it skips it."""
        self._last_hash = h
