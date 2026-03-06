"""XExplorer-HTML — PyQt/JS bridge.

Exposes every operation the React UI needs via pyqtSlot.
Reuses the existing database, indexer, watcher and SearchEngine backends
unchanged — only the frontend is replaced.
"""

import base64
import contextlib
import html
import json
import os
import queue as _queue
import shutil
import sqlite3
import sys
import threading
import time

from PyQt6.QtCore import QFileInfo, QObject, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFileIconProvider,
    QInputDialog,
    QMessageBox,
)

from src.common.config import X_EXPLORER_DB as DB_PATH
from src.common.search_engine import SearchEngine
from src.xexplorer.database import init_db
from src.xexplorer.indexer import IndexerWorker

try:
    from watchdog.observers import Observer
    from watchdog.observers.polling import PollingObserver

    from src.xexplorer.watcher import LiveCacheUpdater

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


# ── helpers ───────────────────────────────────────────────────────────────────


def _is_network_path(path: str) -> bool:
    """Return True if *path* lives on a network / UNC share."""
    if sys.platform != "win32" or not path:
        return False
    norm = path.replace("/", "\\")
    if norm.startswith("\\\\"):  # already a UNC path
        return True
    if len(norm) >= 2 and norm[1] == ":":
        drive_root = norm[0].upper() + ":\\"
        try:
            import ctypes

            DRIVE_REMOTE = 4
            return ctypes.windll.kernel32.GetDriveTypeW(drive_root) == DRIVE_REMOTE
        except Exception:
            pass
    return False


def _fmt_size(path: str, is_dir: bool) -> str:
    if is_dir:
        return ""
    try:
        b = os.path.getsize(path)
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.0f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except OSError:
        return ""


def _fmt_size_stat(size_bytes: int, is_dir: bool) -> str:
    """Format size from an already-retrieved stat value (no extra I/O)."""
    if is_dir:
        return ""
    b: float = size_bytes
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def _fmt_mtime(path: str) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
    except OSError:
        return ""


def _fmt_mtime_stat(mtime: float) -> str:
    """Format mtime from an already-retrieved stat value (no extra I/O)."""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
    except Exception:
        return ""


def _db_size_mb() -> float:
    try:
        return os.path.getsize(DB_PATH) / (1024 * 1024)
    except OSError:
        return 0.0


# ── Bridge ─────────────────────────────────────────────────────────────────────────────────


class XExplorerBridge(QObject):
    # Signals → JS
    indexing_progress = pyqtSignal(int, str)  # count, current_path
    indexing_done = pyqtSignal(int, float)  # count, seconds
    stats_updated = pyqtSignal(str)  # JSON stats blob
    live_changed = pyqtSignal()  # watcher detected FS change
    # Signal → Python (caught by xexplorer window to spawn child)
    open_window_requested = pyqtSignal(str)  # path to pre-navigate
    # Signal → JS (sent to a target window when a tab is dropped onto it)
    tab_incoming = pyqtSignal(str)  # JSON {path, title}
    # Async file-op progress/done
    file_op_progress = pyqtSignal(
        str, int, int, str
    )  # op_id, done, total, current_name
    file_op_done = pyqtSignal(str, str)  # op_id, JSON {errors:[]}
    # Async preview (heavy renderers like win32com PPT)
    preview_ready = pyqtSignal(str)  # JSON blob (same schema as get_preview_page)
    # Async search
    search_results = pyqtSignal(str, str)  # query, JSON results
    # Database ready signal
    db_ready = pyqtSignal()  # emitted when database cache is warmed

    def __init__(self, initial_path: str = "") -> None:
        super().__init__()
        init_db()
        self._search_engine = SearchEngine(DB_PATH)

        # Warm database cache and emit signal when ready
        def _warm_and_signal():
            self._search_engine.warm_cache()
            # Wait for warming to complete (it runs in a thread)
            import time
            time.sleep(0.5)  # Give it time to warm
            self.db_ready.emit()

        threading.Thread(target=_warm_and_signal, daemon=True).start()

        self._worker: IndexerWorker | None = None
        self._observers: list = []
        self._icon_provider = QFileIconProvider()
        self._icon_cache: dict[str, str] = {}
        self._start_time: float = 0.0
        self._current_roots: list[str] = []
        self._initial_path: str = initial_path
        self._auto_reindex_timer: QTimer | None = None
        # Browse-folder change poller — emits live_changed when the currently
        # viewed folder's mtime changes (covers non-indexed paths too).
        self._browse_poll_path: str = ""
        self._browse_poll_mtime: float = 0.0
        self._browse_poll_timer = QTimer(self)
        self._browse_poll_timer.setInterval(750)
        self._browse_poll_timer.timeout.connect(self._poll_browse_dir)
        self._browse_poll_timer.start()
        # Thread-safe relay queue: worker threads post events here instead of
        # emitting signals directly (cross-thread signal emission via the
        # WebEngine bridge is unreliable from plain Python threads).
        self._op_emit_queue: _queue.Queue = _queue.Queue()
        self._cancel_flags: dict[str, threading.Event] = {}
        # Preview async state (key = "<abs_path>|<page>")
        self._preview_cache: dict[str, str] = {}
        self._preview_in_flight: set[str] = set()
        self._preview_cancel: dict[str, threading.Event] = {}  # key → cancel flag
        self._preview_lock = threading.Lock()  # Serialize heavy renders
        self._op_flush_timer = QTimer(self)
        self._op_flush_timer.setInterval(50)  # flush 20×/s
        self._op_flush_timer.timeout.connect(self._flush_op_queue)
        self._op_flush_timer.start()

    # ── Op-queue flush (main-thread relay for worker-thread signals) ─────────

    def _flush_op_queue(self) -> None:
        """Called by QTimer on the main thread; relays queued signal emissions."""
        try:
            while True:
                item = self._op_emit_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, op_id, done, total, current = item
                    self.file_op_progress.emit(op_id, done, total, current)
                elif kind == "done":
                    _, op_id, json_str = item
                    self.file_op_done.emit(op_id, json_str)
                    self.live_changed.emit()
                    # Clean up cancel flag
                    self._cancel_flags.pop(op_id, None)
                elif kind == "preview":
                    _, key, json_str = item
                    self._preview_cache[key] = json_str
                    self._preview_in_flight.discard(key)
                    self.preview_ready.emit(json_str)
                elif kind == "search_results":
                    _, query_str, json_results = item
                    self.search_results.emit(query_str, json_results)
        except _queue.Empty:
            pass

    # ── Browse-path polling ──────────────────────────────────────────────────

    @pyqtSlot(str)
    def set_active_browse_path(self, path: str) -> None:
        """JS calls this every time the active tab navigates to a new folder."""
        self._browse_poll_path = path
        # Never call os.stat() on a UNC/network path from the main thread —
        # a slow/unreachable share blocks the entire Qt event loop.
        if _is_network_path(path):
            self._browse_poll_mtime = 0.0
            return
        try:
            self._browse_poll_mtime = os.stat(path).st_mtime if path else 0.0
        except OSError:
            self._browse_poll_mtime = 0.0

    def _poll_browse_dir(self) -> None:
        """Check if the watched browse folder changed; fire live_changed if so."""
        path = self._browse_poll_path
        if not path:
            return
        # Skip polling for UNC/network locations — the PollingObserver in
        # _restart_watchers already covers them, and os.stat on a slow/gone
        # share would stall the main thread every 750 ms.
        if _is_network_path(path):
            return
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            # Drive removed (e.g. USB unplugged) — stop polling this path so
            # we don't spam live_changed, and clear it so the UI doesn't freeze.
            self._browse_poll_path = ""
            self._browse_poll_mtime = 0.0
            self.live_changed.emit()  # let UI know the listing is now stale
            return
        if mtime != self._browse_poll_mtime:
            self._browse_poll_mtime = mtime
            self.live_changed.emit()

    # ── Window management ─────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_initial_path(self) -> str:
        """Return the path this window should navigate to on startup (or empty)."""
        p = self._initial_path
        self._initial_path = ""
        return p

    @pyqtSlot(str)
    def open_new_window(self, path: str) -> None:
        """Ask the host Qt window to open a new XExplorer window at *path*."""
        self.open_window_requested.emit(path)

    @pyqtSlot()
    def close_window(self) -> None:
        """Close the host Qt window (used when the last tab is torn off)."""
        from src.xexplorer.xexplorer import _open_windows

        for win in list(_open_windows) + list(QApplication.topLevelWidgets()):
            if hasattr(win, "bridge") and win.bridge is self:
                win.close()
                return

    @pyqtSlot(str, str)
    def drop_tab(self, path: str, title: str) -> None:
        """Handle a torn-off tab drop.

        Uses QCursor.pos() (always in Qt screen coordinates, DPI-correct) to
        detect whether another XExplorer window is under the cursor.  If one is
        found it receives the tab via tab_incoming; otherwise a new window is
        spawned.
        """
        import json

        from PyQt6.QtGui import QCursor

        from src.xexplorer.xexplorer import _open_windows  # lazy to avoid circular

        cursor = QCursor.pos()
        candidates: list = []
        seen_ids: set[int] = set()
        for win in list(_open_windows) + list(QApplication.topLevelWidgets()):
            if not hasattr(win, "bridge"):
                continue
            if id(win) in seen_ids:
                continue
            seen_ids.add(id(win))
            if win.bridge is self:
                continue  # skip the source window
            if not win.isVisible():
                continue
            candidates.append(win)
            if win.frameGeometry().contains(cursor) or win.geometry().contains(
                win.mapFromGlobal(cursor)
            ):
                win.bridge.tab_incoming.emit(json.dumps({"path": path, "title": title}))
                return
        # Fallback: snap to the nearest other window if cursor is very close
        # (helps with multi-monitor / DPI coordinate edge cases).
        nearest = None
        nearest_dist = 10**9
        for win in candidates:
            rect = win.frameGeometry()
            dx = max(rect.left() - cursor.x(), 0, cursor.x() - rect.right())
            dy = max(rect.top() - cursor.y(), 0, cursor.y() - rect.bottom())
            dist = dx + dy
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = win
        if nearest is not None and nearest_dist <= 80:
            nearest.bridge.tab_incoming.emit(json.dumps({"path": path, "title": title}))
            return
        # No target window found — open a brand-new window
        self.open_window_requested.emit(path)

    # ── Config ───────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_config(self) -> str:
        """Return {folders:[{path,label}], ignore:[{rule,enabled}]}"""
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            # Folders
            c.execute("SELECT value FROM settings WHERE key='folders'")
            res = c.fetchone()
            folders: list[dict] = []
            if res:
                try:
                    for f in json.loads(res[0]):
                        path = f.get("path", "")
                        label = f.get("label", path)
                        folders.append({"path": path, "label": label})
                except (json.JSONDecodeError, TypeError):
                    pass

            # Ignore rules
            win_dir = os.environ.get("SYSTEMROOT", "C:\\Windows")
            prog_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
            prog_x86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
            defaults = [
                # ── Python ───────────────────────────────────────────────────
                "venv",
                ".venv",
                "env",
                ".env",
                "__pycache__",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                ".tox",
                ".nox",
                "eggs",
                ".eggs",
                "*.egg-info",
                "*.pyc",
                "*.pyo",
                "*.pyd",
                # ── JS / Node ─────────────────────────────────────────────────
                "node_modules",
                ".pnp",
                ".yarn",
                ".npm",
                ".pnpm-store",
                # ── Version control ──────────────────────────────────────────
                ".git",
                ".svn",
                ".hg",
                ".bzr",
                # ── IDEs & editors ────────────────────────────────────────────
                ".idea",
                ".vscode",
                ".vs",
                ".fleet",
                ".eclipse",
                # ── Build & dist outputs ──────────────────────────────────────
                "dist",
                "build",
                "out",
                "target",
                "bin",
                "obj",
                "__pycache__",
                ".next",
                ".nuxt",
                ".svelte-kit",
                ".parcel-cache",
                ".turbo",
                ".gradle",
                ".m2",
                # ── Compiled / binary extensions ──────────────────────────────
                ".exe",
                ".dll",
                ".so",
                ".dylib",
                ".sys",
                ".pdb",
                ".o",
                ".a",
                ".lib",
                ".class",
                ".jar",
                # ── Temp / generated ─────────────────────────────────────────
                ".tmp",
                ".temp",
                ".cache",
                ".pyc",
                ".log",
                "thumbs.db",
                "desktop.ini",
                # ── macOS noise ───────────────────────────────────────────────
                ".DS_Store",
                ".Spotlight-V100",
                ".Trashes",
                ".fseventsd",
                "__MACOSX",
                # ── Linux noise ───────────────────────────────────────────────
                ".Trash-1000",
                ".thumbnails",
                # ── Windows system ────────────────────────────────────────────
                "AppData",
                "Local Settings",
                "System Volume Information",
                "$RECYCLE.BIN",
                win_dir,
                prog_files,
                prog_x86,
                "C:\\MSOCache",
                "C:\\$Recycle.Bin",
                # ── Docker / containers ───────────────────────────────────────
                ".docker",
                # ── Rust ─────────────────────────────────────────────────────
                # (target/ already in build outputs above)
                # ── Go ────────────────────────────────────────────────────────
                "vendor",
                # ── Coverage / reports ────────────────────────────────────────
                ".coverage",
                "coverage",
                "htmlcov",
                ".nyc_output",
                # ── Secrets / env files ───────────────────────────────────────
                ".env.local",
                ".env.production",
                ".env.development",
            ]
            c.execute("SELECT value FROM settings WHERE key='ignore'")
            res2 = c.fetchone()
            current: dict[str, bool] = {}
            if res2:
                for raw in res2[0].split("|"):
                    if ":" in raw:
                        rule, st = raw.rsplit(":", 1)
                        current[rule] = st == "1"
                    elif raw:
                        current[raw] = True
            for d in defaults:
                if d not in current:
                    current[d] = True
            ignore = [
                {"rule": k, "enabled": v}
                for k, v in sorted(current.items(), key=lambda x: x[0].lower())
            ]

        # Start filesystem watchers on first config load (and whenever config is re-read)
        if folders and not self._observers:
            self._restart_watchers(folders)
            self._schedule_auto_reindex(folders)

        return json.dumps({"folders": folders, "ignore": ignore})

    @pyqtSlot(str)
    def save_config(self, json_str: str) -> None:
        data = json.loads(json_str)
        folders_json = json.dumps(data.get("folders", []))
        ignore_parts = [
            f"{r['rule']}:{'1' if r['enabled'] else '0'}"
            for r in data.get("ignore", [])
        ]
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES(?,?)", ("folders", folders_json)
            )
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES(?,?)",
                ("ignore", "|".join(ignore_parts)),
            )
            conn.commit()
        # _restart_watchers is async — returns immediately, work happens in a thread
        self._restart_watchers(data.get("folders", []))

    # ── Folder / drive management ─────────────────────────────────────────────

    @pyqtSlot(result=str)
    def pick_folder(self) -> str:
        path = QFileDialog.getExistingDirectory(None, "Select Folder to Index")
        if path:
            return path.replace("/", "\\")
        return ""

    @pyqtSlot(result=str)
    def get_drives(self) -> str:
        drives = []
        if sys.platform == "win32":
            try:
                import ctypes

                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    if bitmask & (1 << (ord(letter) - 65)):
                        drives.append(f"{letter}:\\")
            except Exception:
                drives = []
        else:
            drives = ["/"]
        return json.dumps(drives)

    @pyqtSlot(str, result=str)
    def list_folder(self, path: str) -> str:
        """Return JSON list of items in a directory (same schema as search)."""
        if not path:
            return json.dumps([])
        # os.path.isdir() blocks the main thread on UNC/network paths that are
        # slow or unreachable. Skip the guard for those — os.scandir() below
        # will raise OSError if the path is not a valid directory anyway.
        if not _is_network_path(path) and not os.path.isdir(path):
            return json.dumps([])
        items: list[dict] = []
        try:
            with os.scandir(path) as it:
                entries = sorted(
                    it,
                    key=lambda e: (not e.is_dir(follow_symlinks=True), e.name.lower()),
                )
            for entry in entries:
                try:
                    is_dir = entry.is_dir(follow_symlinks=True)
                    ext = (
                        ""
                        if is_dir
                        else os.path.splitext(entry.name)[1].lstrip(".").lower()
                    )
                    # Reuse the stat that scandir already fetched via FindNextFile
                    # (on Windows this is free — no extra syscall, even on network shares).
                    # Avoids a separate getsize()+getmtime() round-trip per file.
                    try:
                        st = entry.stat(follow_symlinks=False)
                        size = _fmt_size_stat(st.st_size, is_dir)
                        mtime = _fmt_mtime_stat(st.st_mtime)
                    except OSError:
                        size, mtime = "", ""
                    items.append(
                        {
                            "path": entry.path,
                            "name": entry.name,
                            "is_dir": is_dir,
                            "ext": ext,
                            "size": size,
                            "mtime": mtime,
                        }
                    )
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            return json.dumps([])
        return json.dumps(items)

    @pyqtSlot(str, result=str)
    def get_drive_info(self, path: str) -> str:
        """Return JSON {label, total_gb, free_gb, used_pct} for a path."""
        info: dict = {"label": "", "total_gb": 0.0, "free_gb": 0.0, "used_pct": 0}
        if sys.platform == "win32":
            try:
                import ctypes

                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(path),
                    None,
                    ctypes.byref(total_bytes),
                    ctypes.byref(free_bytes),
                )
                total_gb = total_bytes.value / (1024**3)
                free_gb = free_bytes.value / (1024**3)
                used_pct = round((1 - free_gb / total_gb) * 100) if total_gb else 0
                label_buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(path),
                    label_buf,
                    256,
                    None,
                    None,
                    None,
                    None,
                    0,
                )
                info = {
                    "label": label_buf.value,
                    "total_gb": round(total_gb, 1),
                    "free_gb": round(free_gb, 1),
                    "used_pct": used_pct,
                }
            except Exception:
                pass
        return json.dumps(info)

    @pyqtSlot(str)
    def add_ignore_rule(self, rule: str) -> None:
        """Append a new ignore rule to the persisted config (state=enabled)."""
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='ignore'")
            res = c.fetchone()
            current = res[0] if res else ""
            # Avoid duplicates
            existing = {r.rsplit(":", 1)[0] for r in current.split("|") if r}
            if rule not in existing:
                new_val = (current + "|" if current else "") + f"{rule}:1"
                c.execute(
                    "INSERT OR REPLACE INTO settings VALUES(?,?)", ("ignore", new_val)
                )
                conn.commit()

    @pyqtSlot(result=str)
    def prompt_ignore_rule(self) -> str:
        """Open a Qt dialog to ask for a rule string; returns it or empty string."""
        rule, ok = QInputDialog.getText(
            None, "Add Ignore Rule", "Folder name, extension, or path:"
        )
        return rule if ok and rule else ""

    # ── Favorites ─────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_favorites(self) -> str:
        """Return JSON list of [{path, label, icon}] favourites."""
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='favorites'")
            res = c.fetchone()
            if res:
                try:
                    return res[0]
                except Exception:
                    pass
        return "[]"

    @pyqtSlot(str)
    def save_favorites(self, json_str: str) -> None:
        """Persist the favorites list."""
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES(?,?)", ("favorites", json_str)
            )
            conn.commit()


    # ── Search ────────────────────────────────────────────────────────────────

    @pyqtSlot(str, str, str)
    def search_async(self, query: str, filter_type: str, folders_json: str) -> None:
        """Kicks off a search in a background thread to avoid freezing the UI.
        Emits search_results(query, results_json) when done.
        """

        def _run():
            res = self.search(query, filter_type, folders_json)
            self._op_emit_queue.put(("search_results", query, res))

        threading.Thread(target=_run, daemon=True).start()

    @pyqtSlot(str, str, str, result=str)
    def search(self, query: str, filter_type: str, folders_json: str) -> str:
        """Return JSON list of {path, name, is_dir, size, mtime, ext}.

        Everything comes from the local SQLite index — **zero** filesystem I/O.
        This keeps search instant regardless of whether the indexed folders are
        on a local drive, a USB stick, or a slow/offline network share.
        """
        folder_paths: list[str] = json.loads(folders_json) if folders_json else []
        if not folder_paths:
            return "[]"
        terms = query.strip().split()
        if len(query.strip()) < 2:
            return "[]"

        if filter_type == "content":
            raw = self._search_engine.search_content(
                query_terms=terms, target_folders=folder_paths
            )
            # content search returns (path, is_dir, ...) — no size column
            results = []
            for r in raw[:3000]:
                path, is_dir = r[0], r[1]
                name = os.path.basename(path) or path
                _, ext = os.path.splitext(name)
                results.append(
                    {
                        "path": path,
                        "name": name,
                        "is_dir": bool(is_dir),
                        "size": "",
                        "mtime": "",
                        "ext": ext.lower().lstrip("."),
                    }
                )
            return json.dumps(results)

        raw = self._search_engine.search_files(
            query_terms=terms,
            target_folders=folder_paths,
            files_only=(filter_type == "files"),
            folders_only=(filter_type == "folders"),
        )

        results = []
        for r in raw[:3000]:
            path, is_dir, name, size = r[0], r[1], r[2], r[3]
            _, ext = os.path.splitext(name)
            results.append(
                {
                    "path": path,
                    "name": name,
                    "is_dir": bool(is_dir),
                    "size": _fmt_size_stat(size or 0, bool(is_dir)),
                    "mtime": "",  # not stored in DB; avoids per-file stat
                    "ext": ext.lower().lstrip("."),
                }
            )
        return json.dumps(results)

    # ── Indexing ──────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def start_indexing(self, paths_json: str) -> None:
        roots: list[str] = json.loads(paths_json)
        if not roots:
            return
        ignore_rules = self._get_active_ignore_rules()
        self._current_roots = roots
        self._start_time = time.time()
        self._worker = IndexerWorker(roots, ignore_rules)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    @pyqtSlot()
    def stop_indexing(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()

    def _get_active_ignore_rules(self) -> list[str]:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='ignore'")
            res = c.fetchone()
        rules = []
        if res:
            for raw in res[0].split("|"):
                if ":" in raw:
                    rule, st = raw.rsplit(":", 1)
                    if st == "1":
                        rules.append(rule)
                elif raw:
                    rules.append(raw)
        return rules

    def _on_progress(self, count: int, msg: str) -> None:
        self.indexing_progress.emit(count, msg)

    def _on_done(self, count: int) -> None:
        dur = time.time() - self._start_time
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            for root in self._current_roots:
                c.execute(
                    "INSERT OR REPLACE INTO folder_stats VALUES(?,?)", (root, now_str)
                )
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES(?,?)", ("last_indexed", now_str)
            )
            conn.commit()
        self.indexing_done.emit(count, dur)
        self._emit_stats()
        self._schedule_auto_reindex()  # start periodic timer after first index completes

    # ── Periodic auto-reindex ────────────────────────────────────────────────

    _AUTO_REINDEX_INTERVAL_MS = 30 * 60 * 1000  # 30 minutes

    def _schedule_auto_reindex(self, folders: list[dict] | None = None) -> None:
        """Start a repeating timer that re-indexes all configured folders periodically.
        Safe to call multiple times — only one timer is ever active.
        """
        if self._auto_reindex_timer is not None:
            return  # already scheduled
        self._auto_reindex_timer = QTimer(self)
        self._auto_reindex_timer.setInterval(self._AUTO_REINDEX_INTERVAL_MS)
        self._auto_reindex_timer.timeout.connect(self._auto_reindex)
        self._auto_reindex_timer.start()

    def _auto_reindex(self) -> None:
        """Silently re-index all configured folders (skipped if a manual index is running)."""
        if self._worker and self._worker.isRunning():
            return  # don't interrupt a user-triggered index
        # Reload folder list from DB so we always use the current config
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT value FROM settings WHERE key='folders'")
                res = c.fetchone()
            roots = [f["path"] for f in json.loads(res[0])] if res else []
        except Exception:
            roots = []
        if not roots:
            return
        # os.path.isdir() blocks the main-thread timer callback on network paths.
        # Network roots are trusted as valid (the user explicitly configured them);
        # skip the isdir check for them so the main thread never stalls.
        roots = [r for r in roots if _is_network_path(r) or os.path.isdir(r)]
        if not roots:
            return
        ignore_rules = self._get_active_ignore_rules()
        self._current_roots = roots
        self._start_time = time.time()
        self._worker = IndexerWorker(roots, ignore_rules)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    # ── Stats ─────────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_stats(self) -> str:
        return self._build_stats_json()

    def _build_stats_json(self) -> str:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM files")
                count = c.fetchone()[0]
                c.execute("SELECT value FROM settings WHERE key='last_indexed'")
                res = c.fetchone()
                last = res[0] if res else "Never"
            return json.dumps(
                {"count": count, "last_indexed": last, "db_mb": round(_db_size_mb(), 1)}
            )
        except Exception:
            return json.dumps({"count": 0, "last_indexed": "Never", "db_mb": 0})

    def _emit_stats(self) -> None:
        self.stats_updated.emit(self._build_stats_json())

    # ── Clear DB ──────────────────────────────────────────────────────────────

    @pyqtSlot()
    def clear_index(self) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM folder_stats")
            conn.commit()
            conn.execute("VACUUM")
            conn.commit()
        self._emit_stats()

    # ── Async file-move / copy / delete / rename ──────────────────────────────

    @pyqtSlot(str, str, str)
    def copy_items(self, op_id: str, sources_json: str, dest_dir: str) -> None:
        """Copy files/folders into dest_dir asynchronously.

        Emits file_op_progress(op_id, done, total, current) during the operation
        and file_op_done(op_id, json) with {errors:[]} when finished.
        Uses shutil.copy2 (preserves metadata); cross-device safe.
        """
        sources: list[str] = json.loads(sources_json)
        cancel = threading.Event()
        self._cancel_flags[op_id] = cancel

        def _run() -> None:
            errors: list[str] = []
            total = len(sources)
            # Raise recursion limit for this thread so shutil.copytree doesn't
            # hit the default ~1000 frame limit on deeply-nested trees.
            old_limit = sys.getrecursionlimit()
            sys.setrecursionlimit(max(old_limit, 5000))
            try:
                for i, src in enumerate(sources):
                    if cancel.is_set():
                        errors.append("Cancelled")
                        break
                    name = os.path.basename(src.rstrip("/\\"))
                    self._op_emit_queue.put(("progress", op_id, i, total, name))
                    try:
                        dst = os.path.join(dest_dir, name)
                        os.makedirs(dest_dir, exist_ok=True)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                    except RecursionError:
                        errors.append(
                            f"{name}: directory tree is too deeply nested to copy"
                        )
                    except Exception as exc:
                        errors.append(f"{name}: {exc}")
            finally:
                sys.setrecursionlimit(old_limit)
            self._op_emit_queue.put(("progress", op_id, total, total, ""))
            self._op_emit_queue.put(("done", op_id, json.dumps({"errors": errors})))

        threading.Thread(target=_run, daemon=True).start()

    @pyqtSlot(str, str, str)
    def move_items(self, op_id: str, sources_json: str, dest_dir: str) -> None:
        """Move files/folders into dest_dir asynchronously.

        Same-drive renames are instant; cross-device falls back to copy+delete.
        """
        sources: list[str] = json.loads(sources_json)
        cancel = threading.Event()
        self._cancel_flags[op_id] = cancel

        def _run() -> None:
            errors: list[str] = []
            total = len(sources)
            for i, src in enumerate(sources):
                if cancel.is_set():
                    errors.append("Cancelled")
                    break
                name = os.path.basename(src.rstrip("/\\"))
                self._op_emit_queue.put(("progress", op_id, i, total, name))
                try:
                    dst = os.path.join(dest_dir, name)
                    os.makedirs(dest_dir, exist_ok=True)
                    shutil.move(src, dst)
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
            self._op_emit_queue.put(("progress", op_id, total, total, ""))
            self._op_emit_queue.put(("done", op_id, json.dumps({"errors": errors})))

        threading.Thread(target=_run, daemon=True).start()

    @pyqtSlot(str, str)
    def delete_items(self, op_id: str, paths_json: str) -> None:
        """Send items to trash (send2trash if available) or permanently delete."""
        paths: list[str] = json.loads(paths_json)
        cancel = threading.Event()
        self._cancel_flags[op_id] = cancel

        def _run() -> None:
            errors: list[str] = []
            total = len(paths)
            old_limit = sys.getrecursionlimit()
            sys.setrecursionlimit(max(old_limit, 5000))
            try:
                for i, path in enumerate(paths):
                    if cancel.is_set():
                        errors.append("Cancelled")
                        break
                    name = os.path.basename(path)
                    self._op_emit_queue.put(("progress", op_id, i, total, name))
                    try:
                        try:
                            import send2trash  # type: ignore

                            send2trash.send2trash(path)
                        except ImportError:
                            if os.path.isdir(path):
                                shutil.rmtree(path, ignore_errors=False)
                            else:
                                os.unlink(path)
                    except RecursionError:
                        errors.append(
                            f"{name}: directory tree is too deeply nested to delete"
                        )
                    except Exception as exc:
                        errors.append(f"{name}: {exc}")
            finally:
                sys.setrecursionlimit(old_limit)
            self._op_emit_queue.put(("progress", op_id, total, total, ""))
            self._op_emit_queue.put(("done", op_id, json.dumps({"errors": errors})))

        threading.Thread(target=_run, daemon=True).start()

    @pyqtSlot(str)
    def cancel_file_op(self, op_id: str) -> None:
        """Signal a running file operation to stop at the next item boundary."""
        flag = self._cancel_flags.get(op_id)
        if flag:
            flag.set()

    @pyqtSlot(str, str, result=str)
    def rename_item(self, path: str, new_name: str) -> str:
        """Rename a single file or folder. Returns '' on success or an error string."""
        new_name = new_name.strip()
        if not new_name:
            return "Name cannot be empty"
        # Forbid characters Windows does not allow in file names
        forbidden = set('<>:"/\\|?*')
        if any(c in forbidden for c in new_name):
            return f"Name contains invalid characters: {' '.join(c for c in new_name if c in forbidden)}"
        try:
            parent = os.path.dirname(path)
            dst = os.path.join(parent, new_name)
            if os.path.exists(dst):
                return f"'{new_name}' already exists"
            os.rename(path, dst)
            self.live_changed.emit()
            return ""
        except Exception as exc:
            return str(exc)

    # ── File operations ───────────────────────────────────────────────────────

    @pyqtSlot(str, str, result=str)
    def create_folder(self, parent_dir: str, name: str) -> str:
        """Create a new folder in parent_dir. Returns '' on success or error string."""
        if not name.strip():
            return "Name cannot be empty"
        try:
            path = os.path.join(parent_dir, name.strip())
            os.mkdir(path)
            self.live_changed.emit()
            return ""
        except Exception as e:
            return str(e)

    @pyqtSlot(str, str, result=str)
    def create_file(self, parent_dir: str, name: str) -> str:
        """Create an empty file in parent_dir. Returns '' on success or error string."""
        if not name.strip():
            return "Name cannot be empty"
        try:
            path = os.path.join(parent_dir, name.strip())
            with open(path, "a"):
                pass
            self.live_changed.emit()
            return ""
        except Exception as e:
            return str(e)

    @pyqtSlot(str)
    def open_path(self, path: str) -> None:
        if os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess

                subprocess.Popen(["open", path])
            else:
                import subprocess

                subprocess.Popen(["xdg-open", path])

    @pyqtSlot(str)
    def show_in_explorer(self, path: str) -> None:
        d = path if os.path.isdir(path) else os.path.dirname(path)
        if os.path.exists(d):
            if sys.platform == "win32":
                import subprocess

                subprocess.Popen(
                    ["explorer", "/select,", path]
                    if os.path.isfile(path)
                    else ["explorer", d]
                )
            elif sys.platform == "darwin":
                import subprocess

                subprocess.Popen(
                    ["open", "-R", path] if os.path.isfile(path) else ["open", d]
                )
            else:
                import subprocess

                subprocess.Popen(["xdg-open", d])

    @pyqtSlot(str)
    def copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text)

    @pyqtSlot(str)
    def open_in_file_ops(self, paths_json: str) -> None:
        """Open File Tools window with the given paths pre-loaded."""
        try:
            from src.file_ops.file_ops import FileToolsWindow

            paths = json.loads(paths_json)
            win = FileToolsWindow()
            win.source_paths = list(paths)
            win._refresh_list()
            win.show()
            self.__file_ops_win = win  # keep alive
        except Exception as e:
            QMessageBox.warning(None, "File Ops Error", str(e))

    @pyqtSlot(str)
    def open_in_archiver(self, paths_json: str) -> None:
        """Open File Tools window on the Archiver tab with the given paths pre-loaded."""
        try:
            from src.file_ops.file_ops import FileToolsWindow

            paths = json.loads(paths_json)
            win = FileToolsWindow()
            win.arc_sources = list(paths)
            win._arc_refresh()
            win._switch_tab("archiver")
            win.show()
            self.__archiver_win = win  # keep alive
        except Exception as e:
            QMessageBox.warning(None, "Archiver Error", str(e))

    @pyqtSlot(str, result=str)
    def get_file_icon_b64(self, path: str) -> str:
        """Return a base64-encoded PNG of the system file icon (high-res)."""
        ext = (
            os.path.splitext(path)[1].lower() if not os.path.isdir(path) else "__DIR__"
        )
        # Per-file cache key for exe/lnk/url (each has a unique icon),
        # extension-based key for everything else (same as Nexus logic).
        is_dir = os.path.isdir(path)
        cache_key = path if (is_dir or ext in (".exe", ".lnk", ".url")) else ext
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        try:
            from PyQt6.QtCore import QBuffer, QByteArray, QIODevice

            fi = QFileInfo(path) if os.path.exists(path) else None
            icon = (
                self._icon_provider.icon(fi)
                if fi
                else (
                    self._icon_provider.icon(QFileIconProvider.IconType.Folder)
                    if is_dir
                    else self._icon_provider.icon(QFileIconProvider.IconType.File)
                )
            )
            # Render at 256×256 then scale down for sharp icons (Nexus approach)
            pm: QPixmap = icon.pixmap(256, 256)
            if pm.isNull():
                print(f"[icon] pixmap null for {path}")
                return ""
            pm = pm.scaled(
                48,
                48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Serialize pixmap → PNG → base64
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            ok = pm.save(buf, "PNG")
            buf.close()
            if not ok or ba.isEmpty():
                print(f"[icon] PNG save failed for {path}, ok={ok}")
                return ""
            b64 = base64.b64encode(bytes(ba)).decode()
            self._icon_cache[cache_key] = b64
            return b64
        except Exception as exc:
            print(f"[icon] EXCEPTION for {path}: {exc}")
            return ""

    # ── Internal sync helpers (run in background thread) ─────────────────────

    def _load_image_sync(
        self, path: str, ext: str, cancel: threading.Event | None = None
    ) -> str:
        """Read an image file and return preview JSON. Called off the main thread."""
        try:
            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            size = os.path.getsize(path)

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            if size > 8 * 1024 * 1024:
                return json.dumps(
                    {"type": "unsupported", "content": "Image too large to preview."}
                )

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode()

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            mime = {".svg": "image/svg+xml", ".gif": "image/gif"}.get(ext, "image/png")
            return json.dumps(
                {"type": "image", "content": f"data:{mime};base64,{data}", "ext": ext}
            )
        except Exception as e:
            return json.dumps({"type": "error", "content": str(e)})

    def _load_text_sync(
        self, path: str, ext: str, cancel: threading.Event | None = None
    ) -> str:
        """Read a text file and return preview JSON. Called off the main thread."""
        try:
            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read(64 * 1024)

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            return json.dumps(
                {"type": "text", "content": content, "ext": ext.lstrip(".")}
            )
        except Exception as e:
            return json.dumps({"type": "error", "content": str(e)})

    def _load_html_sync(self, path: str, cancel: threading.Event | None = None) -> str:
        """Read an HTML file and return rendered preview JSON. Called off the main thread."""
        try:
            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read(512 * 1024)  # 512KB limit for HTML

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            # Light sanitization - allow JS/CSS but prevent dangerous actions
            # The iframe sandbox will provide the main security layer
            import re

            # Only remove extremely dangerous patterns, allow most HTML/JS/CSS
            # Remove form submissions to external URLs (keep sandbox contained)
            content = re.sub(
                r'<form[^>]*action\s*=\s*["\']https?://',
                '<form action="about:blank" data-blocked="',
                content,
                flags=re.IGNORECASE,
            )

            # Inject <base> tag to resolve relative URLs correctly
            # Get the directory of the HTML file as file:// URL
            file_dir = os.path.dirname(os.path.abspath(path)).replace("\\", "/")
            base_url = f"file:///{file_dir}/"

            # Insert base tag after <head> or at the start if no head tag
            if re.search(r"<head[^>]*>", content, re.IGNORECASE):
                content = re.sub(
                    r"(<head[^>]*>)",
                    rf'\1<base href="{base_url}">',
                    content,
                    count=1,
                    flags=re.IGNORECASE,
                )
            else:
                # No head tag, add it
                content = f'<base href="{base_url}">' + content

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            return json.dumps({"type": "html", "content": content, "path": path})
        except Exception as e:
            return json.dumps({"type": "error", "content": str(e)})

    def _load_pdf_sync(
        self, path: str, page: int, cancel: threading.Event | None = None
    ) -> str:
        """Render a PDF page and return preview JSON. Called off the main thread."""
        try:
            from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize
            from PyQt6.QtPdf import QPdfDocument

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            doc = QPdfDocument(None)

            # Load PDF with timeout protection for network drives
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(doc.load, path)
                try:
                    future.result(timeout=5.0)  # 5 second timeout for network drives
                except concurrent.futures.TimeoutError:
                    doc.close()
                    return json.dumps(
                        {
                            "type": "error",
                            "content": "PDF load timeout - network drive too slow",
                        }
                    )

            if cancel and cancel.is_set():
                doc.close()
                return json.dumps({"type": "unsupported", "content": ""})

            n = doc.pageCount()
            if n == 0:
                doc.close()
                return json.dumps(
                    {"type": "unsupported", "content": "Cannot open PDF."}
                )

            if cancel and cancel.is_set():
                doc.close()
                return json.dumps({"type": "unsupported", "content": ""})

            idx = max(0, min(page, n - 1))
            page_size = doc.pagePointSize(idx)
            scale = 1.5
            w = max(1, int(page_size.width() * scale))
            h = max(1, int(page_size.height() * scale))

            if cancel and cancel.is_set():
                doc.close()
                return json.dumps({"type": "unsupported", "content": ""})

            # Heavy render lock to prevent concurrent pdfium usage (prevents freezing/crashes)
            with self._preview_lock:
                if cancel and cancel.is_set():
                    doc.close()
                    return json.dumps({"type": "unsupported", "content": ""})
                img = doc.render(idx, QSize(w, h))

            doc.close()

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            from PyQt6.QtGui import QColor, QImage, QPainter

            white = QImage(img.size(), QImage.Format.Format_RGB32)
            white.fill(QColor("white"))
            p = QPainter(white)
            p.drawImage(0, 0, img)
            p.end()
            img = white

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            buf.close()
            data = base64.b64encode(bytes(ba)).decode()

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            return json.dumps(
                {
                    "type": "pdf",
                    "content": f"data:image/png;base64,{data}",
                    "page_count": n,
                    "page": idx,
                    "label": f"Page {idx + 1} of {n}",
                }
            )
        except Exception as exc:
            return json.dumps(
                {"type": "unsupported", "content": f"Cannot preview PDF: {exc}"}
            )

    def _load_pptx_xml_sync(
        self, path: str, page: int, cancel: threading.Event | None = None
    ) -> str:
        """Parse a .pptx file with stdlib XML and return slide preview JSON. Off main thread."""
        try:
            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})
            import re as _re2
            import xml.etree.ElementTree as _ET
            import zipfile as _zf

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            if not _zf.is_zipfile(path):
                raise ValueError(
                    ".ppt legacy binary format is not supported; save as .pptx first"
                )

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            _A = "http://schemas.openxmlformats.org/drawingml/2006/main"
            with _zf.ZipFile(path) as _z:
                if cancel and cancel.is_set():
                    return json.dumps({"type": "unsupported", "content": ""})

                _slides = sorted(
                    (
                        s
                        for s in _z.namelist()
                        if _re2.match(r"ppt/slides/slide\d+\.xml$", s)
                    ),
                    key=lambda s: int(_re2.search(r"\d+", s.split("/")[-1]).group()),
                )
                n = len(_slides)
                if n == 0:
                    return json.dumps(
                        {"type": "unsupported", "content": "No slides found in file."}
                    )

                if cancel and cancel.is_set():
                    return json.dumps({"type": "unsupported", "content": ""})

                idx = max(0, min(page, n - 1))
                _root = _ET.fromstring(_z.read(_slides[idx]))

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            parts: list[str] = []
            title_text = ""
            for _para in _root.iter(f"{{{_A}}}p"):
                _pPr = _para.find(f"{{{_A}}}pPr")
                _lvl = int(_pPr.get("lvl", 0)) if _pPr is not None else 0
                _line = "".join(t.text or "" for t in _para.iter(f"{{{_A}}}t")).strip()
                if not _line:
                    continue
                if not title_text and _lvl == 0:
                    title_text = _line
                _tag = "h2" if _lvl == 0 and not parts else "p"
                _style = f"margin-left:{_lvl * 16}px"
                parts.append(
                    f'<{_tag} class="sl-text sl-l{_lvl}" style="{_style}">{html.escape(_line)}</{_tag}>'
                )

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            return json.dumps(
                {
                    "type": "slide",
                    "content": "\n".join(parts)
                    or '<p class="sl-empty">Empty slide</p>',
                    "page_count": n,
                    "page": idx,
                    "label": f"Slide {idx + 1}/{n}: {title_text}"
                    if title_text
                    else f"Slide {idx + 1}/{n}",
                }
            )
        except Exception as _exc:
            return json.dumps(
                {
                    "type": "unsupported",
                    "content": f"Cannot preview this presentation: {_exc}",
                }
            )

    def _load_xlsx_sync(
        self, path: str, page: int, cancel: threading.Event | None = None
    ) -> str:
        """Parse a .xlsx/.xlsm file and return sheet preview JSON. Off main thread."""
        try:
            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})
            import xml.etree.ElementTree as _ET
            import zipfile as _zf

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            _SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            _REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

            def _col_idx(ref: str) -> int:
                col = "".join(c for c in ref if c.isalpha())
                r = 0
                for ch in col.upper():
                    r = r * 26 + (ord(ch) - 64)
                return r - 1

            with _zf.ZipFile(path) as _z:
                if cancel and cancel.is_set():
                    return json.dumps({"type": "unsupported", "content": ""})

                _names = _z.namelist()
                _wb = _ET.fromstring(_z.read("xl/workbook.xml"))

                if cancel and cancel.is_set():
                    return json.dumps({"type": "unsupported", "content": ""})

                _sels = _wb.findall(f".//{{{_SS}}}sheet")
                _sheet_names = [
                    s.get("name", f"Sheet{i + 1}") for i, s in enumerate(_sels)
                ]
                _rids = [s.get(f"{{{_REL}}}id") for s in _sels]
                n = len(_sheet_names)
                idx = max(0, min(page, n - 1))

                if cancel and cancel.is_set():
                    return json.dumps({"type": "unsupported", "content": ""})

                _rels = _ET.fromstring(_z.read("xl/_rels/workbook.xml.rels"))
                _rid_map = {r.get("Id"): r.get("Target") for r in _rels}
                _target = _rid_map.get(_rids[idx], f"worksheets/sheet{idx + 1}.xml")
                _sheet_path = "xl/" + _target.lstrip("/")
                _sst: list[str] = []

                if cancel and cancel.is_set():
                    return json.dumps({"type": "unsupported", "content": ""})

                if "xl/sharedStrings.xml" in _names:
                    for _si in _ET.fromstring(_z.read("xl/sharedStrings.xml")).findall(
                        f"{{{_SS}}}si"
                    ):
                        _sst.append(
                            "".join(e.text or "" for e in _si.iter(f"{{{_SS}}}t"))
                        )

                if cancel and cancel.is_set():
                    return json.dumps({"type": "unsupported", "content": ""})

                _ws = _ET.fromstring(_z.read(_sheet_path))
                rows: list[list] = []
                for _row_el in _ws.findall(f".//{{{_SS}}}row"):
                    if len(rows) >= 200:
                        break
                    _cs = _row_el.findall(f"{{{_SS}}}c")
                    if not _cs:
                        continue
                    _max_c = max(_col_idx(_c.get("r", "A")) for _c in _cs) + 1
                    _row: list = [None] * _max_c
                    for _c in _cs:
                        _ci = _col_idx(_c.get("r", "A"))
                        _t = _c.get("t", "")
                        _v_e = _c.find(f"{{{_SS}}}v")
                        _v = _v_e.text if _v_e is not None else None
                        if _t == "s" and _v is not None:
                            _v = _sst[int(_v)] if int(_v) < len(_sst) else ""
                        elif _t == "b":
                            _v = "TRUE" if _v == "1" else "FALSE"
                        if _ci < _max_c:
                            _row[_ci] = _v
                    rows.append(_row)

            def _table_html(rows: list) -> str:
                if not rows:
                    return '<p class="sl-empty">Empty sheet</p>'
                head = rows[0]
                h = '<div class="sheet-wrap"><table class="sheet-table"><thead><tr>'
                for cell in head:
                    h += f"<th>{'&nbsp;' if cell is None else html.escape(str(cell))}</th>"
                h += "</tr></thead><tbody>"
                for row in rows[1:]:
                    h += "<tr>"
                    for cell in row:
                        h += f"<td>{'&nbsp;' if cell is None else html.escape(str(cell))}</td>"
                    h += "</tr>"
                h += "</tbody></table></div>"
                return h

            return json.dumps(
                {
                    "type": "sheet",
                    "content": _table_html(rows),
                    "page_count": n,
                    "page": idx,
                    "label": f"{_sheet_names[idx]} ({idx + 1}/{n})",
                }
            )
        except Exception as _exc:
            return json.dumps(
                {
                    "type": "unsupported",
                    "content": f"Cannot preview this spreadsheet: {_exc}",
                }
            )

    def _load_docx_sync(self, path: str, cancel: threading.Event | None = None) -> str:
        """Parse a .docx file and return document preview JSON. Off main thread."""
        try:
            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})
            import xml.etree.ElementTree as _ET
            import zipfile as _zf

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            _W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            with _zf.ZipFile(path) as _z:
                if cancel and cancel.is_set():
                    return json.dumps({"type": "unsupported", "content": ""})
                _doc = _ET.fromstring(_z.read("word/document.xml"))

            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})

            blocks: list[str] = []

            _HEADING_MAP = [
                ("heading1", "h1"),
                ("heading2", "h2"),
                ("heading3", "h3"),
                ("heading4", "h4"),
                ("title", "h1"),
                ("subtitle", "h2"),
            ]

            _body = _doc.find(f"{{{_W}}}body") or _doc
            for _child in _body:
                _local = _child.tag.split("}")[-1] if "}" in _child.tag else _child.tag
                if _local == "p":
                    _text = "".join(
                        t.text or "" for t in _child.iter(f"{{{_W}}}t")
                    ).strip()
                    if not _text:
                        continue
                    _pPr = _child.find(f"{{{_W}}}pPr")
                    _sid = ""
                    if _pPr is not None:
                        _ps = _pPr.find(f"{{{_W}}}pStyle")
                        if _ps is not None:
                            _sid = (_ps.get(f"{{{_W}}}val") or "").lower()
                    _html_tag = "p"
                    for _key, _htag in _HEADING_MAP:
                        if _sid.startswith(_key):
                            _html_tag = _htag
                            break
                    blocks.append(f"<{_html_tag}>{html.escape(_text)}</{_html_tag}>")
                elif _local == "tbl":
                    _rows_html: list[str] = []
                    for _tr in _child.findall(f".//{{{_W}}}tr"):
                        _cells = [
                            html.escape(
                                "".join(
                                    t.text or "" for t in _tc.iter(f"{{{_W}}}t")
                                ).strip()
                            )
                            for _tc in _tr.findall(f"{{{_W}}}tc")
                        ]
                        _rows_html.append(
                            "<tr>" + "".join(f"<td>{c}</td>" for c in _cells) + "</tr>"
                        )
                    if _rows_html:
                        blocks.append(
                            '<div class="sheet-wrap"><table class="sheet-table"><tbody>'
                            + "".join(_rows_html)
                            + "</tbody></table></div>"
                        )

            if not blocks:
                blocks.append('<p class="sl-empty">Empty document</p>')

            return json.dumps(
                {
                    "type": "docx",
                    "content": "\n".join(blocks),
                    "page_count": 1,
                    "page": 0,
                    "label": "Word document",
                }
            )
        except Exception as _exc:
            return json.dumps(
                {
                    "type": "unsupported",
                    "content": f"Cannot preview this document: {_exc}",
                }
            )

    # ── Async preview dispatch ────────────────────────────────────────────────

    def _async_preview(
        self, path: str, page: int, loader_fn, loading_msg: str = "Loading…"
    ) -> str:
        """Generic async preview helper using the existing op-queue pattern.

        Cancels any in-flight render for a *different* file so switching files
        is instant — the old thread stops as soon as it checks the flag.
        """
        # NO heavy os.path.abspath or os.path.exists here — those block the main thread!
        async_key = f"{path}|{page}"

        if async_key in self._preview_cache:
            return self._preview_cache[async_key]

        # Cancel every in-flight render that isn't for this exact key.
        for key, flag in list(self._preview_cancel.items()):
            if key != async_key:
                flag.set()

        if async_key in self._preview_in_flight:
            return json.dumps(
                {"type": "loading", "key": async_key, "content": loading_msg}
            )

        self._preview_in_flight.add(async_key)
        cancel = threading.Event()
        self._preview_cancel[async_key] = cancel

        def _run(_key=async_key, _cancel=cancel, _loader=loader_fn):
            if _cancel.is_set():
                self._preview_in_flight.discard(_key)
                self._preview_cancel.pop(_key, None)
                return

            # Do existence and abspath check INSIDE the thread with timeout for network drives
            try:
                # Quick check with timeout to avoid hanging on slow network drives
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        lambda: os.path.exists(path) and not os.path.isdir(path)
                    )
                    try:
                        exists_and_file = future.result(timeout=3.0)
                        if not exists_and_file:
                            self._preview_in_flight.discard(_key)
                            self._preview_cancel.pop(_key, None)
                            self._op_emit_queue.put(
                                (
                                    "preview",
                                    _key,
                                    json.dumps({"type": "unsupported", "content": ""}),
                                )
                            )
                            return
                    except concurrent.futures.TimeoutError:
                        # Network drive too slow, abort
                        self._preview_in_flight.discard(_key)
                        self._preview_cancel.pop(_key, None)
                        self._op_emit_queue.put(
                            (
                                "preview",
                                _key,
                                json.dumps(
                                    {
                                        "type": "error",
                                        "content": "Network drive timeout - file access too slow",
                                    }
                                ),
                            )
                        )
                        return
            except Exception:
                pass

            if _cancel.is_set():
                self._preview_in_flight.discard(_key)
                self._preview_cancel.pop(_key, None)
                return

            result = _loader(_cancel)
            if _cancel.is_set():
                self._preview_in_flight.discard(_key)
                self._preview_cancel.pop(_key, None)
                return
            # Inject the key so the JS side can match the event
            try:
                d = json.loads(result)
                d["key"] = _key
                result = json.dumps(d)
            except Exception:
                pass
            self._preview_cancel.pop(_key, None)
            self._op_emit_queue.put(("preview", _key, result))

        threading.Thread(target=_run, daemon=True).start()
        return json.dumps({"type": "loading", "key": async_key, "content": loading_msg})

    @pyqtSlot(str, result=str)
    def get_preview(self, path: str) -> str:
        """Return JSON {type, content, ...} for the preview pane (first page/slide/sheet).

        Always returns immediately — heavy work runs in a background thread and
        the result is delivered via the preview_ready signal / xex:preview_ready event.
        """
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}
        HTML_EXTS = {".html", ".htm"}
        TEXT_EXTS = {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".css",
            ".xml",
            ".csv",
            ".sh",
            ".bat",
            ".ps1",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".log",
            ".env",
            ".gitignore",
        }
        PDF_EXTS = {".pdf"}
        OFFICE_EXTS = {".pptx", ".ppt", ".xlsx", ".xls", ".xlsm", ".docx"}
        VISIO_EXTS = {".vsd", ".vsdx", ".vsdm"}

        ext = os.path.splitext(path)[1].lower()

        # Paginated types go through get_preview_page which is already async
        if ext in PDF_EXTS or ext in OFFICE_EXTS or ext in VISIO_EXTS:
            return self.get_preview_page(path, 0)

        if ext in IMAGE_EXTS:
            return self._async_preview(
                path, 0, lambda c: self._load_image_sync(path, ext, c), "Loading image…"
            )

        # HTML files get rendered preview
        if ext in HTML_EXTS:
            return self._async_preview(
                path, 0, lambda c: self._load_html_sync(path, c), "Loading HTML…"
            )

        # For text files we need to peek at the size first — but we must not
        # block the main thread, so we do that check inside the worker too.
        def _text_or_unsupported(cancel=None):
            if cancel and cancel.is_set():
                return json.dumps({"type": "unsupported", "content": ""})
            try:
                size = os.path.getsize(path)
            except OSError as e:
                return json.dumps({"type": "error", "content": str(e)})
            if ext in TEXT_EXTS or size < 256 * 1024:
                return self._load_text_sync(path, ext, cancel)
            return json.dumps({"type": "unsupported", "content": ""})

        return self._async_preview(path, 0, _text_or_unsupported, "Loading…")

    @pyqtSlot(str, result=bool)
    def can_preview(self, path: str) -> bool:
        """Return True if we have a previewer for this path."""
        if not path or not os.path.isfile(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}
        HTML_EXTS = {".html", ".htm"}
        TEXT_EXTS = {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".css",
            ".xml",
            ".csv",
            ".sh",
            ".bat",
            ".ps1",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".log",
            ".env",
            ".gitignore",
        }
        PDF_EXTS = {".pdf"}
        OFFICE_EXTS = {".pptx", ".ppt", ".xlsx", ".xls", ".xlsm", ".docx"}
        VISIO_EXTS = {".vsd", ".vsdx", ".vsdm"}
        if (
            ext in IMAGE_EXTS
            or ext in HTML_EXTS
            or ext in TEXT_EXTS
            or ext in PDF_EXTS
            or ext in OFFICE_EXTS
            or ext in VISIO_EXTS
        ):
            return True
        # Check size for generic text preview
        try:
            if os.path.getsize(path) < 256 * 1024:
                return True
        except OSError:
            pass
        return False

    @pyqtSlot(str, int, result=str)
    def get_preview_page(self, path: str, page: int) -> str:
        """Return preview for a specific page/slide/sheet (0-based).

        Handles: PDF (.pdf), PowerPoint (.pptx/.ppt), Excel (.xlsx/.xls/.xlsm), Word (.docx),
        Visio (.vsd/.vsdx/.vsdm).
        """
        # Moved os.path.exists / isdir check inside _async_preview / _loader_fn
        # to prevent main-thread stalls on slow network drives.

        ext = os.path.splitext(path)[1].lower()
        try:
            # ── PDF ──────────────────────────────────────────────────────────
            if ext == ".pdf":
                return self._async_preview(
                    path,
                    page,
                    lambda c: self._load_pdf_sync(path, page, c),
                    "Rendering PDF…",
                )

            # ── PowerPoint ───────────────────────────────────────────────────
            if ext in {".pptx", ".ppt"}:
                # Preferred path on Windows: export real slide images via
                # PowerPoint COM so the user sees actual slides (layout/colors).
                # Runs in a background thread so the UI never freezes.
                if sys.platform == "win32":
                    try:
                        import importlib

                        importlib.import_module("pythoncom")
                        importlib.import_module("win32com.client")
                    except ImportError:
                        pass  # COM not available — fall through to stdlib XML parser
                    else:
                        # Use raw path as key to avoid blocking os.path.abspath on main thread
                        async_key = f"{path}|{page}|ppt_com"

                        # Return cached result instantly if available
                        if async_key in self._preview_cache:
                            return self._preview_cache[async_key]

                        # Cancel every in-flight render that isn't for this exact key
                        for key, flag in list(self._preview_cancel.items()):
                            if key != async_key:
                                flag.set()

                        # Already rendering — tell the caller to wait
                        if async_key in self._preview_in_flight:
                            return json.dumps(
                                {
                                    "type": "loading",
                                    "key": async_key,
                                    "content": "Rendering slide…",
                                }
                            )

                        # Kick off background render
                        self._preview_in_flight.add(async_key)
                        cancel = threading.Event()
                        self._preview_cancel[async_key] = cancel

                        def _run_ppt_com(
                            _path=path, _page=page, _key=async_key, _cancel=cancel
                        ) -> None:
                            import hashlib
                            import tempfile

                            import pythoncom
                            import win32com.client

                            # Check cancellation before starting COM
                            if _cancel.is_set():
                                self._preview_in_flight.discard(_key)
                                self._preview_cancel.pop(_key, None)
                                return

                            # Do abspath in worker thread to avoid blocking main thread
                            try:
                                abs_path = os.path.abspath(_path)
                            except Exception:
                                self._preview_in_flight.discard(_key)
                                self._preview_cancel.pop(_key, None)
                                return

                            pythoncom.CoInitialize()
                            app = None
                            prs = None
                            result: str
                            try:
                                # Check cancellation before expensive operations
                                if _cancel.is_set():
                                    return

                                app = win32com.client.DispatchEx(
                                    "PowerPoint.Application"
                                )

                                if _cancel.is_set():
                                    return

                                prs = app.Presentations.Open(
                                    abs_path, WithWindow=False, ReadOnly=True
                                )

                                if _cancel.is_set():
                                    return

                                n = int(prs.Slides.Count)
                                idx = max(0, min(_page, n - 1))

                                if _cancel.is_set():
                                    return

                                st = os.stat(abs_path)
                                file_key_src = (
                                    f"{abs_path}|{st.st_size}|{st.st_mtime_ns}"
                                )
                                file_key = hashlib.sha1(
                                    file_key_src.encode("utf-8", errors="replace")
                                ).hexdigest()
                                cache_dir = os.path.join(
                                    tempfile.gettempdir(),
                                    "xexplorer_ppt_cache",
                                    file_key,
                                )
                                os.makedirs(cache_dir, exist_ok=True)

                                img_path = os.path.join(
                                    cache_dir, f"slide_{idx + 1:04d}.png"
                                )

                                if _cancel.is_set():
                                    return

                                if not os.path.exists(img_path):
                                    prs.Slides(idx + 1).Export(
                                        img_path, "PNG", 1600, 900
                                    )

                                if _cancel.is_set():
                                    return

                                with open(img_path, "rb") as f:
                                    data = base64.b64encode(f.read()).decode()

                                if _cancel.is_set():
                                    return

                                title_text = ""
                                with contextlib.suppress(Exception):
                                    title_shape = prs.Slides(idx + 1).Shapes.Title
                                    if (
                                        title_shape
                                        and title_shape.TextFrame
                                        and title_shape.TextFrame.HasText
                                    ):
                                        title_text = str(
                                            title_shape.TextFrame.TextRange.Text or ""
                                        ).strip()

                                result = json.dumps(
                                    {
                                        "type": "slide_image",
                                        "key": _key,
                                        "content": f"data:image/png;base64,{data}",
                                        "page_count": n,
                                        "page": idx,
                                        "label": (
                                            f"Slide {idx + 1}/{n}: {title_text}"
                                            if title_text
                                            else f"Slide {idx + 1}/{n}"
                                        ),
                                    }
                                )
                            except Exception as exc:
                                # Don't emit error if cancelled
                                if _cancel.is_set():
                                    return
                                result = json.dumps(
                                    {
                                        "type": "error",
                                        "key": _key,
                                        "content": str(exc),
                                    }
                                )
                            finally:
                                with contextlib.suppress(Exception):
                                    if prs is not None:
                                        prs.Close()
                                with contextlib.suppress(Exception):
                                    if app is not None:
                                        app.Quit()
                                with contextlib.suppress(Exception):
                                    pythoncom.CoUninitialize()
                                self._preview_in_flight.discard(_key)
                                self._preview_cancel.pop(_key, None)

                            # Only emit if not cancelled
                            if not _cancel.is_set():
                                self._op_emit_queue.put(("preview", _key, result))

                        threading.Thread(target=_run_ppt_com, daemon=True).start()
                        return json.dumps(
                            {
                                "type": "loading",
                                "key": async_key,
                                "content": "Rendering slide…",
                            }
                        )

                return self._async_preview(
                    path,
                    page,
                    lambda c: self._load_pptx_xml_sync(path, page, c),
                    "Loading presentation…",
                )

            # ── Excel ────────────────────────────────────────────────────────
            if ext in {".xlsx", ".xls", ".xlsm"}:
                return self._async_preview(
                    path,
                    page,
                    lambda c: self._load_xlsx_sync(path, page, c),
                    "Loading spreadsheet…",
                )

            # ── Word (DOCX) ───────────────────────────────────────────────────
            if ext == ".docx":
                return self._async_preview(
                    path,
                    page,
                    lambda c: self._load_docx_sync(path, c),
                    "Loading document…",
                )

            # ── Visio ─────────────────────────────────────────────────────────
            if ext in {".vsd", ".vsdx", ".vsdm"}:
                if sys.platform != "win32":
                    return json.dumps(
                        {
                            "type": "unsupported",
                            "content": "Visio preview requires Windows + Visio installed.",
                        }
                    )
                import importlib as _ilv

                try:
                    _ilv.import_module("pythoncom")
                    _ilv.import_module("win32com.client")
                except ImportError:
                    return json.dumps(
                        {
                            "type": "unsupported",
                            "content": "Visio preview requires pywin32:\npip install pywin32",
                        }
                    )

                # Use raw path as key to avoid blocking os.path.abspath on main thread
                async_key = f"{path}|{page}|visio_com"
                if async_key in self._preview_cache:
                    return self._preview_cache[async_key]

                # Cancel every in-flight render that isn't for this exact key
                for key, flag in list(self._preview_cancel.items()):
                    if key != async_key:
                        flag.set()

                if async_key in self._preview_in_flight:
                    return json.dumps(
                        {
                            "type": "loading",
                            "key": async_key,
                            "content": "Rendering diagram\u2026",
                        }
                    )
                self._preview_in_flight.add(async_key)
                cancel = threading.Event()
                self._preview_cancel[async_key] = cancel

                def _run_visio(
                    _path=path, _page=page, _key=async_key, _cancel=cancel
                ) -> None:
                    import hashlib
                    import tempfile

                    import pythoncom
                    import win32com.client

                    # Check cancellation before starting COM
                    if _cancel.is_set():
                        self._preview_in_flight.discard(_key)
                        self._preview_cancel.pop(_key, None)
                        return

                    # Do abspath in worker thread to avoid blocking main thread
                    try:
                        abs_path = os.path.abspath(_path)
                    except Exception:
                        self._preview_in_flight.discard(_key)
                        self._preview_cancel.pop(_key, None)
                        return

                    pythoncom.CoInitialize()
                    app = None
                    doc = None
                    result: str
                    try:
                        if _cancel.is_set():
                            return

                        app = win32com.client.DispatchEx("Visio.Application")
                        app.Visible = False

                        if _cancel.is_set():
                            return

                        doc = app.Documents.OpenEx(abs_path, 64)  # 64 = visOpenRO

                        if _cancel.is_set():
                            return

                        n = int(doc.Pages.Count)
                        idx = max(0, min(_page, n - 1))
                        pg = doc.Pages.Item(idx + 1)
                        pg_name = str(pg.Name) if pg.Name else ""

                        if _cancel.is_set():
                            return

                        st = os.stat(abs_path)
                        key_src = f"{abs_path}|{st.st_size}|{st.st_mtime_ns}|p{idx}"
                        file_key = hashlib.sha1(
                            key_src.encode("utf-8", errors="replace")
                        ).hexdigest()
                        cache_dir = os.path.join(
                            tempfile.gettempdir(), "xexplorer_visio_cache", file_key
                        )
                        os.makedirs(cache_dir, exist_ok=True)
                        img_path = os.path.join(cache_dir, f"page_{idx + 1:04d}.png")

                        if _cancel.is_set():
                            return

                        if not os.path.exists(img_path):
                            pg.Export(img_path)

                        if _cancel.is_set():
                            return

                        with open(img_path, "rb") as f:
                            data = base64.b64encode(f.read()).decode()

                        result = json.dumps(
                            {
                                "type": "slide_image",
                                "key": _key,
                                "content": f"data:image/png;base64,{data}",
                                "page_count": n,
                                "page": idx,
                                "label": f"{pg_name} ({idx + 1}/{n})"
                                if pg_name
                                else f"Page {idx + 1}/{n}",
                            }
                        )
                    except Exception as exc:
                        # Don't emit error if cancelled
                        if _cancel.is_set():
                            return
                        result = json.dumps(
                            {"type": "error", "key": _key, "content": str(exc)}
                        )
                    finally:
                        with contextlib.suppress(Exception):
                            if doc is not None:
                                doc.Close()
                        with contextlib.suppress(Exception):
                            if app is not None:
                                app.Quit()
                        with contextlib.suppress(Exception):
                            pythoncom.CoUninitialize()
                        self._preview_in_flight.discard(_key)
                        self._preview_cancel.pop(_key, None)

                    # Only emit if not cancelled
                    if not _cancel.is_set():
                        self._op_emit_queue.put(("preview", _key, result))

                threading.Thread(target=_run_visio, daemon=True).start()
                return json.dumps(
                    {
                        "type": "loading",
                        "key": async_key,
                        "content": "Rendering diagram\u2026",
                    }
                )

        except Exception as e:
            return json.dumps({"type": "error", "content": str(e)})

        return json.dumps({"type": "unsupported", "content": ""})

    # ── Live watcher ──────────────────────────────────────────────────────────

    def _restart_watchers(self, folders: list[dict]) -> None:
        """Restart filesystem watchers asynchronously.

        All potentially-blocking work (obs.stop/join, os.path.exists,
        Observer.schedule, obs.start) runs in a daemon thread so the
        main/Qt thread is never stalled — especially important for UNC/
        network paths where any of those calls can block for seconds.
        """
        if not WATCHDOG_AVAILABLE:
            return

        # Grab the current observer list and clear it immediately on the main
        # thread; the background thread is then responsible for stopping them.
        old_observers = list(self._observers)
        self._observers.clear()

        def _bg(folders=folders, old_obs=old_observers) -> None:
            # 1. Stop stale observers (obs.join() can block on a hung network watcher)
            for obs in old_obs:
                with contextlib.suppress(Exception):
                    obs.stop()
                    obs.join()

            # 2. Resolve which paths actually exist.
            #    Skip os.path.exists() for network paths — it can hang on an
            #    unreachable share; network roots are trusted as valid.
            paths: list[str] = []
            for f in folders:
                p = f.get("path", "")
                if not p:
                    continue
                if _is_network_path(p) or os.path.exists(p):
                    paths.append(p)
            if not paths:
                return

            ignore_rules = self._get_active_ignore_rules()
            handler = LiveCacheUpdater(ignore_rules)
            handler.file_changed = lambda: self.live_changed.emit()  # type: ignore

            local_paths = [p for p in paths if not _is_network_path(p)]
            network_paths = [p for p in paths if _is_network_path(p)]

            new_obs: list = []

            def _make_observer(path_list, observer_cls) -> None:
                if not path_list:
                    return
                obs = observer_cls()
                scheduled = 0
                for p in path_list:
                    with contextlib.suppress(Exception):
                        obs.schedule(handler, p, recursive=True)
                        scheduled += 1
                if scheduled:
                    try:
                        obs.start()
                        new_obs.append(obs)
                    except Exception as e:
                        print(f"Failed to start observer: {e}")

            _make_observer(local_paths, Observer)
            # Poll every 30 s for network paths — frequent enough to notice
            # changes without hammering the share or spamming live_changed
            # (each live_changed triggers a full UI re-list AND re-search).
            _make_observer(network_paths, lambda: PollingObserver(timeout=30))

            # Merge new observers back (list.extend is thread-safe enough here;
            # the main thread only ever reads _observers in _restart_watchers itself)
            self._observers.extend(new_obs)

        threading.Thread(target=_bg, daemon=True, name="xexplorer-watchers").start()

    @pyqtSlot(result=bool)
    def is_watchdog_available(self) -> bool:
        return WATCHDOG_AVAILABLE
