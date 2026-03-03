"""Ghost Typist — SQLite schema and helpers."""

import sqlite3

from src.common.config import GHOST_TYPIST_DB


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(GHOST_TYPIST_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snippets (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger   TEXT    NOT NULL UNIQUE,
                expansion TEXT    NOT NULL,
                label     TEXT    NOT NULL DEFAULT '',
                category  TEXT    NOT NULL DEFAULT 'General',
                use_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT   NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        # defaults
        conn.execute(
            "INSERT OR IGNORE INTO settings VALUES ('watcher_enabled', '1')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings VALUES ('trigger_prefix', ';;')"
        )
        conn.commit()

    # Seed some example snippets on first run
    _seed_examples()


def _seed_examples() -> None:
    with _connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM snippets").fetchone()[0]
        if count > 0:
            return
        examples = [
            (";;email", "your@email.com", "My Email", "Personal"),
            (";;addr", "123 Main Street, City, State", "My Address", "Personal"),
            (";;date", "__DATE__", "Today's Date", "Utilities"),
            (";;time", "__TIME__", "Current Time", "Utilities"),
            (";;br", "Best regards,\nYour Name", "Sign-off", "Email"),
            (";;ty", "Thank you for your time!", "Thank You", "Email"),
            (";;lgtm", "Looks good to me!", "LGTM", "Dev"),
            (";;wip", "Work in progress", "WIP", "Dev"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO snippets (trigger,expansion,label,category) VALUES (?,?,?,?)",
            examples,
        )
        conn.commit()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_all_snippets() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM snippets ORDER BY category, trigger"
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_snippet(trigger: str, expansion: str, label: str, category: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO snippets (trigger, expansion, label, category)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trigger) DO UPDATE SET
                expansion = excluded.expansion,
                label     = excluded.label,
                category  = excluded.category
            """,
            (trigger, expansion, label, category),
        )
        conn.commit()


def delete_snippet(trigger: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM snippets WHERE trigger = ?", (trigger,))
        conn.commit()


def increment_use(trigger: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE snippets SET use_count = use_count + 1 WHERE trigger = ?",
            (trigger,),
        )
        conn.commit()


# ── SETTINGS ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
