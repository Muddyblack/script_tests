"""SQLite Viewer — Python bridge (QWebChannel / pyBridge)."""

from __future__ import annotations

import json
import os
import sqlite3
import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

# ── Background query worker ───────────────────────────────────────────────────

class _QueryWorker(QThread):
    finished = pyqtSignal(str)  # JSON result

    def __init__(self, db_path: str, sql: str, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._sql = sql

    def run(self) -> None:
        t0 = time.perf_counter()
        try:
            with sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(self._sql)
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = [list(r) for r in cur.fetchmany(2000)]
                elapsed = round((time.perf_counter() - t0) * 1000, 2)
                self.finished.emit(json.dumps({
                    "ok": True,
                    "cols": cols,
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": len(rows) == 2000,
                    "elapsed_ms": elapsed,
                }))
        except Exception as exc:
            self.finished.emit(json.dumps({"ok": False, "error": str(exc)}))


# ── Bridge ────────────────────────────────────────────────────────────────────

class SqliteViewerBridge(QObject):
    """Exposed as ``pyBridge`` in the QWebChannel."""

    # Signals pushed to JS
    query_result = pyqtSignal(str)   # JSON
    db_opened    = pyqtSignal(str)   # JSON (tables + stats)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db_path: str = ""
        self._worker: _QueryWorker | None = None

    # ── File operations ───────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def browse_db(self) -> str:
        """Open a file picker and return the chosen path (or empty string)."""
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Open SQLite Database",
            "",
            "SQLite Databases (*.db *.sqlite *.sqlite3 *.db3);;All Files (*)",
        )
        return path or ""

    @pyqtSlot(str, result=str)
    def open_db(self, path: str) -> str:
        """Open *path* as the active database; returns JSON with metadata."""
        path = path.strip().strip('"')
        if not os.path.isfile(path):
            return json.dumps({"ok": False, "error": f"File not found: {path}"})
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
                cur = conn.cursor()

                # Tables with row counts
                cur.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
                table_names = [r[0] for r in cur.fetchall()]

                tables = []
                for tname in table_names:
                    try:
                        cur.execute(f'SELECT COUNT(*) FROM "{tname}"')
                        count = cur.fetchone()[0]
                    except Exception:
                        count = -1
                    tables.append({"name": tname, "row_count": count})

                # Views
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
                )
                views = [{"name": r[0], "row_count": -1, "is_view": True}
                         for r in cur.fetchall()]

                # DB pragmas
                cur.execute("PRAGMA page_count")
                page_count = cur.fetchone()[0]
                cur.execute("PRAGMA page_size")
                page_size_b = cur.fetchone()[0]

                file_size = os.path.getsize(path)

            self._db_path = path

            res = {
                "ok": True,
                "path": path,
                "name": os.path.basename(path),
                "file_size": file_size,
                "page_count": page_count,
                "page_size": page_size_b,
                "tables": tables,
                "views": views,
            }
            # Emit signal so JS listeners update even if they didn't initiate the call
            self.db_opened.emit(json.dumps(res))
            return json.dumps(res)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    # ── Schema ────────────────────────────────────────────────────────────────

    @pyqtSlot(str, result=str)
    def get_schema(self, table: str) -> str:
        """Return column info for *table* as JSON."""
        if not self._db_path:
            return json.dumps({"ok": False, "error": "No database open"})
        try:
            with sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True) as conn:
                cur = conn.cursor()
                cur.execute(f'PRAGMA table_info("{table}")')
                cols = [
                    {
                        "cid": r[0],
                        "name": r[1],
                        "type": r[2] or "TEXT",
                        "notnull": bool(r[3]),
                        "default": r[4],
                        "pk": r[5],
                    }
                    for r in cur.fetchall()
                ]
                # Foreign keys
                cur.execute(f'PRAGMA foreign_key_list("{table}")')
                fks = [
                    {"from": r[3], "table": r[2], "to": r[4]}
                    for r in cur.fetchall()
                ]
                # Indexes
                cur.execute(f'PRAGMA index_list("{table}")')
                idxs = [
                    {"name": r[1], "unique": bool(r[2])}
                    for r in cur.fetchall()
                ]
            return json.dumps({"ok": True, "columns": cols, "fks": fks, "indexes": idxs})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    # ── Row fetching ──────────────────────────────────────────────────────────

    @pyqtSlot(str, int, int, str, str, str, result=str)
    def get_rows(
        self,
        table: str,
        page: int,
        page_size: int,
        search: str,
        sort_col: str,
        sort_dir: str,
    ) -> str:
        """Return paginated rows from *table* as JSON."""
        if not self._db_path:
            return json.dumps({"ok": False, "error": "No database open"})
        try:
            page_size = max(10, min(page_size, 500))
            page      = max(0, page)
            offset    = page * page_size
            safe_dir  = "DESC" if sort_dir.upper() == "DESC" else "ASC"

            with sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # Column names
                cur.execute(f'PRAGMA table_info("{table}")')
                pragma_rows = cur.fetchall()
                col_names = [r[1] for r in pragma_rows]

                # Build WHERE for search
                params: list = []
                where = ""
                if search:
                    clauses = [f'CAST("{c}" AS TEXT) LIKE ?' for c in col_names]
                    where = "WHERE " + " OR ".join(clauses)
                    params = [f"%{search}%"] * len(col_names)

                # Total count
                cur.execute(f'SELECT COUNT(*) FROM "{table}" {where}', params)
                total = cur.fetchone()[0]

                # ORDER BY
                order = ""
                if sort_col and sort_col in col_names:
                    order = f'ORDER BY "{sort_col}" {safe_dir}'

                cur.execute(
                    f'SELECT * FROM "{table}" {where} {order} LIMIT ? OFFSET ?',
                    params + [page_size, offset],
                )
                rows = []
                for r in cur.fetchall():
                    rows.append([
                        None if v is None else
                        (v if isinstance(v, (int, float, bool)) else str(v))
                        for v in r
                    ])

            return json.dumps({
                "ok": True,
                "cols": col_names,
                "rows": rows,
                "total": total,
                "page": page,
                "page_size": page_size,
            })
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    # ── SQL console ───────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def run_query(self, sql: str) -> None:
        """Execute *sql* in a background thread; emits *query_result* when done."""
        if not self._db_path:
            self.query_result.emit(json.dumps({"ok": False, "error": "No database open"}))
            return

        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(300)

        self._worker = _QueryWorker(self._db_path, sql, self)
        self._worker.finished.connect(self.query_result)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
