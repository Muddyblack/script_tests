"""
Chronos — database initialisation & migrations.
"""
import sqlite3

from src.common.config import CHRONOS_DB


def init_db():
    with sqlite3.connect(CHRONOS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                content TEXT NOT NULL,
                impact TEXT DEFAULT 'Medium',
                notes TEXT,
                links TEXT,
                week_number INTEGER,
                year INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                content TEXT NOT NULL,
                notes TEXT,
                links TEXT,
                status TEXT DEFAULT 'Pending',
                is_expanded INTEGER DEFAULT 1
            )
        """)

        # --- Migrations: achievements ---
        cursor = conn.execute("PRAGMA table_info(achievements)")
        cols = {c[1] for c in cursor.fetchall()}
        for col, spec in [("notes", "TEXT"), ("links", "TEXT")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE achievements ADD COLUMN {col} {spec}")

        # --- Migrations: tasks ---
        cursor = conn.execute("PRAGMA table_info(tasks)")
        cols = {c[1] for c in cursor.fetchall()}
        migrations = [
            ("parent_id", "INTEGER DEFAULT 0"),
            ("notes", "TEXT"),
            ("links", "TEXT"),
            ("is_expanded", "INTEGER DEFAULT 1"),
            ("priority", "TEXT DEFAULT 'Medium'"),
            ("due_date", "TEXT"),
            ("tags", "TEXT"),
            ("completed_at", "DATETIME"),
            ("is_achievement", "INTEGER DEFAULT 0"),
            ("position", "INTEGER DEFAULT 0"),
            ("time_spent", "INTEGER DEFAULT 0"),
        ]
        for col, spec in migrations:
            if col not in cols:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {spec}")

        # Migrate old achievements into tasks
        ach_cursor = conn.execute(
            "SELECT content, timestamp, impact, notes, links FROM achievements"
        )
        old_achs = ach_cursor.fetchall()
        if old_achs:
            for content, ts, impact, notes, links in old_achs:
                conn.execute(
                    "INSERT INTO tasks (content, timestamp, notes, links, status, "
                    "completed_at, is_achievement, priority) "
                    "VALUES (?, ?, ?, ?, 'Completed', ?, 1, ?)",
                    (content, ts, notes, links, ts, impact or "Medium"),
                )
            conn.execute("DELETE FROM achievements")

        conn.commit()
