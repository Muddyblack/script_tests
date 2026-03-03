"""Auto-split module."""

import os
import sqlite3
import time

from src.common.config import X_EXPLORER_DB as DB_PATH

try:
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class LiveCacheUpdater(FileSystemEventHandler):
    def __init__(self, ignore_list):
        self.ignore_list = [i.lower() for i in ignore_list]
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._c = self._conn.cursor()
        self._c.execute("PRAGMA journal_mode=WAL")

    def _skip(self, path):
        pl, nl = path.lower(), os.path.basename(path).lower()
        return any(ig in nl or ig in pl for ig in self.ignore_list)

    def _notify(self):
        cb = getattr(self, 'file_changed', None)
        if callable(cb):
            cb()

    def on_created(self, event):
        if self._skip(event.src_path):
            return
        size = 0
        if not event.is_directory:
            try:
                size = os.path.getsize(event.src_path)
            except OSError:
                pass
        try:
            self._c.execute(
                "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)",
                (
                    event.src_path,
                    os.path.basename(event.src_path),
                    os.path.dirname(event.src_path),
                    1 if event.is_directory else 0,
                    int(time.time()),
                    size,
                ),
            )
            self._conn.commit()
            self._notify()
        except sqlite3.OperationalError:
            pass

    def on_deleted(self, event):
        try:
            self._c.execute("DELETE FROM files WHERE path=?", (event.src_path,))
            if event.is_directory:
                # Cascade: remove every child that lived inside the deleted folder.
                # Normalise to backslash (Windows) and strip any trailing separator
                # so the LIKE pattern matches both shallow and deep children.
                norm = event.src_path.replace("/", "\\").rstrip("\\")
                self._c.execute(
                    "DELETE FROM files WHERE path LIKE ?",
                    (norm + "\\%",),
                )
                # Also handle forward-slash stored paths
                norm_fwd = event.src_path.replace("\\", "/").rstrip("/")
                self._c.execute(
                    "DELETE FROM files WHERE path LIKE ?",
                    (norm_fwd + "/%",),
                )
            self._conn.commit()
            self._notify()
        except sqlite3.OperationalError:
            pass

    def on_moved(self, event):
        size = 0
        if not event.is_directory:
            try:
                size = os.path.getsize(event.dest_path)
            except OSError:
                pass
        try:
            self._c.execute("DELETE FROM files WHERE path=?", (event.src_path,))
            self._c.execute(
                "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)",
                (
                    event.dest_path,
                    os.path.basename(event.dest_path),
                    os.path.dirname(event.dest_path),
                    1 if event.is_directory else 0,
                    int(time.time()),
                    size,
                ),
            )
            self._conn.commit()
            self._notify()
        except sqlite3.OperationalError:
            pass
