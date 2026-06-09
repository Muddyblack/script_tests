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
        limit=3000,
    ):
        """
        Search files/folders with OR-based recall + multi-tier relevance ranking.

        Filter (never misses): at least one term must appear in name OR path.
        Score per term (summed, higher = more relevant):
          +20  name starts with term
          +10  name contains term
          +1   path contains term (but name does not)
        Results are ordered by score DESC so best matches always surface first.
        """
        candidates = []  # list of (score, path, is_dir, name, size)
        for db in self.db_paths:
            if not os.path.exists(db):
                continue

            try:
                conn = self._get_connection(db)
                cursor = conn.cursor()
                where_params: list = []
                score_params: list = []

                # WHERE: any term appears anywhere (OR across all terms)
                if query_terms:
                    any_match = " OR ".join(
                        ["(name LIKE ? OR path LIKE ?)" for _ in query_terms]
                    )
                    for t in query_terms:
                        where_params.extend([f"%{t}%", f"%{t}%"])
                    term_filter = f"({any_match})"
                else:
                    term_filter = "1"

                # SCORE: per-term weighted match tiers
                score_parts = []
                for t in query_terms:
                    score_parts.append(
                        # starts-with bonus
                        "CASE WHEN name LIKE ? THEN 20 "
                        # contains-in-name bonus
                        "WHEN name LIKE ? THEN 10 "
                        # path-only bonus
                        "WHEN path LIKE ? THEN 1 "
                        "ELSE 0 END"
                    )
                    score_params.extend([f"{t}%", f"%{t}%", f"%{t}%"])
                score_expr = " + ".join(score_parts) if score_parts else "0"

                extra_conds = []
                extra_params: list = []
                if files_only:
                    extra_conds.append("is_dir = 0")
                elif folders_only:
                    extra_conds.append("is_dir = 1")

                if target_folders:
                    folder_conds = ["path LIKE ?" for _ in target_folders]
                    extra_params.extend([f"{p}%" for p in target_folders])
                    extra_conds.append(f"({' OR '.join(folder_conds)})")

                where_clause = " AND ".join(
                    [term_filter] + extra_conds
                ) if extra_conds else term_filter

                sql = (
                    f"SELECT path, is_dir, name, size, ({score_expr}) AS score "
                    f"FROM files WHERE {where_clause} "
                    f"ORDER BY score DESC LIMIT {limit}"
                )

                cursor.execute(sql, where_params + extra_params + score_params)
                for row in cursor.fetchall():
                    candidates.append((row[4], row[0], row[1], row[2], row[3]))
            except Exception:
                pass

        # Deduplicate across DBs keeping highest score, then sort
        best: dict[str, tuple] = {}
        for score, path, is_dir, name, size in candidates:
            if path not in best or score > best[path][0]:
                best[path] = (score, path, is_dir, name, size)

        return [
            (path, is_dir, name, size)
            for _, path, is_dir, name, size in sorted(
                best.values(), key=lambda x: x[0], reverse=True
            )
        ]

    def search_content(self, query_terms, target_folders=None, limit=2000):
        """
        Content Search: returns text files whose name/path matches the query terms.
        The DB does not store file contents, so this scans text-extension files
        whose name or path contains all terms.
        """
        text_ext_cond = " OR ".join(
            ["path LIKE ?" for _ in self.text_exts]
        )
        text_ext_params = [f"%{ext}" for ext in self.text_exts]

        candidates = []
        for db in self.db_paths:
            if not os.path.exists(db):
                continue

            try:
                conn = self._get_connection(db)
                cursor = conn.cursor()
                where_conds = [f"is_dir = 0", f"({text_ext_cond})"]
                params = list(text_ext_params)

                if query_terms:
                    per_term = []
                    for t in query_terms:
                        per_term.append("(name LIKE ? OR path LIKE ?)")
                        params.extend([f"%{t}%", f"%{t}%"])
                    where_conds.append("(" + " AND ".join(per_term) + ")")

                if target_folders:
                    path_conds = ["path LIKE ?" for _ in target_folders]
                    params.extend([f"{p}%" for p in target_folders])
                    where_conds.append(f"({' OR '.join(path_conds)})")

                sql = (
                    "SELECT path, is_dir FROM files WHERE "
                    + " AND ".join(where_conds)
                    + f" LIMIT {limit}"
                )

                cursor.execute(sql, params)
                candidates.extend(cursor.fetchall())
            except Exception:
                pass

        # Deduplicate
        unique_cands = {}
        for path, is_dir in candidates:
            unique_cands[path] = (path, is_dir)

        return list(unique_cands.values())
