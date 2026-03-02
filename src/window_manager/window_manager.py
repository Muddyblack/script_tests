"""Window Manager — snap, tile, save & restore window layouts.

Features:
• List all visible windows with title, process name, PID, position & size
• One-click: focus, minimise, maximise, restore, close
• Snap presets: Left Half · Right Half · Top Half · Bottom Half ·
                Top-Left · Top-Right · Bottom-Left · Bottom-Right ·
                Full Screen · Centre (80%)
• Custom tile grid: N columns × M rows  (drag-to-assign coming soon)
• Save current layout as a named preset (JSON in APPDATA)
• Restore any saved preset with one click
• Live window list auto-refreshes every 2 s
• Search / filter windows by title or process
"""

import ctypes
import ctypes.wintypes
import json
import os
import sys

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QIcon,
    QKeyEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    from src.common.config import APPDATA, ICON_PATH
except ImportError:
    APPDATA = os.getenv("APPDATA", ".")
    ICON_PATH = ""

from src.common.theme import ThemeManager, WindowThemeBridge
from src.common.theme_template import TOOL_SHEET

LAYOUTS_FILE = os.path.join(APPDATA, "nexus_window_layouts.json")
REFRESH_MS = 2000

# ── Win32 helpers ─────────────────────────────────────────────────────────────

user32 = ctypes.windll.user32
RECT = ctypes.wintypes.RECT

SW_RESTORE = 9
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_SHOW = 5
GW_OWNER = 4
WS_VISIBLE = 0x10000000


def _get_pid(hwnd: int) -> int:
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _get_proc_name(pid: int) -> str:
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Name",
            ],
            timeout=2,
            stderr=subprocess.DEVNULL,
        )
        return out.decode("utf-8", errors="ignore").strip() or "?"
    except Exception:
        return "?"


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _list_windows() -> list[dict]:
    hwnds: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _cb(hwnd, _lp):
        if (
            user32.IsWindowVisible(hwnd)
            and user32.GetWindowTextLengthW(hwnd) > 0
            and user32.GetWindow(hwnd, GW_OWNER) == 0
        ):
            hwnds.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    results = []
    for hwnd in hwnds:
        title = _get_window_title(hwnd)
        if not title:
            continue
        pid = _get_pid(hwnd)
        left, top, right, bottom = _get_window_rect(hwnd)
        results.append(
            {
                "hwnd": hwnd,
                "title": title,
                "pid": pid,
                "name": "",  # filled lazily
                "x": left,
                "y": top,
                "w": right - left,
                "h": bottom - top,
            }
        )
    return results


def _move_window(hwnd: int, x: int, y: int, w: int, h: int):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.MoveWindow(hwnd, x, y, w, h, True)


def _screen_size() -> tuple[int, int]:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


# ── Snap presets ─────────────────────────────────────────────────────────────


def _snap_rect(preset: str) -> tuple[int, int, int, int]:
    sw, sh = _screen_size()
    hw, hh = sw // 2, sh // 2
    presets = {
        "Left Half": (0, 0, hw, sh),
        "Right Half": (hw, 0, hw, sh),
        "Top Half": (0, 0, sw, hh),
        "Bottom Half": (0, hh, sw, hh),
        "Top-Left": (0, 0, hw, hh),
        "Top-Right": (hw, 0, hw, hh),
        "Bottom-Left": (0, hh, hw, hh),
        "Bottom-Right": (hw, hh, hw, hh),
        "Full Screen": (0, 0, sw, sh),
        "Centre 80%": (int(sw * 0.1), int(sh * 0.1), int(sw * 0.8), int(sh * 0.8)),
        "Centre 60%": (int(sw * 0.2), int(sh * 0.2), int(sw * 0.6), int(sh * 0.6)),
    }
    return presets.get(preset, (0, 0, sw, sh))


SNAP_PRESETS = [
    "Left Half",
    "Right Half",
    "Top Half",
    "Bottom Half",
    "Top-Left",
    "Top-Right",
    "Bottom-Left",
    "Bottom-Right",
    "Full Screen",
    "Centre 80%",
    "Centre 60%",
]

# ── Worker ────────────────────────────────────────────────────────────────────


class WindowListWorker(QThread):
    done = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = True

    def run(self):
        wins = _list_windows()
        seen_pids: dict[int, str] = {}
        for w in wins:
            pid = w["pid"]
            if pid not in seen_pids:
                seen_pids[pid] = _get_proc_name(pid)
            w["name"] = seen_pids[pid]
        if self._active:
            self.done.emit(wins)


# ── Extra stylesheet ──────────────────────────────────────────────────────────

_EXTRA = """
QListWidget#win_list {
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
QListWidget#win_list::item {
    padding: 8px 10px;
    border-radius: 8px;
    border-bottom: 1px solid {{border}};
    color: {{text_primary}};
}
QListWidget#win_list::item:selected {
    background: {{accent_subtle}};
    color: {{accent}};
}
QListWidget#win_list::item:hover:!selected {
    background: rgba(255,255,255,0.03);
}
QPushButton#snap_btn {
    background: {{bg_control}};
    color: {{text_secondary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 7px 10px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#snap_btn:hover {
    background: {{bg_control_hov}};
    color: {{accent}};
    border: 1px solid {{border_focus}};
}
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
QPushButton#action_btn:hover {
    background: {{bg_control_hov}};
    color: {{accent}};
    border: 1px solid {{border_focus}};
}
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
QPushButton#danger_btn:hover {
    background: {{danger_glow}};
    border: 1px solid {{danger}};
}
QFrame#section_box {
    background: {{bg_elevated}};
    border: 1px solid {{border}};
    border-radius: 12px;
}
QLabel#layout_item {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    color: {{text_primary}};
    padding: 4px 0;
}
QLabel#meta_lbl {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    color: {{text_secondary}};
}
"""


class WindowManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self._mgr = ThemeManager()
        self._windows: list[dict] = []
        self._worker: WindowListWorker | None = None
        self._worker_running: bool = False
        self._layouts: dict[str, list[dict]] = self._load_layouts()

        self.setWindowTitle("Window Manager")
        if ICON_PATH and os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(1000, 620)
        self.resize(1160, 700)

        self._build_ui()
        self._apply_theme()
        self._mgr.theme_changed.connect(self._apply_theme)
        self._theme_bridge = WindowThemeBridge(self._mgr, self)  # Win32 titlebar + palette

        self._refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.setInterval(REFRESH_MS)
        self._timer.start()

        _fade_in(self)

    # ── Layouts persistence ───────────────────────────────────────────────────

    def _load_layouts(self) -> dict:
        try:
            if os.path.exists(LAYOUTS_FILE):
                with open(LAYOUTS_FILE) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_layouts(self):
        try:
            with open(LAYOUTS_FILE, "w") as f:
                json.dump(self._layouts, f, indent=2)
        except Exception:
            pass

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        out = QVBoxLayout(root)
        out.setContentsMargins(20, 20, 20, 20)
        out.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        t = QLabel("WINDOW MANAGER")
        t.setObjectName("title")
        s = QLabel("snap · tile · save & restore layouts")
        s.setObjectName("sub")
        s.setAlignment(Qt.AlignmentFlag.AlignBottom)
        hdr.addWidget(t)
        hdr.addSpacing(10)
        hdr.addWidget(s)
        hdr.addStretch()
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("status")
        hdr.addWidget(self.count_lbl)
        out.addLayout(hdr)

        # Search
        self.search = QLineEdit()
        self.search.setObjectName("search_bar")
        self.search.setPlaceholderText("  Filter windows by title or process…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_windows)
        out.addWidget(self.search)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: window list ─────────────────────────────────────────────────
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(8)

        self.win_list = QListWidget()
        self.win_list.setObjectName("win_list")
        self.win_list.currentItemChanged.connect(self._on_select)
        llay.addWidget(self.win_list)

        # Window actions row
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        for label, slot in [
            ("FOCUS", self._focus_win),
            ("MIN", self._min_win),
            ("MAX", self._max_win),
            ("RESTORE", self._restore_win),
        ]:
            b = QPushButton(label)
            b.setObjectName("action_btn")
            b.clicked.connect(slot)
            act_row.addWidget(b)
        close_btn = QPushButton("CLOSE")
        close_btn.setObjectName("danger_btn")
        close_btn.clicked.connect(self._close_win)
        act_row.addWidget(close_btn)
        llay.addLayout(act_row)

        self.meta_lbl = QLabel("")
        self.meta_lbl.setObjectName("meta_lbl")
        llay.addWidget(self.meta_lbl)

        # ── Right: snap + layouts ─────────────────────────────────────────────
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(12)

        # Snap presets box
        snap_box = QFrame()
        snap_box.setObjectName("section_box")
        snap_inner = QVBoxLayout(snap_box)
        snap_inner.setContentsMargins(12, 10, 12, 12)
        snap_inner.setSpacing(8)
        snap_title = QLabel("SNAP PRESETS")
        snap_title.setObjectName("section_label")
        snap_inner.addWidget(snap_title)

        grid_rows = [SNAP_PRESETS[i : i + 3] for i in range(0, len(SNAP_PRESETS), 3)]
        for row_items in grid_rows:
            row_w = QHBoxLayout()
            row_w.setSpacing(6)
            for preset in row_items:
                btn = QPushButton(preset)
                btn.setObjectName("snap_btn")
                btn.clicked.connect(lambda _=False, p=preset: self._snap(p))
                row_w.addWidget(btn)
            snap_inner.addLayout(row_w)

        rlay.addWidget(snap_box)

        # Layout save/restore
        layout_box = QFrame()
        layout_box.setObjectName("section_box")
        layout_inner = QVBoxLayout(layout_box)
        layout_inner.setContentsMargins(12, 10, 12, 12)
        layout_inner.setSpacing(8)
        lt = QLabel("SAVED LAYOUTS")
        lt.setObjectName("section_label")
        layout_inner.addWidget(lt)

        self.layout_list = QListWidget()
        self.layout_list.setObjectName("win_list")
        self.layout_list.setMaximumHeight(160)
        layout_inner.addWidget(self.layout_list)

        layout_btns = QHBoxLayout()
        layout_btns.setSpacing(8)
        save_btn = QPushButton("💾  SAVE LAYOUT")
        save_btn.setObjectName("action_btn")
        save_btn.clicked.connect(self._save_layout)
        restore_btn = QPushButton("↩  RESTORE")
        restore_btn.setObjectName("action_btn")
        restore_btn.clicked.connect(self._restore_layout)
        del_layout_btn = QPushButton("✕  DELETE")
        del_layout_btn.setObjectName("danger_btn")
        del_layout_btn.clicked.connect(self._delete_layout)
        layout_btns.addWidget(save_btn)
        layout_btns.addWidget(restore_btn)
        layout_btns.addWidget(del_layout_btn)
        layout_inner.addLayout(layout_btns)

        rlay.addWidget(layout_box)
        rlay.addStretch()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([520, 420])
        out.addWidget(splitter)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("status")
        out.addWidget(self.status_lbl)

        self._refresh_layout_list()

    def _apply_theme(self):
        self._mgr.apply_to_widget(self, TOOL_SHEET + _EXTRA)

    # ── Window list ───────────────────────────────────────────────────────────

    def _refresh(self):
        # Guard: don't start a new worker if one is still running
        if self._worker_running:
            return
        self._worker_running = True
        w = WindowListWorker()
        w.done.connect(self._on_windows)
        w.finished.connect(self._on_worker_finished)
        self._worker = w
        w.start()

    def _on_worker_finished(self):
        self._worker_running = False
        self._worker = None

    def _on_windows(self, wins: list[dict]):
        self._windows = wins
        self._filter_windows()

    def _filter_windows(self):
        q = self.search.text().lower()
        filtered = [
            w
            for w in self._windows
            if not q or q in w["title"].lower() or q in w["name"].lower()
        ]
        sel_hwnd = None
        cur = self.win_list.currentItem()
        if cur:
            sel_hwnd = cur.data(Qt.ItemDataRole.UserRole)

        self.win_list.blockSignals(True)
        self.win_list.clear()
        sel_row = 0
        for i, w in enumerate(filtered):
            label = f"{w['title'][:55]}"
            if w["name"] and w["name"] != "?":
                label += f"  ·  {w['name']}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, w["hwnd"])
            item.setData(Qt.ItemDataRole.UserRole + 1, w)
            self.win_list.addItem(item)
            if w["hwnd"] == sel_hwnd:
                sel_row = i
        self.win_list.blockSignals(False)
        if self.win_list.count() > 0:
            self.win_list.setCurrentRow(sel_row)
        self.count_lbl.setText(f"{len(filtered)} / {len(self._windows)} windows")

    def _on_select(self, item: QListWidgetItem | None):
        if not item:
            self.meta_lbl.setText("")
            return
        w: dict = item.data(Qt.ItemDataRole.UserRole + 1)
        self.meta_lbl.setText(
            f"PID: {w['pid']}  ·  pos: ({w['x']},{w['y']})  ·  size: {w['w']}×{w['h']}"
        )

    def _selected_hwnd(self) -> int | None:
        item = self.win_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ── Window actions ────────────────────────────────────────────────────────

    def _focus_win(self):
        hwnd = self._selected_hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)

    def _min_win(self):
        hwnd = self._selected_hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, SW_MINIMIZE)

    def _max_win(self):
        hwnd = self._selected_hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, SW_MAXIMIZE)

    def _restore_win(self):
        hwnd = self._selected_hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, SW_RESTORE)

    def _close_win(self):
        hwnd = self._selected_hwnd()
        if hwnd:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE

    # ── Snap ──────────────────────────────────────────────────────────────────

    def _snap(self, preset: str):
        hwnd = self._selected_hwnd()
        if not hwnd:
            self._flash("Select a window first")
            return
        x, y, w, h = _snap_rect(preset)
        _move_window(hwnd, x, y, w, h)
        self._flash(f"✓  Snapped to {preset}")
        self._refresh()

    # ── Layouts ───────────────────────────────────────────────────────────────

    def _save_layout(self):
        name, ok = QInputDialog.getText(self, "Save Layout", "Layout name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        # Snapshot current state of all visible windows
        snapshot = []
        for w in self._windows:
            snapshot.append(
                {
                    "title": w["title"],
                    "name": w["name"],
                    "x": w["x"],
                    "y": w["y"],
                    "width": w["w"],
                    "height": w["h"],
                }
            )
        self._layouts[name] = snapshot
        self._save_layouts()
        self._refresh_layout_list()
        self._flash(f"✓  Layout '{name}' saved  ({len(snapshot)} windows)")

    def _restore_layout(self):
        item = self.layout_list.currentItem()
        if not item:
            return
        name = item.text()
        entries = self._layouts.get(name, [])
        matched = 0
        for entry in entries:
            # Try to find window by title
            for w in self._windows:
                if w["title"] == entry["title"]:
                    _move_window(
                        w["hwnd"],
                        entry["x"],
                        entry["y"],
                        entry["width"],
                        entry["height"],
                    )
                    matched += 1
                    break
        self._flash(f"✓  Restored '{name}'  ({matched}/{len(entries)} windows matched)")
        self._refresh()

    def _delete_layout(self):
        item = self.layout_list.currentItem()
        if not item:
            return
        name = item.text()
        self._layouts.pop(name, None)
        self._save_layouts()
        self._refresh_layout_list()
        self._flash(f"✕  Layout '{name}' deleted")

    def _refresh_layout_list(self):
        self.layout_list.clear()
        for name in self._layouts:
            self.layout_list.addItem(name)

    # ── Status ────────────────────────────────────────────────────────────────

    def _flash(self, msg: str):
        self.status_lbl.setText(msg)
        QTimer.singleShot(3000, lambda: self.status_lbl.setText(""))

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(e)

    def closeEvent(self, event):
        self._timer.stop()
        if self._worker is not None:
            self._worker._active = False
            self._worker.quit()
        super().closeEvent(event)


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
    win = WindowManager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
