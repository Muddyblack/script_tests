"""Always-on clipboard watcher — lives in the Nexus process forever.

Polls the system clipboard every 500 ms and persists every unique entry
to nexus_clipboard.db regardless of whether the Clipboard Manager GUI
is open.  The manager window is purely a *viewer* of this DB.

Supports both text and image clipboard content.
Images are stored as PNG bytes in the image_data BLOB column.
"""

import hashlib
import sqlite3
import time

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication

try:
    from src.common.config import CLIPBOARD_DB as CLIP_DB
except ImportError:
    import os as _os
    CLIP_DB = _os.path.join(_os.getenv("APPDATA", "."), "nexus_clipboard.db")

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

        # Use dataChanged signal for instant response + poll as fallback
        cb = QApplication.clipboard()
        cb.dataChanged.connect(self._on_changed)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._on_changed)
        self._timer.start()

    # ── internal ──────────────────────────────────────────────────────────────

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
        import os
        import urllib.parse
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

        urls = list(mime.urls()) if mime.hasUrls() else []
        if not urls and mime.hasFormat("text/uri-list"):
            raw = bytes(mime.data("text/uri-list")).decode("utf-8", "ignore")
            from PyQt6.QtCore import QUrl
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
                "INSERT INTO clips (content, hash, pinned, ts, type) VALUES (?,?,0,?,?)",
                (content, h, time.time(), "text"),
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
        """Remove oldest unpinned entries beyond MAX_HISTORY."""
        self._conn.execute(
            """DELETE FROM clips WHERE id IN (
                SELECT id FROM clips WHERE pinned=0
                ORDER BY ts DESC LIMIT -1 OFFSET ?
            )""",
            (MAX_HISTORY,),
        )

    # ── _save kept for backward compat (text only callers) ───────────────────
    def _save(self, content: str, h: str) -> None:
        self._save_text(content, h)

    # ── public ────────────────────────────────────────────────────────────────

    def set_last_hash(self, h: str) -> None:
        """Tell the watcher that *we* just set the clipboard so it skips it."""
        self._last_hash = h
