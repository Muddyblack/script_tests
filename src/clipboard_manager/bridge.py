"""Clipboard Manager — QWebChannel bridge.

Exposes read/write operations on nexus_clipboard.db to the React UI.
The ClipboardWatcher (in watcher.py) keeps capturing in the background;
this bridge is the viewer/editor layer.
"""

import base64
import contextlib
import hashlib
import json
import sqlite3

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from src.clipboard_manager.watcher import CLIP_DB, ensure_db, get_watcher


class ClipboardBridge(QObject):
    # Signal → JS: fired whenever the watcher adds a new clip
    clip_added = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._conn = sqlite3.connect(CLIP_DB, check_same_thread=False)
        ensure_db(self._conn)

    # ── Queries ───────────────────────────────────────────────────────────

    @pyqtSlot(str, result=str)
    def get_clips(self, query: str) -> str:
        """Return JSON list of {id, content, pinned, ts, type} ordered pinned-first then newest.
        image_data is intentionally excluded — fetch separately via get_image_data(id).
        """
        q = query.strip().lower()
        if q:
            rows = self._conn.execute(
                """SELECT id, content, pinned, ts, type FROM clips
                   WHERE (type='text' AND lower(content) LIKE ?)
                   ORDER BY pinned DESC, ts DESC LIMIT 300""",
                (f"%{q}%",),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT id, content, pinned, ts, type FROM clips
                   ORDER BY pinned DESC, ts DESC LIMIT 300"""
            ).fetchall()
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
        import os
        import urllib.parse

        def _row_type(clip_type, content):
            if clip_type == "image":
                return "image"
            if clip_type == "text" and content:
                path = content.strip()
                if path.startswith("file:///"):
                    path = urllib.parse.unquote(path[8:])
                if os.path.splitext(path)[1].lower() in IMAGE_EXTS and os.path.isfile(path):
                    return "image_path"
            return clip_type

        return json.dumps([
            {"id": r[0], "content": r[1], "pinned": r[2], "ts": r[3],
             "type": _row_type(r[4], r[1])}
            for r in rows
        ])

    @pyqtSlot(result=int)
    def get_total(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]

    @pyqtSlot(int, result=str)
    def get_image_data(self, clip_id: int) -> str:
        """Return base64-encoded PNG for an image clip.
        Also handles text clips whose content is a path to an image file.
        """
        row = self._conn.execute(
            "SELECT image_data, type, content FROM clips WHERE id=?", (clip_id,)
        ).fetchone()
        if not row:
            return ""
        image_data, clip_type, content = row

        # Stored image blob
        if clip_type == "image" and image_data:
            return base64.b64encode(image_data).decode()

        # Text that looks like a local image file path
        if clip_type == "text" and content:
            import os
            path = content.strip()
            # Strip file:/// prefix if present
            if path.startswith("file:///"):
                import urllib.parse
                path = urllib.parse.unquote(path[8:])
                if not path.startswith("/"):
                    path = path  # Windows: C:/...
            IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
            if os.path.splitext(path)[1].lower() in IMAGE_EXTS and os.path.isfile(path):
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    return base64.b64encode(data).decode()
                except Exception:
                    pass
        return ""

    # ── Actions ───────────────────────────────────────────────────────────

    @pyqtSlot(int, result=bool)
    def copy_clip(self, clip_id: int) -> bool:
        """Copy a clip's content (text or image) to the system clipboard."""
        row = self._conn.execute(
            "SELECT content, type, image_data FROM clips WHERE id=?", (clip_id,)
        ).fetchone()
        if not row:
            return False
        content, clip_type, image_data = row

        if clip_type == "image" and image_data:
            from PyQt6.QtGui import QImage
            img = QImage()
            img.loadFromData(bytes(image_data), "PNG")
            if not img.isNull():
                h = hashlib.sha256(bytes(image_data)).hexdigest()
                watcher = get_watcher()
                if watcher is not None:
                    watcher.set_last_hash(h)
                QApplication.clipboard().setImage(img)
                return True
            return False

        # Text
        h = hashlib.sha256(content.encode()).hexdigest()
        watcher = get_watcher()
        if watcher is not None:
            watcher.set_last_hash(h)
        QApplication.clipboard().setText(content)
        return True

    @pyqtSlot(int, result=bool)
    def toggle_pin(self, clip_id: int) -> bool:
        row = self._conn.execute(
            "SELECT pinned FROM clips WHERE id=?", (clip_id,)
        ).fetchone()
        if not row:
            return False
        self._conn.execute(
            "UPDATE clips SET pinned=? WHERE id=?", (0 if row[0] else 1, clip_id)
        )
        self._conn.commit()
        return True

    @pyqtSlot(int, result=bool)
    def delete_clip(self, clip_id: int) -> bool:
        self._conn.execute("DELETE FROM clips WHERE id=?", (clip_id,))
        self._conn.commit()
        return True

    @pyqtSlot(result=bool)
    def clear_unpinned(self) -> bool:
        self._conn.execute("DELETE FROM clips WHERE pinned=0")
        self._conn.commit()
        return True

    def notify_clip_added(self) -> None:
        """Call this from the watcher integration to push updates to JS."""
        self.clip_added.emit()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._conn.close()
