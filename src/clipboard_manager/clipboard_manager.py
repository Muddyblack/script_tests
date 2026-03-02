"""Clipboard Manager GUI — view, search, pin and copy from persistent history.

The actual clipboard capture runs in the Nexus process 24/7 via
``src.clipboard_manager.watcher.ClipboardWatcher``.  This window is a
pure *viewer / editor* of the shared nexus_clipboard.db.
"""

import hashlib
import os
import sqlite3
import sys
from contextlib import suppress
from datetime import datetime

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QIcon,
    QKeyEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    from src.common.config import ICON_PATH
except ImportError:
    ICON_PATH = ""

from src.clipboard_manager.watcher import CLIP_DB, ensure_db, get_watcher
from src.common.theme import ThemeManager
from src.common.theme_template import TOOL_SHEET

PREVIEW_MAX = 8000  # chars shown in preview panel
UI_REFRESH_MS = 800  # how often the open window polls DB for new entries


def _fade_in(w: QWidget, ms: int = 220) -> None:
    eff = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


# ── Extra stylesheet ─────────────────────────────────────────────────────────

_EXTRA = """
QListWidget#clip_list {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 12px;
    padding: 4px;
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: transparent;
    outline: none;
}
QListWidget#clip_list::item {
    padding: 8px 10px;
    border-radius: 8px;
    border-bottom: 1px solid {{border}};
    color: {{text_primary}};
    min-height: 24px;
}
QListWidget#clip_list::item:last  { border-bottom: none; }
QListWidget#clip_list::item:selected {
    background: {{accent_subtle}};
    color: {{accent}};
}
QListWidget#clip_list::item:hover:!selected {
    background: rgba(255,255,255,0.03);
}
QLabel#count_lbl {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 9px;
    letter-spacing: 2px;
    color: {{text_secondary}};
}
QPlainTextEdit#preview {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 12px;
    padding: 10px;
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: {{accent_subtle}};
}
QPushButton#action_btn {
    background: {{bg_control}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 6px 14px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}
QPushButton#action_btn:hover {
    background: {{bg_control_hov}};
    border: 1px solid {{border_focus}};
    color: {{accent}};
}
QPushButton#action_btn:pressed { background: {{bg_control_prs}}; }
QPushButton#danger_btn {
    background: {{bg_control}};
    color: {{danger}};
    border: 1px solid {{danger_border}};
    border-radius: 8px;
    padding: 6px 14px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}
QPushButton#danger_btn:hover {
    background: {{danger_glow}};
    border: 1px solid {{danger}};
}
"""


# ── Main Window ───────────────────────────────────────────────────────────────


class ClipboardManager(QMainWindow):
    """Clipboard history viewer. Capture is handled by ClipboardWatcher in Nexus."""

    def __init__(self) -> None:
        super().__init__()
        self._mgr = ThemeManager()
        # Own DB connection for reads/edits (watcher has a separate connection)
        self._conn = sqlite3.connect(CLIP_DB, check_same_thread=False)
        ensure_db(self._conn)
        self._search_text = ""

        self.setWindowTitle("Clipboard Manager")
        if ICON_PATH and os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setMinimumSize(860, 580)
        self.resize(960, 640)
        self._build_ui()
        from src.common.theme import WindowThemeBridge

        self._theme_bridge = WindowThemeBridge(self._mgr, self, TOOL_SHEET + _EXTRA)
        self._refresh_list()

        # Light UI refresh — picks up new entries written by the always-on watcher
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(UI_REFRESH_MS)
        self._ui_timer.timeout.connect(
            lambda: self._refresh_list(preserve_selection=True)
        )
        self._ui_timer.start()

        _fade_in(self)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("CLIPBOARD MANAGER")
        title.setObjectName("title")
        sub = QLabel("persistent · searchable · pinnable")
        sub.setObjectName("sub")
        sub.setAlignment(Qt.AlignmentFlag.AlignBottom)
        hdr.addWidget(title)
        hdr.addSpacing(12)
        hdr.addWidget(sub)
        hdr.addStretch()
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("count_lbl")
        hdr.addWidget(self.count_lbl)
        outer.addLayout(hdr)

        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("search_bar")
        self.search_bar.setPlaceholderText("  Search clipboard history…")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self._on_search)
        outer.addWidget(self.search_bar)

        # Splitter: list | preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: list ──────────────────────────────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("clip_list")
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list_widget.currentItemChanged.connect(self._on_select)
        self.list_widget.itemDoubleClicked.connect(self._copy_selected)
        self.list_widget.installEventFilter(self)
        left_lay.addWidget(self.list_widget)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.copy_btn = QPushButton("⎘  COPY")
        self.copy_btn.setObjectName("action_btn")
        self.copy_btn.clicked.connect(self._copy_selected)
        self.pin_btn = QPushButton("📌  PIN")
        self.pin_btn.setObjectName("action_btn")
        self.pin_btn.clicked.connect(self._toggle_pin)
        self.del_btn = QPushButton("✕  DELETE")
        self.del_btn.setObjectName("danger_btn")
        self.del_btn.clicked.connect(self._delete_selected)
        self.clear_btn = QPushButton("🗑  CLEAR ALL")
        self.clear_btn.setObjectName("danger_btn")
        self.clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.pin_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.del_btn)
        btn_row.addWidget(self.clear_btn)
        left_lay.addLayout(btn_row)

        # ── Right: preview ───────────────────────────────────────────────────
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(8)

        prev_lbl = QLabel("PREVIEW")
        prev_lbl.setObjectName("section_label")
        right_lay.addWidget(prev_lbl)

        self.preview = QPlainTextEdit()
        self.preview.setObjectName("preview")
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select an item to preview…")
        right_lay.addWidget(self.preview)

        # Metadata label
        self.meta_lbl = QLabel("")
        self.meta_lbl.setObjectName("status")
        right_lay.addWidget(self.meta_lbl)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 380])
        outer.addWidget(splitter)

    # ── List management ───────────────────────────────────────────────────────

    # ── List management ───────────────────────────────────────────────────────

    def _refresh_list(self, preserve_selection=False):
        sel_id = None
        cur = self.list_widget.currentItem()
        if preserve_selection and cur:
            sel_id = cur.data(Qt.ItemDataRole.UserRole)

        q = self._search_text.lower()
        if q:
            rows = self._conn.execute(
                """SELECT id, content, pinned, ts FROM clips
                   WHERE lower(content) LIKE ?
                   ORDER BY pinned DESC, ts DESC LIMIT 300""",
                (f"%{q}%",),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT id, content, pinned, ts FROM clips
                   ORDER BY pinned DESC, ts DESC LIMIT 300"""
            ).fetchall()

        total = self._conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        self.count_lbl.setText(f"{total} ENTRIES")

        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        restore_row = 0
        for i, (row_id, content, pinned, ts) in enumerate(rows):
            preview = content.replace("\n", " ").replace("\t", " ").strip()
            if len(preview) > 120:
                preview = preview[:120] + "…"
            pin_mark = "📌 " if pinned else ""
            item = QListWidgetItem(f"{pin_mark}{preview}")
            item.setData(Qt.ItemDataRole.UserRole, row_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, content)
            item.setData(Qt.ItemDataRole.UserRole + 2, pinned)
            item.setData(Qt.ItemDataRole.UserRole + 3, ts)
            self.list_widget.addItem(item)
            if row_id == sel_id:
                restore_row = i

        self.list_widget.blockSignals(False)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(restore_row)

    def _on_search(self, text: str):
        self._search_text = text
        self._refresh_list()

    def _on_select(self, item: QListWidgetItem | None):
        if not item:
            self.preview.clear()
            self.meta_lbl.setText("")
            return
        content: str = item.data(Qt.ItemDataRole.UserRole + 1)
        ts: float = item.data(Qt.ItemDataRole.UserRole + 3)
        self.preview.setPlainText(content[:PREVIEW_MAX])
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d  %H:%M:%S")
        chars = len(content)
        lines = content.count("\n") + 1
        self.meta_lbl.setText(f"Saved: {dt}  •  {chars:,} chars  •  {lines} lines")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _copy_selected(self, *_) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        content: str = item.data(Qt.ItemDataRole.UserRole + 1)
        h = hashlib.sha256(content.encode()).hexdigest()
        # Tell the always-on watcher to skip this hash so it isn't re-added
        watcher = get_watcher()
        if watcher is not None:
            watcher.set_last_hash(h)
        QApplication.clipboard().setText(content)
        self._flash("✓  Copied to clipboard")

    def _toggle_pin(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        row_id = item.data(Qt.ItemDataRole.UserRole)
        pinned = item.data(Qt.ItemDataRole.UserRole + 2)
        self._conn.execute(
            "UPDATE clips SET pinned=? WHERE id=?", (0 if pinned else 1, row_id)
        )
        self._conn.commit()
        self._refresh_list(preserve_selection=True)

    def _delete_selected(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        self._conn.execute(
            "DELETE FROM clips WHERE id=?", (item.data(Qt.ItemDataRole.UserRole),)
        )
        self._conn.commit()
        self._refresh_list()

    def _clear_all(self) -> None:
        self._conn.execute("DELETE FROM clips WHERE pinned=0")
        self._conn.commit()
        self._refresh_list()
        self._flash("🗑  Cleared unpinned history")

    def _flash(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 2000)

    # ── Key handling ─────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.list_widget and isinstance(event, QKeyEvent):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._copy_selected()
                return True
            if event.key() == Qt.Key.Key_Delete:
                self._delete_selected()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._ui_timer.stop()
        with suppress(Exception):
            self._conn.close()
        super().closeEvent(event)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    # When run standalone (not inside Nexus) spin up a local watcher
    from src.clipboard_manager.watcher import ClipboardWatcher
    from src.clipboard_manager.watcher import get_watcher as _gw

    if _gw() is None:
        _watcher = ClipboardWatcher(app)  # noqa: F841 — keep alive
    win = ClipboardManager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
