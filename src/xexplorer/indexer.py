"""Auto-split module."""

import os
import sqlite3
import time
from collections import deque

from PyQt6.QtCore import QThread, pyqtSignal

from src.common.config import X_EXPLORER_DB as DB_PATH


class IndexerWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(int)

    def __init__(self, roots, ignore_list):
        super().__init__()
        self.roots = roots
        self.ignore_list = set(i.lower() for i in ignore_list)
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
        IL = self.ignore_list

        for root_path in self.roots:
            if not self._running or not os.path.isdir(root_path):
                continue

            queue: deque[str] = deque([root_path])
            while queue and self._running:
                current = queue.popleft()
                try:
                    entries = list(os.scandir(current))
                except (OSError, PermissionError):
                    continue

                now = int(time.time())
                subdirs: list[str] = []

                for entry in entries:
                    if not self._running:
                        break
                    name = entry.name
                    name_lower = name.lower()
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        full_path = entry.path          # already absolute when parent is absolute
                        path_lower = full_path.lower()

                        if is_dir:
                            if name_lower not in IL and path_lower not in IL:
                                batch.append((full_path, name, current, 1, now, 0))
                                subdirs.append(full_path)
                        else:
                            _, ext = os.path.splitext(name)
                            ext_lower = ext.lower()
                            if name_lower not in IL and path_lower not in IL and ext_lower not in IL:
                                # entry.stat() on Windows reuses FindNextFile data — no extra syscall
                                try:
                                    size = entry.stat(follow_symlinks=False).st_size
                                except (OSError, PermissionError):
                                    size = 0
                                batch.append((full_path, name, current, 0, now, size))
                    except (OSError, PermissionError):
                        continue

                queue.extend(subdirs)

                if len(batch) >= BATCH:
                    c.executemany(
                        "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)", batch
                    )
                    total += len(batch)
                    self.progress.emit(total, current[:70])
                    batch = []
                    conn.commit()

        if batch:
            c.executemany("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)", batch)
            total += len(batch)
            conn.commit()
        conn.close()
        self.finished.emit(total)
