"""Auto-split module."""

import contextlib
import sqlite3

from src.common.config import X_EXPLORER_DB as DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY, name TEXT, parent TEXT,
        is_dir INTEGER, last_seen INTEGER, size INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS folder_stats (
        path TEXT PRIMARY KEY, last_indexed TEXT)""")
    # Migrate existing DBs that lack the size column
    with contextlib.suppress(Exception):
        c.execute("ALTER TABLE files ADD COLUMN size INTEGER DEFAULT 0")
    # Add index for faster search if it doesn't exist
    c.execute("CREATE INDEX IF NOT EXISTS idx_files_name ON files(name)")
    conn.commit()
    conn.close()
