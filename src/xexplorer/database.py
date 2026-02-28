"""Auto-split module."""

import sqlite3

from src.common.config import X_EXPLORER_DB as DB_PATH

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False



def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY, name TEXT, parent TEXT,
        is_dir INTEGER, last_seen INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS folder_stats (
        path TEXT PRIMARY KEY, last_indexed TEXT)""")
    conn.commit()
    conn.close()


