"""Port Inspector — cross-platform real-time network port viewer.

Works on Windows, macOS, and Linux via psutil.

Shows all active TCP/UDP connections with:
• Local address & port   • Remote address      • State (ESTABLISHED, LISTEN…)
• PID                     • Process name        • Executable path
• One-click copy          • Kill process by port • Auto-refresh
• Search / filter by port, PID or process name
"""

import os
import signal
import sys
from concurrent.futures import ThreadPoolExecutor

import psutil
from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QKeyEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from src.common.config import PORT_INSPECTOR_ICON_PATH as ICON_PATH
except ImportError:
    ICON_PATH = ""

try:
    from src.common.theme import ThemeManager, WindowThemeBridge
    from src.common.theme_template import TOOL_SHEET
    _HAS_THEME = True
except ImportError:
    _HAS_THEME = False
    ThemeManager = None
    WindowThemeBridge = None
    TOOL_SHEET = ""

REFRESH_MS = 3000  # auto-refresh interval

# ── Data fetching ─────────────────────────────────────────────────────────────

# Shared executor for parallel process-info lookups — avoids spawning threads per row
_EXECUTOR = ThreadPoolExecutor(max_workers=6)


def _resolve_proc(pid: int) -> tuple[str, str]:
    """Return (name, exe_path) for a PID. Runs in thread pool."""
    try:
        p = psutil.Process(pid)
        with p.oneshot():           # batch all syscalls into one round-trip
            name = p.name()
            try:
                path = p.exe()
            except (psutil.AccessDenied, psutil.ZombieProcess):
                path = ""
        return name, path
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return "?", ""


def _fetch_ports() -> list[dict]:
    """Return list of port dicts using psutil — works on Windows, macOS, Linux."""
    try:
        conns = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        # macOS / Linux without root — fall back; fewer entries but won't crash
        try:
            conns = psutil.net_connections(kind="inet4")
        except Exception:
            return []

    # Resolve all unique PIDs in parallel so we don't block per-row
    pids = {c.pid for c in conns if c.pid}
    futures = {pid: _EXECUTOR.submit(_resolve_proc, pid) for pid in pids}
    pid_info: dict[int, tuple[str, str]] = {}
    for pid, fut in futures.items():
        try:
            pid_info[pid] = fut.result(timeout=3)
        except Exception:
            pid_info[pid] = ("?", "")

    rows = []
    for conn in conns:
        la = conn.laddr
        ra = conn.raddr
        name, path = pid_info.get(conn.pid, ("?", "")) if conn.pid else ("?", "")
        state = conn.status if conn.status and conn.status != psutil.CONN_NONE else "NONE"
        rows.append({
            "proto":  "TCP" if conn.type == psutil.socket.SOCK_STREAM else "UDP",
            "local":  la.ip        if la else "",
            "lport":  str(la.port) if la else "",
            "remote": ra.ip        if ra else "",
            "rport":  str(ra.port) if ra else "",
            "state":  state,
            "pid":    str(conn.pid) if conn.pid else "",
            "name":   name,
            "path":   path,
        })
    return rows


# ── Worker thread ─────────────────────────────────────────────────────────────

class PortWorker(QThread):
    data_ready = pyqtSignal(list)

    def run(self):
        rows = _fetch_ports()
        self.data_ready.emit(rows)


# ── Main window ───────────────────────────────────────────────────────────────

COLS = ["Proto", "Local Port", "Local Addr", "Remote", "State", "PID", "Process", "Path"]

_STATE_COLORS = {
    "ESTABLISHED":  "#0EADCF",
    "LISTEN":       "#44FFB1",
    "TIME_WAIT":    "#FFE073",
    "CLOSE_WAIT":   "#D95C5C",
    "SYN_SENT":     "#FFE073",
    "SYN_RECEIVED": "#FFE073",
    "FIN_WAIT1":    "#D95C5C",
    "FIN_WAIT2":    "#D95C5C",
    "CLOSED":       "#8295A0",
    "NONE":         "#8295A0",
}


class PortInspector(QMainWindow):
    def __init__(self):
        super().__init__()
        self._all_rows: list[dict] = []
        self._worker: PortWorker | None = None
        self._busy: bool = False

        if _HAS_THEME:
            self._mgr = ThemeManager()
        else:
            self._mgr = None

        self.setWindowTitle("Port Inspector")
        if ICON_PATH and os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)

        self._build_ui()
        self._apply_theme()

        if _HAS_THEME:
            self._mgr.theme_changed.connect(self._apply_theme)
            self._theme_bridge = WindowThemeBridge(self._mgr, self)

        self._refresh()

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

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
        t = QLabel("PORT INSPECTOR")
        t.setObjectName("title")
        s = QLabel("real-time network connections")
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

        # Toolbar
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("search_bar")
        self.search_bar.setPlaceholderText("  Filter  port / process / PID …")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self._apply_filter)
        bar.addWidget(self.search_bar, stretch=1)

        self.state_combo = QComboBox()
        self.state_combo.addItems(
            ["All States", "LISTEN", "ESTABLISHED", "TIME_WAIT", "CLOSE_WAIT"]
        )
        self.state_combo.currentTextChanged.connect(self._apply_filter)
        bar.addWidget(self.state_combo)

        refresh_btn = QPushButton("⟳  REFRESH")
        refresh_btn.setObjectName("action_btn")
        refresh_btn.clicked.connect(self._refresh)
        bar.addWidget(refresh_btn)

        copy_btn = QPushButton("⎘  COPY ROW")
        copy_btn.setObjectName("action_btn")
        copy_btn.clicked.connect(self._copy_selected)
        bar.addWidget(copy_btn)

        kill_btn = QPushButton("✕  KILL PROCESS")
        kill_btn.setObjectName("danger_btn")
        kill_btn.clicked.connect(self._kill_selected)
        bar.addWidget(kill_btn)

        out.addLayout(bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for col in (0, 1, 4, 5, 6):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(False)
        out.addWidget(self.table)

        self.status_bar_lbl = QLabel("")
        self.status_bar_lbl.setObjectName("status")
        out.addWidget(self.status_bar_lbl)

    def _apply_theme(self):
        if _HAS_THEME and self._mgr:
            self._mgr.apply_to_widget(self, TOOL_SHEET)
        else:
            Exception("ThemeManager not available; skipping theme application")
        self._populate_table(self._all_rows)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh(self):
        # Guard: don't stack workers if previous fetch is still running.
        # Check _busy flag instead of calling isRunning() on a potentially
        # deleted C++ object (which raises RuntimeError after deleteLater).
        if self._busy:
            return
        self._busy = True
        self.count_lbl.setText("Loading…")
        w = PortWorker(self)
        w.data_ready.connect(self._on_data)
        w.finished.connect(self._on_worker_done)
        self._worker = w
        w.start()

    def _on_worker_done(self):
        self._busy = False
        # Disconnect and schedule deletion safely; clear our ref first so
        # _refresh never touches the (soon-to-be-deleted) C++ object again.
        w = self._worker
        self._worker = None
        if w is not None:
            w.deleteLater()

    def _on_data(self, rows: list[dict]):
        self._all_rows = rows
        self._apply_filter()

    def _apply_filter(self):
        q = self.search_bar.text().lower().strip()
        state_filter = self.state_combo.currentText()

        filtered = self._all_rows
        if q:
            filtered = [
                r for r in filtered
                if q in r["lport"]
                or q in r["name"].lower()
                or q in r["pid"]
                or q in r["local"].lower()
                or q in r["remote"].lower()
            ]
        if state_filter != "All States":
            filtered = [r for r in filtered if state_filter in r["state"]]

        self._populate_table(filtered)

    def _populate_table(self, rows: list[dict]):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))

        for i, r in enumerate(rows):
            remote = (
                f"{r['remote']}:{r['rport']}"
                if r["rport"] and r["rport"] != "0"
                else r["remote"]
            )
            vals = [
                r["proto"], r["lport"], r["local"], remote,
                r["state"], r["pid"], r["name"], r["path"],
            ]
            for j, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if j == 4:
                    item.setForeground(QColor(_STATE_COLORS.get(val, "#8295A0")))
                self.table.setItem(i, j, item)

        self.table.setSortingEnabled(True)
        self.count_lbl.setText(f"{len(rows)} / {len(self._all_rows)} connections")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _copy_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        parts = [
            self.table.item(row, c).text()
            for c in range(len(COLS))
            if self.table.item(row, c)
        ]
        QApplication.clipboard().setText("\t".join(parts))
        self.status_bar_lbl.setText("✓  Row copied to clipboard")
        QTimer.singleShot(2000, lambda: self.status_bar_lbl.setText(""))

    def _kill_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pid_item  = self.table.item(row, 5)
        name_item = self.table.item(row, 6)
        if not pid_item or not pid_item.text():
            return
        pid_str = pid_item.text()
        name    = name_item.text() if name_item else "?"
        try:
            pid = int(pid_str)
            if sys.platform == "win32":
                import subprocess
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid_str],
                    check=True, capture_output=True
                )
            else:
                os.kill(pid, signal.SIGTERM)
            self.status_bar_lbl.setText(f"✓  Killed {name} (PID {pid})")
        except Exception as e:
            self.status_bar_lbl.setText(f"✗  Kill failed: {e}")
        QTimer.singleShot(3000, lambda: self.status_bar_lbl.setText(""))
        self._refresh()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)


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
    win = PortInspector()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
