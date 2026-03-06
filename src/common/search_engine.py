import os
import sqlite3
import threading


class SearchEngine:
    def __init__(self, db_paths):
        """
        db_paths: list of sqlite database paths to search from (e.g. x_explorer_cache.db)
        """
        self.db_paths = db_paths if isinstance(db_paths, list) else [db_paths]
        self.text_exts = {
            ".py",
            ".txt",
            ".md",
            ".json",
            ".js",
            ".html",
            ".css",
            ".csv",
            ".ini",
            ".cfg",
            ".log",
            ".xml",
        }
        # Keep persistent connections for faster queries
        self._connections = {}
        self._cache_warmed = False
        self._conn_lock = threading.Lock()

    def _get_connection(self, db_path):
        """Get or create a persistent connection with optimizations."""
        with self._conn_lock:
            if db_path not in self._connections:
                conn = sqlite3.connect(db_path, check_same_thread=False)
                # Optimize for read performance
                conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
                conn.execute("PRAGMA temp_store = MEMORY")
                conn.execute("PRAGMA mmap_size = 268435456")  # 256MB memory-mapped I/O
                conn.execute("PRAGMA journal_mode = WAL")  # Better concurrency
                self._connections[db_path] = conn
            return self._connections[db_path]

    def _warm_cache(self):
        """Warm up the database cache for instant first search."""
        if self._cache_warmed:
            return
        self._cache_warmed = True

        for db in self.db_paths:
            if not os.path.exists(db):
                continue
            try:
                conn = self._get_connection(db)
                # Touch the table data to load it into memory
                # A full scan using string operations ensures we read the data pages, not just the index
                conn.execute(
                    "SELECT SUM(LENGTH(path) + LENGTH(name) + size) FROM files"
                ).fetchone()
                # Dummy query to compile the LIKE statement cache
                conn.execute(
                    "SELECT path, is_dir, name, size FROM files WHERE name LIKE '%__warmup__%' LIMIT 1"
                ).fetchall()
            except Exception:
                pass

    def warm_cache(self, blocking=False):
        """Public method to warm cache - can be called from Nexus startup."""
        if blocking:
            self._warm_cache()
        else:
            threading.Thread(target=self._warm_cache, daemon=True).start()

    def search_files(
        self,
        query_terms,
        target_folders=None,
        files_only=False,
        folders_only=False,
        limit=2000,
    ):
        """
        Standard Search across all databases for files/folders matching ALL query_terms (AND logic)
        """
        candidates = []
        for db in self.db_paths:
            if not os.path.exists(db):
                continue

            try:
                conn = self._get_connection(db)
                cursor = conn.cursor()
                f_conds, f_params = [], []

                if query_terms:
                    f_conds.append(
                        "(" + " AND ".join(["name LIKE ?" for _ in query_terms]) + ")"
                    )
                    f_params.extend([f"%{t}%" for t in query_terms])

                if files_only:
                    f_conds.append("is_dir = 0")
                elif folders_only:
                    f_conds.append("is_dir = 1")

                if target_folders:
                    path_conds = ["path LIKE ?" for _ in target_folders]
                    f_params.extend([f"{p}%" for p in target_folders])
                    f_conds.append(f"({' OR '.join(path_conds)})")

                sql = (
                    "SELECT path, is_dir, name, size FROM files WHERE "
                    + (" AND ".join(f_conds) if f_conds else "1")
                    + f" LIMIT {limit}"
                )

                cursor.execute(sql, f_params)
                candidates.extend(cursor.fetchall())
            except Exception:
                pass

        # Deduplicate candidates across databases (using path as unique key)
        unique_cands = {}
        for path, is_dir, name, size in candidates:
            unique_cands[path] = (path, is_dir, name, size)

        return list(unique_cands.values())

    def search_content(self, query_terms, target_folders=None, limit=2000):
        """
        Content Search: searches inside text files for query_terms (AND logic)
        """
        candidates = []
        for db in self.db_paths:
            if not os.path.exists(db):
                continue

            try:
                conn = self._get_connection(db)
                cursor = conn.cursor()
                c_conds, c_params = [], []

                if query_terms:
                    c_conds.append(
                        "("
                        + " AND ".join(["content LIKE ?" for _ in query_terms])
                        + ")"
                    )
                    c_params.extend([f"%{t}%" for t in query_terms])

                if target_folders:
                    path_conds = ["path LIKE ?" for _ in target_folders]
                    c_params.extend([f"{p}%" for p in target_folders])
                    c_conds.append(f"({' OR '.join(path_conds)})")

                sql = (
                    "SELECT path, is_dir FROM files WHERE "
                    + (" AND ".join(c_conds) if c_conds else "1")
                    + f" LIMIT {limit}"
                )

                cursor.execute(sql, c_params)
                candidates.extend(cursor.fetchall())
            except Exception:
                pass

        # Deduplicate
        unique_cands = {}
        for path, is_dir in candidates:
            unique_cands[path] = (path, is_dir)

        return list(unique_cands.values())
