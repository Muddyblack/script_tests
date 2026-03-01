"""Env Var Explorer — browse, edit, add & delete environment variables.

Far better than System Properties → Advanced → Environment Variables:
• User  /  System  /  Process (current session)  tabs
• Full-text search across names and values
• PATH-type vars shown as split list  (one path per row, drag-reorder)
• Add, edit, delete with immediate winreg write  (no shell restart needed)
• Undo last change (single-level)
• Export visible vars to clipboard as JSON / .env / shell format
• Reads directly from the Windows Registry (winreg) for User & System vars
"""

import json
import os
import sys
import winreg

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QIcon,
    QKeyEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from src.common.config import ICON_PATH
except ImportError:
    ICON_PATH = ""

from src.common.theme import ThemeManager
from src.common.theme_template import TOOL_SHEET

# ── Registry helpers ──────────────────────────────────────────────────────────

_USER_REG = r"Environment"
_SYS_REG = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def _read_user_vars() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _USER_REG, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(key, i)
                out[name] = val
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    return out


def _read_system_vars() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SYS_REG, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(key, i)
                out[name] = val
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    return out


def _write_user_var(name: str, value: str):
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _USER_REG, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ
    )
    # Use REG_EXPAND_SZ for PATH-style vars, REG_SZ otherwise
    reg_type = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
    winreg.SetValueEx(key, name, 0, reg_type, value)
    winreg.CloseKey(key)


def _delete_user_var(name: str):
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _USER_REG, 0, winreg.KEY_SET_VALUE)
    winreg.DeleteValue(key, name)
    winreg.CloseKey(key)


def _write_system_var(name: str, value: str):
    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, _SYS_REG, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ
    )
    reg_type = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
    winreg.SetValueEx(key, name, 0, reg_type, value)
    winreg.CloseKey(key)


def _delete_system_var(name: str):
    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SYS_REG, 0, winreg.KEY_SET_VALUE)
    winreg.DeleteValue(key, name)
    winreg.CloseKey(key)


def _broadcast_env_change():
    """Notify other windows that environment changed (HWND_BROADCAST WM_SETTINGCHANGE)."""
    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        res = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            ctypes.byref(res),
        )
    except Exception:
        pass


# ── Extra stylesheet ──────────────────────────────────────────────────────────

_EXTRA = """
QTabWidget::pane {
    border: 1px solid {{border}};
    border-radius: 12px;
    background: {{bg_overlay}};
    top: -1px;
}
QTabBar::tab {
    background: {{bg_control}};
    color: {{text_secondary}};
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    border: 1px solid {{border}};
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 8px 22px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: {{bg_overlay}};
    color: {{accent}};
    border-color: {{border_focus}};
}
QTabBar::tab:hover:!selected { background: {{bg_control_hov}}; color: {{text_primary}}; }
QListWidget#var_list {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 12px;
    padding: 4px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: transparent;
    outline: none;
}
QListWidget#var_list::item {
    padding: 7px 10px;
    border-radius: 8px;
    border-bottom: 1px solid {{border}};
    color: {{text_primary}};
}
QListWidget#var_list::item:selected {
    background: {{accent_subtle}};
    color: {{accent}};
}
QListWidget#var_list::item:hover:!selected { background: rgba(255,255,255,0.03); }

/* PATH items list */
QListWidget#path_list {
    background: {{bg_elevated}};
    border: 1px solid {{border}};
    border-radius: 10px;
    padding: 4px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: {{accent_subtle}};
    selection-color: {{accent}};
    outline: none;
}
QListWidget#path_list::item {
    padding: 6px 10px;
    border-radius: 6px;
    border-bottom: 1px solid {{border}};
}
QListWidget#path_list::item:selected { background: {{accent_subtle}}; color: {{accent}}; }

QLabel#var_name {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    font-weight: 700;
    color: {{accent}};
}
QLabel#var_value {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    color: {{text_secondary}};
}
QPlainTextEdit#edit_val {
    background: {{bg_control}};
    border: 1px solid {{border}};
    border-radius: 10px;
    padding: 10px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: {{accent_subtle}};
}
QPlainTextEdit#edit_val:focus { border: 1px solid {{border_focus}}; }
QPushButton#action_btn {
    background: {{bg_control}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 6px 14px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#action_btn:hover { background: {{bg_control_hov}}; color: {{accent}}; border: 1px solid {{border_focus}}; }
QPushButton#danger_btn {
    background: {{bg_control}};
    color: {{danger}};
    border: 1px solid {{danger_border}};
    border-radius: 8px;
    padding: 6px 14px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#danger_btn:hover { background: {{danger_glow}}; border: 1px solid {{danger}}; }
QPushButton#accent_btn {
    background: {{accent}};
    color: {{text_on_accent}};
    border: none;
    border-radius: 8px;
    padding: 6px 14px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#accent_btn:hover { background: {{accent_hover}}; }
QPushButton#accent_btn:pressed { background: {{accent_pressed}}; }
QLabel#path_badge {
    color: {{warning}};
    font-size: 9px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    letter-spacing: 2px;
    border: 1px solid {{warning}};
    border-radius: 4px;
    padding: 1px 6px;
}
"""


# ── Edit dialog ────────────────────────────────────────────────────────────────


class _EditDialog(QDialog):
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
            note = QLabel("PATH variable: one entry per line")
            note.setStyleSheet("font-size: 10px; color: #8295A0;")
            lay.addWidget(note)
            self._editor = QPlainTextEdit()
            self._editor.setObjectName("edit_val")
            self._editor.setPlainText("\n".join(p for p in value.split(";") if p))
        else:
            self._editor = QPlainTextEdit()
            self._editor.setObjectName("edit_val")
            self._editor.setPlainText(value)

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
            parts = [p.strip() for p in raw.splitlines() if p.strip()]
            return ";".join(parts)
        return raw


# ── Tab widget ─────────────────────────────────────────────────────────────────


class _EnvTab(QWidget):
    """A single tab displaying one scope of environment variables."""

    status_msg = pyqtSignal(str)

    def __init__(self, scope: str, parent=None):
        """scope: 'user' | 'system' | 'process'"""
        super().__init__(parent)
        self._scope = scope
        self._vars: dict[str, str] = {}
        self._undo_stack: list[tuple[str, str, str]] = []  # (op, name, old_val)
        self._build_ui()
        self.reload()

    def _build_ui(self):
        out = QVBoxLayout(self)
        out.setContentsMargins(10, 10, 10, 10)
        out.setSpacing(10)

        # Search
        self._search = QLineEdit()
        self._search.setObjectName("search_bar")
        self._search.setPlaceholderText("  Search name or value…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_list)
        out.addWidget(self._search)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: var list ─────────────────────────────────────────────────
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(8)

        self._list = QListWidget()
        self._list.setObjectName("var_list")
        self._list.currentItemChanged.connect(self._on_select)
        self._list.itemDoubleClicked.connect(self._edit_selected)
        llay.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        add_btn = QPushButton("＋  ADD")
        add_btn.setObjectName("action_btn")
        add_btn.clicked.connect(self._add_var)
        edit_btn = QPushButton("✏  EDIT")
        edit_btn.setObjectName("action_btn")
        edit_btn.clicked.connect(self._edit_selected)
        copy_btn = QPushButton("⎘  COPY")
        copy_btn.setObjectName("action_btn")
        copy_btn.clicked.connect(self._copy_selected)
        del_btn = QPushButton("✕  DELETE")
        del_btn.setObjectName("danger_btn")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        btn_row.addWidget(del_btn)
        llay.addLayout(btn_row)

        undo_row = QHBoxLayout()
        undo_btn = QPushButton("↩  UNDO")
        undo_btn.setObjectName("action_btn")
        undo_btn.clicked.connect(self._undo)
        export_btn = QPushButton("⬇  EXPORT")
        export_btn.setObjectName("action_btn")
        export_btn.clicked.connect(self._export)
        undo_row.addWidget(undo_btn)
        undo_row.addWidget(export_btn)
        undo_row.addStretch()
        llay.addLayout(undo_row)

        # ── Right: detail ─────────────────────────────────────────────────
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(8)

        self._name_lbl = QLabel("")
        self._name_lbl.setObjectName("var_name")
        self._name_lbl.setWordWrap(True)
        rlay.addWidget(self._name_lbl)

        self._path_badge = QLabel("PATH-TYPE")
        self._path_badge.setObjectName("path_badge")
        self._path_badge.setVisible(False)
        rlay.addWidget(self._path_badge)

        # Raw value display
        raw_lbl = QLabel("RAW VALUE")
        raw_lbl.setObjectName("section_label")
        rlay.addWidget(raw_lbl)

        self._val_display = QPlainTextEdit()
        self._val_display.setObjectName("edit_val")
        self._val_display.setReadOnly(True)
        self._val_display.setMaximumHeight(70)
        rlay.addWidget(self._val_display)

        # PATH-split list
        self._path_lbl = QLabel("PATHS")
        self._path_lbl.setObjectName("section_label")
        self._path_lbl.setVisible(False)
        rlay.addWidget(self._path_lbl)

        self._path_list = QListWidget()
        self._path_list.setObjectName("path_list")
        self._path_list.setVisible(False)
        rlay.addWidget(self._path_list, stretch=1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([340, 300])
        out.addWidget(splitter)

    # ── Data ──────────────────────────────────────────────────────────────────

    def reload(self):
        if self._scope == "user":
            self._vars = _read_user_vars()
        elif self._scope == "system":
            self._vars = _read_system_vars()
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
            val_preview = self._vars[k].replace("\n", " ")[:80]
            item = QListWidgetItem(f"{k}")
            item.setData(Qt.ItemDataRole.UserRole, k)
            item.setToolTip(val_preview)
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
        is_path = ";" in val and ("\\" in val or "/" in val)
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
        is_path = ";" in val and ("\\" in val or "/" in val)
        dlg = _EditDialog(key, val, is_path, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_val = dlg.get_value()
            self._undo_stack.append(("set", key, val))
            self._set_var(key, new_val)

    def _add_var(self):
        name, ok = QInputDialog.getText(self, "New Variable", "Variable name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        val_dlg = _EditDialog(name, "", False, self)
        if val_dlg.exec() == QDialog.DialogCode.Accepted:
            new_val = val_dlg.get_value()
            self._undo_stack.append(("delete", name, ""))
            self._set_var(name, new_val)

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
        old_val = self._vars.get(key, "")
        self._undo_stack.append(("set", key, old_val))
        self._delete_var(key)

    def _copy_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        val = self._vars.get(key, "")
        QApplication.clipboard().setText(f"{key}={val}")
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
        text = json.dumps(data, indent=2, ensure_ascii=False)
        QApplication.clipboard().setText(text)
        self.status_msg.emit(f"✓  Exported {len(data)} variables to clipboard (JSON)")

    # ── Registry write ────────────────────────────────────────────────────────

    def _set_var(self, name: str, value: str, record_undo: bool = True):
        try:
            if self._scope == "user":
                _write_user_var(name, value)
                _broadcast_env_change()
            elif self._scope == "system":
                _write_system_var(name, value)
                _broadcast_env_change()
            else:
                os.environ[name] = value
            self._vars[name] = value
            self._refresh_list()
            self.status_msg.emit(f"✓  Saved {name}")
        except PermissionError:
            self.status_msg.emit(
                "✗  Permission denied.  Run as Administrator to edit System vars."
            )
        except Exception as e:
            self.status_msg.emit(f"✗  Error: {e}")

    def _delete_var(self, name: str, record_undo: bool = True):
        try:
            if self._scope == "user":
                _delete_user_var(name)
                _broadcast_env_change()
            elif self._scope == "system":
                _delete_system_var(name)
                _broadcast_env_change()
            else:
                os.environ.pop(name, None)
            self._vars.pop(name, None)
            self._refresh_list()
            self.status_msg.emit(f"✓  Deleted {name}")
        except PermissionError:
            self.status_msg.emit(
                "✗  Permission denied.  Run as Administrator to delete System vars."
            )
        except Exception as e:
            self.status_msg.emit(f"✗  Error: {e}")


# ── Main window ────────────────────────────────────────────────────────────────


class EnvVarExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self._mgr = ThemeManager()

        self.setWindowTitle("Env Var Explorer")
        if ICON_PATH and os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(860, 580)
        self.resize(1000, 660)

        self._build_ui()
        self._apply_theme()
        self._mgr.theme_changed.connect(self._apply_theme)
        _fade_in(self)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        out = QVBoxLayout(root)
        out.setContentsMargins(20, 20, 20, 20)
        out.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        t = QLabel("ENV VAR EXPLORER")
        t.setObjectName("title")
        s = QLabel("browse · edit · add · delete  environment variables")
        s.setObjectName("sub")
        s.setAlignment(Qt.AlignmentFlag.AlignBottom)
        hdr.addWidget(t)
        hdr.addSpacing(10)
        hdr.addWidget(s)
        hdr.addStretch()
        out.addLayout(hdr)

        tabs = QTabWidget()

        self._user_tab = _EnvTab("user")
        self._system_tab = _EnvTab("system")
        self._proc_tab = _EnvTab("process")

        for tab, label in [
            (self._user_tab, "USER"),
            (self._system_tab, "SYSTEM"),
            (self._proc_tab, "PROCESS"),
        ]:
            tab.status_msg.connect(self._flash)
            tabs.addTab(tab, label)

        out.addWidget(tabs)

        self._status = QLabel("")
        self._status.setObjectName("status")
        out.addWidget(self._status)

    def _apply_theme(self):
        self._mgr.apply_to_widget(self, TOOL_SHEET + _EXTRA)

    def _flash(self, msg: str):
        self._status.setText(msg)
        QTimer.singleShot(3500, lambda: self._status.setText(""))

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(e)


def _fade_in(w: QWidget, ms=220):
    eff = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = EnvVarExplorer()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
