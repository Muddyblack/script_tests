"""Ghost Typist — PyQt/Python bridge exposed to the WebEngine page."""

import json
import os

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from src.ghost_typist import db
from src.ghost_typist.watcher import get_watcher


class GhostTypistBridge(QObject):
    snippets_changed = pyqtSignal()          # JS listens to refresh UI

    def __init__(self) -> None:
        super().__init__()
        db.init_db()
        # When launched from Nexus, the Nexus process already owns the keyboard
        # hook. Skip starting a second watcher in this subprocess to prevent
        # every trigger from expanding twice.
        if os.environ.get("NEXUS_OWNS_WATCHER") != "1":
            watcher = get_watcher()
            watcher.reload_snippets()
            if db.get_setting("watcher_enabled", "1") == "1":
                watcher.start()

    # ── Snippets ──────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def load_snippets(self) -> str:
        return json.dumps(db.get_all_snippets())

    @pyqtSlot(str, str, str, str)
    def upsert_snippet(
        self, trigger: str, expansion: str, label: str, category: str
    ) -> None:
        db.upsert_snippet(trigger, expansion, label, category)
        get_watcher().reload_snippets()
        self.snippets_changed.emit()

    @pyqtSlot(str)
    def delete_snippet(self, trigger: str) -> None:
        db.delete_snippet(trigger)
        get_watcher().reload_snippets()
        self.snippets_changed.emit()

    # ── Watcher control ───────────────────────────────────────────────────────

    @pyqtSlot(result=bool)
    def get_watcher_status(self) -> bool:
        # When running inside Nexus the real watcher lives in the Nexus process —
        # read the DB (the shared source of truth) instead of the subprocess's
        # in-memory object which was never started.
        if os.environ.get("NEXUS_OWNS_WATCHER") == "1":
            return db.get_setting("watcher_enabled", "1") == "1"
        return get_watcher().is_running

    @pyqtSlot(bool)
    def set_watcher_enabled(self, enabled: bool) -> None:
        # Always write to DB — this is the cross-process signal.
        # The Nexus watcher's _db_reload_loop picks up the flag within 2 s.
        db.set_setting("watcher_enabled", "1" if enabled else "0")
        if os.environ.get("NEXUS_OWNS_WATCHER") != "1":
            # Standalone mode only: control this process's watcher directly.
            w = get_watcher()
            if enabled:
                w.start()
            else:
                w.stop()

    # ── Settings ───────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def load_settings(self) -> str:
        return json.dumps(
            {
                "watcher_enabled": db.get_setting("watcher_enabled", "1") == "1",
                "trigger_prefix": db.get_setting("trigger_prefix", ";;"),
            }
        )

    @pyqtSlot(str, str)
    def save_setting(self, key: str, value: str) -> None:
        db.set_setting(key, value)
