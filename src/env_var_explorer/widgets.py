"""Reusable widgets for the Env Var Explorer: edit dialog and scope tab."""

import json
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.env_var_explorer.registry import (
    broadcast_env_change,
    delete_system_var,
    delete_user_var,
    read_system_vars,
    read_user_vars,
    write_system_var,
    write_user_var,
)


def _is_path_var(value: str) -> bool:
    return ";" in value and ("\\" in value or "/" in value)


# ── Edit dialog ────────────────────────────────────────────────────────────────


class EditDialog(QDialog):
    """Dialog for editing a single environment variable value."""

    def __init__(self, name: str, value: str, is_path: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit: {name}")
        self.setMinimumSize(560, 320)
        self._is_path = is_path

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lbl = QLabel(f"<b>{name}</b>")
        lbl.setStyleSheet(
            "font-size: 13px; font-family: 'JetBrains Mono','Consolas','Courier New';"
        )
        lay.addWidget(lbl)

        if is_path:
            note = QLabel("PATH variable — one entry per line")
            note.setStyleSheet("font-size: 10px; color: #8295A0;")
            lay.addWidget(note)

        self._editor = QPlainTextEdit()
        self._editor.setObjectName("edit_val")
        self._editor.setPlainText(
            "\n".join(p for p in value.split(";") if p) if is_path else value
        )
        lay.addWidget(self._editor)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_value(self) -> str:
        raw = self._editor.toPlainText()
        if self._is_path:
            return ";".join(p.strip() for p in raw.splitlines() if p.strip())
        return raw


# ── Scope tab ─────────────────────────────────────────────────────────────────


class EnvTab(QWidget):
    """A single tab displaying environment variables for one scope."""

    status_msg = pyqtSignal(str)

    def __init__(self, scope: str, parent=None):
        """scope: 'user' | 'system' | 'process'"""
        super().__init__(parent)
        self._scope = scope
        self._vars: dict[str, str] = {}
        self._undo_stack: list[tuple[str, str, str]] = []  # (op, name, old_val)
        self._build_ui()
        self.reload()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self._search = QLineEdit()
        self._search.setObjectName("search_bar")
        self._search.setPlaceholderText("  Search name or value…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_list)
        root.addWidget(self._search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([340, 300])
        root.addWidget(splitter)

    def _build_left(self) -> QWidget:
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._list = QListWidget()
        self._list.setObjectName("var_list")
        self._list.currentItemChanged.connect(self._on_select)
        self._list.itemDoubleClicked.connect(self._edit_selected)
        lay.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        for label, obj_name, slot in [
            ("＋  ADD", "action_btn", self._add_var),
            ("✏  EDIT", "action_btn", self._edit_selected),
            ("⎘  COPY", "action_btn", self._copy_selected),
        ]:
            btn = QPushButton(label)
            btn.setObjectName(obj_name)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        del_btn = QPushButton("✕  DELETE")
        del_btn.setObjectName("danger_btn")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(del_btn)
        lay.addLayout(btn_row)

        util_row = QHBoxLayout()
        for label, slot in [("↩  UNDO", self._undo), ("⬇  EXPORT", self._export)]:
            btn = QPushButton(label)
            btn.setObjectName("action_btn")
            btn.clicked.connect(slot)
            util_row.addWidget(btn)
        util_row.addStretch()
        lay.addLayout(util_row)

        return left

    def _build_right(self) -> QWidget:
        right = QWidget()
        lay = QVBoxLayout(right)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._name_lbl = QLabel("")
        self._name_lbl.setObjectName("var_name")
        self._name_lbl.setWordWrap(True)
        lay.addWidget(self._name_lbl)

        self._path_badge = QLabel("PATH-TYPE")
        self._path_badge.setObjectName("path_badge")
        self._path_badge.setVisible(False)
        lay.addWidget(self._path_badge)

        raw_lbl = QLabel("RAW VALUE")
        raw_lbl.setObjectName("section_label")
        lay.addWidget(raw_lbl)

        self._val_display = QPlainTextEdit()
        self._val_display.setObjectName("edit_val")
        self._val_display.setReadOnly(True)
        self._val_display.setMaximumHeight(70)
        lay.addWidget(self._val_display)

        self._path_lbl = QLabel("PATHS")
        self._path_lbl.setObjectName("section_label")
        self._path_lbl.setVisible(False)
        lay.addWidget(self._path_lbl)

        self._path_list = QListWidget()
        self._path_list.setObjectName("path_list")
        self._path_list.setVisible(False)
        lay.addWidget(self._path_list, stretch=1)

        return right

    # ── Data ──────────────────────────────────────────────────────────────────

    def reload(self):
        if self._scope == "user":
            self._vars = read_user_vars()
        elif self._scope == "system":
            self._vars = read_system_vars()
        else:
            self._vars = dict(os.environ)
        self._refresh_list()

    def _refresh_list(self):
        q = self._search.text().lower()
        keys = sorted(self._vars.keys(), key=str.lower)
        if q:
            keys = [k for k in keys if q in k.lower() or q in self._vars[k].lower()]

        sel_name = None
        cur = self._list.currentItem()
        if cur:
            sel_name = cur.data(Qt.ItemDataRole.UserRole)

        self._list.blockSignals(True)
        self._list.clear()
        sel_row = 0
        for i, k in enumerate(keys):
            item = QListWidgetItem(k)
            item.setData(Qt.ItemDataRole.UserRole, k)
            item.setToolTip(self._vars[k].replace("\n", " ")[:80])
            self._list.addItem(item)
            if k == sel_name:
                sel_row = i
        self._list.blockSignals(False)
        if self._list.count() > 0:
            self._list.setCurrentRow(sel_row)

    def _on_select(self, item: QListWidgetItem | None):
        if not item:
            self._name_lbl.setText("")
            self._val_display.clear()
            self._path_list.clear()
            self._path_list.setVisible(False)
            self._path_lbl.setVisible(False)
            self._path_badge.setVisible(False)
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        val = self._vars.get(key, "")
        self._name_lbl.setText(key)
        self._val_display.setPlainText(val)
        is_path = _is_path_var(val)
        self._path_badge.setVisible(is_path)
        self._path_lbl.setVisible(is_path)
        self._path_list.setVisible(is_path)
        if is_path:
            self._path_list.clear()
            for part in val.split(";"):
                if part.strip():
                    self._path_list.addItem(part.strip())

    # ── Actions ───────────────────────────────────────────────────────────────

    def _edit_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        val = self._vars.get(key, "")
        dlg = EditDialog(key, val, _is_path_var(val), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._undo_stack.append(("set", key, val))
            self._set_var(key, dlg.get_value())

    def _add_var(self):
        name, ok = QInputDialog.getText(self, "New Variable", "Variable name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        dlg = EditDialog(name, "", False, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._undo_stack.append(("delete", name, ""))
            self._set_var(name, dlg.get_value())

    def _delete_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self,
            "Delete Variable",
            f"Delete <b>{key}</b>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._undo_stack.append(("set", key, self._vars.get(key, "")))
        self._delete_var(key)

    def _copy_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        QApplication.clipboard().setText(f"{key}={self._vars.get(key, '')}")
        self.status_msg.emit(f"✓  Copied {key}")

    def _undo(self):
        if not self._undo_stack:
            self.status_msg.emit("Nothing to undo")
            return
        op, key, val = self._undo_stack.pop()
        if op == "set":
            self._set_var(key, val, record_undo=False)
        elif op == "delete":
            self._delete_var(key, record_undo=False)
        self.status_msg.emit(f"↩  Undone: {key}")

    def _export(self):
        data = {k: self._vars[k] for k in sorted(self._vars)}
        QApplication.clipboard().setText(json.dumps(data, indent=2, ensure_ascii=False))
        self.status_msg.emit(f"✓  Exported {len(data)} variables to clipboard (JSON)")

    # ── Registry write ────────────────────────────────────────────────────────

    def _set_var(self, name: str, value: str, record_undo: bool = True):
        try:
            if self._scope == "user":
                write_user_var(name, value)
                broadcast_env_change()
            elif self._scope == "system":
                write_system_var(name, value)
                broadcast_env_change()
            else:
                os.environ[name] = value
            self._vars[name] = value
            self._refresh_list()
            self.status_msg.emit(f"✓  Saved {name}")
        except PermissionError:
            self.status_msg.emit("✗  Permission denied — run as Administrator to edit System vars.")
        except Exception as e:
            self.status_msg.emit(f"✗  Error: {e}")

    def _delete_var(self, name: str, record_undo: bool = True):
        try:
            if self._scope == "user":
                delete_user_var(name)
                broadcast_env_change()
            elif self._scope == "system":
                delete_system_var(name)
                broadcast_env_change()
            else:
                os.environ.pop(name, None)
            self._vars.pop(name, None)
            self._refresh_list()
            self.status_msg.emit(f"✓  Deleted {name}")
        except PermissionError:
            self.status_msg.emit("✗  Permission denied — run as Administrator to delete System vars.")
        except Exception as e:
            self.status_msg.emit(f"✗  Error: {e}")
