"""Auto-split module."""

import os
import sqlite3
import time

from src.common.config import X_EXPLORER_DB as DB_PATH

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False



class LiveCacheUpdater(FileSystemEventHandler):
    def __init__(self, ignore_list):
        self.ignore_list = [i.lower() for i in ignore_list]
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._c = self._conn.cursor()

    def _skip(self, path):
        pl, nl = path.lower(), os.path.basename(path).lower()
        return any(ig in nl or ig in pl for ig in self.ignore_list)

    def on_created(self, event):
        if self._skip(event.src_path): return
        try:
            self._c.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)",
                (event.src_path, os.path.basename(event.src_path),
                 os.path.dirname(event.src_path),
                 1 if event.is_directory else 0, int(time.time())))
            self._conn.commit()
        except sqlite3.OperationalError: pass

    def on_deleted(self, event):
        try:
            self._c.execute("DELETE FROM files WHERE path=?", (event.src_path,))
            self._conn.commit()
        except sqlite3.OperationalError: pass

    def on_moved(self, event):
        self.on_deleted(event)
        class FE:
            def __init__(s,p,d): s.src_path=p; s.is_directory=d
        self.on_created(FE(event.dest_path, event.is_directory))


