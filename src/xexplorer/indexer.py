"""Auto-split module."""

import os
import sqlite3
import time

from PyQt6.QtCore import QThread, pyqtSignal

from src.common.config import X_EXPLORER_DB as DB_PATH


class IndexerWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(int)

    def __init__(self, roots, ignore_list):
        super().__init__()
        self.roots = roots
        self.ignore_list = [i.lower() for i in ignore_list]
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=OFF")
        total, batch = 0, []
        BATCH = 5000

        for root_path in self.roots:
            if not self._running or not os.path.exists(root_path):
                continue
            for root, dirs, files in os.walk(root_path):
                if not self._running:
                    break
                dirs[:] = [
                    d
                    for d in dirs
                    if d.lower() not in self.ignore_list
                    and os.path.abspath(os.path.join(root, d)).lower()
                    not in self.ignore_list
                ]
                now = int(time.time())
                for d in dirs:
                    batch.append((os.path.join(root, d), d, root, 1, now))
                for f in files:
                    fp = os.path.abspath(os.path.join(root, f))
                    _, ext = os.path.splitext(f)
                    if (
                        f.lower() not in self.ignore_list
                        and fp.lower() not in self.ignore_list
                        and ext.lower() not in self.ignore_list
                    ):
                        batch.append((fp, f, root, 0, now))
                if len(batch) >= BATCH:
                    c.executemany(
                        "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)", batch
                    )
                    total += len(batch)
                    self.progress.emit(total, root[:70])
                    batch = []
                    conn.commit()

        if batch:
            c.executemany("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)", batch)
            total += len(batch)
            conn.commit()
        conn.close()
        self.finished.emit(total)
