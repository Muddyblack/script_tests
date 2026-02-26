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
        limit=500,
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

    def search_content(self, query_terms, target_folders=None, limit=100):
        """
        Fast raw inside-content search (looks for text inside files)
        """
        if not query_terms:
            return []

        all_files = []
        for db in self.db_paths:
            if not os.path.exists(db):
                continue
            try:
                with sqlite3.connect(db) as conn:
                    cursor = conn.cursor()
                    sql_content = "SELECT path FROM files WHERE is_dir = 0"
                    content_params = []

                    if target_folders:
                        path_conds = ["path LIKE ?" for _ in target_folders]
                        content_params.extend([f"{p}%" for p in target_folders])
                        sql_content += f" AND ({' OR '.join(path_conds)})"

                    cursor.execute(sql_content, content_params)
                    all_files.extend([r[0] for r in cursor.fetchall()])
            except Exception:
                pass

        matching_files = []
        # naive single term search for extreme speed iteration
        term_lower = query_terms[0].lower()

        seen = set()

        for fpath in all_files:
            if not os.path.exists(fpath):
                continue
            if fpath in seen:
                continue
            seen.add(fpath)

            ext = os.path.splitext(fpath)[1].lower()
            if ext in self.text_exts:
                try:
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if term_lower in line.lower():
                                matching_files.append(
                                    (fpath, 0, os.path.basename(fpath))
                                )
                                break
                except Exception:
                    pass

            if len(matching_files) >= limit:
                break

        return matching_files
