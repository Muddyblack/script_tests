"""Live filesystem watcher for XExplorer.

Monitors indexed folders with watchdog and incrementally updates the SQLite
index DB so search results stay fresh without a full re-index.

Usage (see bridge.py _restart_watchers):
    handler = LiveCacheUpdater(ignore_rules)
    handler.file_changed = lambda: self.live_changed.emit()
    obs = Observer()
    obs.schedule(handler, path, recursive=True)
    obs.start()
"""

import os
import sqlite3
import threading
import time

from watchdog.events import FileSystemEventHandler

from src.common.config import X_EXPLORER_DB as DB_PATH

# Debounce: flush DB writes and notify UI at most once per N ms
_DEBOUNCE_MS = 800


def _should_ignore(path: str, ignore_set: set[str]) -> bool:
    """Return True if any path component or extension matches an ignore rule."""
    path_lower = path.lower()
    # Check full path prefix
    for rule in ignore_set:
        if rule.startswith("."):
            # extension rule
            if path_lower.endswith(rule):
                return True
        else:
            # folder name or full path — match any component
            rule_lower = rule.lower()
            if rule_lower in path_lower:
                return True
    return False


class LiveCacheUpdater(FileSystemEventHandler):
    """Watchdog event handler that keeps the XExplorer SQLite index up to date.

    After any batch of FS events it calls self.file_changed() (debounced)
    so the bridge can emit live_changed to the JS UI.
    """

    # Set by the bridge after construction:  handler.file_changed = lambda: ...
    file_changed = None  # type: ignore

    def __init__(self, ignore_rules: list[str]) -> None:
        super().__init__()
        self._ignore: set[str] = {r.lower() for r in ignore_rules if r}
        # Pending DB operations queued from watchdog threads
        self._lock = threading.Lock()
        self._pending: list[tuple] = []   # list of ('create'|'delete'|'move', ...)
        self._timer: threading.Timer | None = None

    # ── watchdog callbacks (called from watchdog thread) ───────────────────

    def on_created(self, event) -> None:
        path = event.src_path
        if _should_ignore(path, self._ignore):
            return
        self._enqueue(("create", path, event.is_directory))

    def on_deleted(self, event) -> None:
        path = event.src_path
        self._enqueue(("delete", path))

    def on_moved(self, event) -> None:
        src = event.src_path
        dst = event.dest_path
        if _should_ignore(dst, self._ignore):
            self._enqueue(("delete", src))
        else:
            self._enqueue(("move", src, dst, event.is_directory))

    def on_modified(self, event) -> None:
        if event.is_directory:
            return  # directory mtime changes are too noisy; handled by browse-poll
        path = event.src_path
        if _should_ignore(path, self._ignore):
            return
        self._enqueue(("modify", path))

    # ── internal ──────────────────────────────────────────────────────────

    def _enqueue(self, op: tuple) -> None:
        with self._lock:
            self._pending.append(op)
            # (Re)start the debounce timer
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(_DEBOUNCE_MS / 1000.0, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        """Apply all pending operations to the DB then notify the UI."""
        with self._lock:
            ops = self._pending[:]
            self._pending.clear()
            self._timer = None

        if not ops:
            return

        try:
            with sqlite3.connect(DB_PATH, timeout=5) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                c = conn.cursor()
                now = int(time.time())
                for op in ops:
                    kind = op[0]
                    try:
                        if kind == "create":
                            _, path, is_dir = op
                            self._upsert(c, path, bool(is_dir), now)
                        elif kind == "delete":
                            _, path = op
                            path_norm = path.replace("/", "\\")
                            # Delete the item itself and any children (if folder)
                            c.execute(
                                "DELETE FROM files WHERE path = ? OR path LIKE ?",
                                (path_norm, path_norm.rstrip("\\") + "\\%"),
                            )
                        elif kind == "move":
                            _, src, dst, is_dir = op
                            src_norm = src.replace("/", "\\")
                            dst_norm = dst.replace("/", "\\")
                            # Remove old entries
                            c.execute(
                                "DELETE FROM files WHERE path = ? OR path LIKE ?",
                                (src_norm, src_norm.rstrip("\\") + "\\%"),
                            )
                            # Insert new entry
                            self._upsert(c, dst, bool(is_dir), now)
                        elif kind == "modify":
                            _, path = op
                            try:
                                size = os.path.getsize(path)
                            except OSError:
                                size = 0
                            c.execute(
                                "UPDATE files SET last_seen=?, size=? WHERE path=?",
                                (now, size, path.replace("/", "\\")),
                            )
                    except Exception:
                        pass  # individual op errors must not break the batch
                conn.commit()
        except Exception:
            pass  # DB errors are non-fatal

        # Notify UI (called from background thread — bridge uses lambda that emits signal)
        if callable(self.file_changed):
            try:
                self.file_changed()
            except Exception:
                pass

    @staticmethod
    def _upsert(c: sqlite3.Cursor, path: str, is_dir: bool, now: int) -> None:
        """Insert or update a single file/folder entry."""
        path_norm = path.replace("/", "\\")
        name = os.path.basename(path_norm) or path_norm
        parent = os.path.dirname(path_norm)
        try:
            size = 0 if is_dir else os.path.getsize(path)
        except OSError:
            size = 0
        c.execute(
            "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?)",
            (path_norm, name, parent, int(is_dir), now, size),
        )
