"""Port Inspector — real-time network port viewer for Windows.

Shows all active TCP/UDP connections with:
• Local address & port   • Remote address      • State (ESTABLISHED, LISTEN…)
• PID                     • Process name        • Executable path
• One-click copy          • Kill process by port • Auto-refresh
• Search / filter by port, PID or process name
"""

import csv
import os
import subprocess
import sys
from io import StringIO

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
    from src.common.config import ICON_PATH
except ImportError:
    ICON_PATH = ""

from src.common.theme import ThemeManager, WindowThemeBridge
from src.common.theme_template import TOOL_SHEET

REFRESH_MS = 3000  # auto-refresh interval

_EXTRA = """
QTableWidget {
    background: {{bg_overlay}};
    border: 1px solid {{border}};
    border-radius: 12px;
    gridline-color: {{border}};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    color: {{text_primary}};
    selection-background-color: {{accent_subtle}};
    selection-color: {{accent}};
}
QTableWidget::item { padding: 6px 10px; border: none; }
QTableWidget::item:selected { background: {{accent_subtle}}; color: {{accent}}; }
QTableWidget::item:hover:!selected { background: rgba(255,255,255,0.03); }
QHeaderView::section {
    background: {{bg_elevated}};
    color: {{text_secondary}};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 8px 10px;
    border: none;
    border-right: 1px solid {{border}};
    border-bottom: 1px solid {{border}};
}
QHeaderView::section:hover { color: {{accent}}; }
QComboBox {
    background: {{bg_control}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 6px 10px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    min-width: 110px;
}
QComboBox:hover { border: 1px solid {{border_focus}}; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: {{bg_elevated}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    selection-background-color: {{accent_subtle}};
    selection-color: {{accent}};
}
QPushButton#action_btn {
    background: {{bg_control}};
    color: {{text_primary}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 6px 16px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#action_btn:hover {
    background: {{bg_control_hov}};
    border: 1px solid {{border_focus}};
    color: {{accent}};
}
QPushButton#danger_btn {
    background: {{bg_control}};
    color: {{danger}};
    border: 1px solid {{danger_border}};
    border-radius: 8px;
    padding: 6px 16px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#danger_btn:hover {
    background: {{danger_glow}};
    border: 1px solid {{danger}};
}
QLabel#state_LISTEN    { color: {{success}}; font-weight: 600; }
QLabel#state_ESTAB     { color: {{accent}};  font-weight: 600; }
QLabel#state_CLOSE     { color: {{danger}};  font-weight: 600; }
QCheckBox {
    color: {{text_secondary}};
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px; height: 14px;
    border-radius: 3px;
    border: 1px solid {{border_focus}};
    background: {{bg_control}};
}
QCheckBox::indicator:checked { background: {{accent}}; border: 1px solid {{accent}}; }
"""

# ── Worker thread ─────────────────────────────────────────────────────────────


class PortWorker(QThread):
    data_ready = pyqtSignal(list)

    def run(self):
        rows = _fetch_ports()
        self.data_ready.emit(rows)


def _fetch_ports() -> list[dict]:
    """Return list of port dicts using PowerShell Get-NetTCPConnection + process info."""
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            """
$tcp = Get-NetTCPConnection | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess
$procs = @{}
Get-Process | ForEach-Object { $procs[$_.Id] = @{Name=$_.Name; Path=$_.Path} }
$out = foreach ($c in $tcp) {
    $pid_ = $c.OwningProcess
    $proc = $procs[$pid_]
    [PSCustomObject]@{
        Proto='TCP'
        LocalAddr=$c.LocalAddress
        LocalPort=$c.LocalPort
        RemoteAddr=$c.RemoteAddress
        RemotePort=$c.RemotePort
        State=$c.State
        PID=$pid_
        ProcessName=if($proc){$proc.Name}else{'?'}
        Path=if($proc -and $proc.Path){$proc.Path}else{''}
    }
}
$out | ConvertTo-Csv -NoTypeInformation
""",
        ]
        raw = subprocess.check_output(cmd, timeout=8, stderr=subprocess.DEVNULL)
        text = raw.decode("utf-8", errors="ignore")
        reader = csv.DictReader(StringIO(text))
        rows = []
        for r in reader:
            rows.append(
                {
                    "proto": r.get("Proto", "TCP"),
                    "local": r.get("LocalAddr", ""),
                    "lport": r.get("LocalPort", ""),
                    "remote": r.get("RemoteAddr", ""),
                    "rport": r.get("RemotePort", ""),
                    "state": r.get("State", ""),
                    "pid": r.get("PID", ""),
                    "name": r.get("ProcessName", "?"),
                    "path": r.get("Path", ""),
                }
            )
        return rows
    except Exception as e:
        print(f"[PortInspector] fetch error: {e}")
        return []


# ── Main window ───────────────────────────────────────────────────────────────

COLS = [
    "Proto",
    "Local Port",
    "Local Addr",
    "Remote",
    "State",
    "PID",
    "Process",
    "Path",
]

_STATE_COLORS = {
    "Established": "#0EADCF",
    "Listen": "#44FFB1",
    "TimeWait": "#FFE073",
    "CloseWait": "#D95C5C",
    "SynSent": "#FFE073",
    "SynReceived": "#FFE073",
    "FinWait1": "#D95C5C",
    "FinWait2": "#D95C5C",
    "Closed": "#8295A0",
}


class PortInspector(QMainWindow):
    def __init__(self):
        super().__init__()
        self._mgr = ThemeManager()
        self._all_rows: list[dict] = []
        self._worker: PortWorker | None = None

        self.setWindowTitle("Port Inspector")
        if ICON_PATH and os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)

        self._build_ui()
        self._apply_theme()
        self._mgr.theme_changed.connect(self._apply_theme)
        self._theme_bridge = WindowThemeBridge(self._mgr, self)  # Win32 titlebar + palette

        # Initial load
        self._refresh()

        # Auto-refresh timer
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
            ["All States", "Listen", "Established", "TimeWait", "CloseWait"]
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
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.ResizeToContents
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
        self._mgr.apply_to_widget(self, TOOL_SHEET + _EXTRA)
        self._populate_table(self._all_rows)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh(self):
        self.count_lbl.setText("Loading…")
        w = PortWorker(self)
        w.data_ready.connect(self._on_data)
        w.finished.connect(w.deleteLater)
        self._worker = w
        w.start()

    def _on_data(self, rows: list[dict]):
        self._all_rows = rows
        self._apply_filter()

    def _apply_filter(self):
        q = self.search_bar.text().lower().strip()
        state_filter = self.state_combo.currentText()

        filtered = self._all_rows
        if q:
            filtered = [
                r
                for r in filtered
                if q in r["lport"]
                or q in r["name"].lower()
                or q in r["pid"]
                or q in r["local"].lower()
                or q in r["remote"].lower()
            ]
        if state_filter != "All States":
            filtered = [
                r for r in filtered if state_filter.lower() in r["state"].lower()
            ]

        self._populate_table(filtered)

    def _populate_table(self, rows: list[dict]):
        mgr = self._mgr
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))

        for i, r in enumerate(rows):
            vals = [
                r["proto"],
                r["lport"],
                r["local"],
                f"{r['remote']}:{r['rport']}"
                if r["rport"] and r["rport"] != "0"
                else r["remote"],
                r["state"],
                r["pid"],
                r["name"],
                r["path"],
            ]
            for j, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Colour the State cell
                if j == 4:
                    color = _STATE_COLORS.get(val, mgr["text_secondary"])
                    item.setForeground(QColor(color))
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
        pid_item = self.table.item(row, 5)
        name_item = self.table.item(row, 6)
        if not pid_item:
            return
        pid = pid_item.text()
        name = name_item.text() if name_item else "?"
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", pid], check=True, capture_output=True
            )
            self.status_bar_lbl.setText(f"✓  Killed {name} (PID {pid})")
        except subprocess.CalledProcessError as e:
            self.status_bar_lbl.setText(f"✗  Kill failed: {e.stderr.decode().strip()}")
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
