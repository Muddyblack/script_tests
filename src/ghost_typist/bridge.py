"""Ghost Typist — PyQt/Python bridge exposed to the WebEngine page."""

import json

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from src.ghost_typist import db
from src.ghost_typist.watcher import get_watcher


class GhostTypistBridge(QObject):
    snippets_changed = pyqtSignal()          # JS listens to refresh UI

    def __init__(self) -> None:
        super().__init__()
        db.init_db()
        watcher = get_watcher()
        watcher.reload_snippets()
        # Auto-start if DB says enabled
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
        return get_watcher().is_running

    @pyqtSlot(bool)
    def set_watcher_enabled(self, enabled: bool) -> None:
        w = get_watcher()
        if enabled:
            w.start()
        else:
            w.stop()
        db.set_setting("watcher_enabled", "1" if enabled else "0")

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
