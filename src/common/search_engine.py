import os
import sqlite3


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
                with sqlite3.connect(db) as conn:
                    cursor = conn.cursor()
                    f_conds, f_params = [], []

                    if query_terms:
                        f_conds.append(
                            "("
                            + " AND ".join(["name LIKE ?" for _ in query_terms])
                            + ")"
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
                        "SELECT path, is_dir, name FROM files WHERE "
                        + (" AND ".join(f_conds) if f_conds else "1")
                        + f" LIMIT {limit}"
                    )

                    cursor.execute(sql, f_params)
                    candidates.extend(cursor.fetchall())
            except Exception:
                pass

        # Deduplicate candidates across databases (using path as unique key)
        unique_cands = {}
        for path, is_dir, name in candidates:
            unique_cands[path] = (path, is_dir, name)

        return list(unique_cands.values())
