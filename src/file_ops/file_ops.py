"""Nexus File Ops — redesigned with premium Qt UI.

Aesthetic direction: Sharp industrial glass — deep obsidian surfaces,
electric cyan accents, crisp monospace typography, fluid spring animations.
Feels like a pro tool, not a form.
"""

import os
import shutil
import sys
import threading

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

COPY_BUFFER = 8 * 1024 * 1024

# ─── Palette ──────────────────────────────────────────────────────────
C = {
    "bg": "#060910",
    "surface": "#0c1017",
    "panel": "#111722",
    "border": "#1e2a3a",
    "border2": "#243040",
    "cyan": "#00d4ff",
    "cyan_dim": "#006480",
    "cyan_glow": "rgba(0,212,255,0.08)",
    "green": "#00ff9d",
    "green_dim": "#005c3a",
    "red": "#ff4466",
    "red_dim": "#5c0018",
    "text": "#d0dcea",
    "muted": "#4a6070",
    "muted2": "#2a3a4a",
}

STYLESHEET = f"""
/* ── Root ── */
* {{ outline: none; }}
QMainWindow, QWidget#root {{
    background: {C["bg"]};
}}

/* ── Main card ── */
QFrame#card {{
    background: {C["surface"]};
    border: 1px solid {C["border"]};
    border-radius: 20px;
}}

/* ── Header labels ── */
QLabel#title {{
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 4px;
    color: {C["cyan"]};
}}
QLabel#sub {{
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 10px;
    letter-spacing: 2px;
    color: {C["muted"]};
}}
QLabel#section_label {{
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 9px;
    letter-spacing: 3px;
    color: {C["muted"]};
}}
QLabel#status {{
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    color: {C["muted"]};
    padding: 2px 0;
}}

/* ── Drop zone ── */
QLabel#drop_zone {{
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 12px;
    letter-spacing: 1px;
    color: {C["muted"]};
    background: transparent;
    border: 1px dashed {C["border2"]};
    border-radius: 14px;
    padding: 40px 20px;
}}
QLabel#drop_zone[active="true"] {{
    color: {C["cyan"]};
    border: 1px solid {C["cyan"]};
    background: {C["cyan_glow"]};
}}

/* ── File list ── */
QListWidget {{
    background: {C["panel"]};
    border: 1px solid {C["border"]};
    border-radius: 12px;
    padding: 4px;
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    color: {C["text"]};
    selection-background-color: transparent;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-radius: 8px;
    border-bottom: 1px solid {C["border"]};
    color: {C["text"]};
}}
QListWidget::item:last {{
    border-bottom: none;
}}
QListWidget::item:selected {{
    background: rgba(0,212,255,0.08);
    color: {C["cyan"]};
}}
QListWidget::item:hover:!selected {{
    background: rgba(255,255,255,0.03);
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {C["border2"]};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* ── Input ── */
QLineEdit {{
    background: {C["panel"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
    padding: 9px 14px;
    color: {C["text"]};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    selection-background-color: {C["cyan_dim"]};
}}
QLineEdit:focus {{
    border: 1px solid {C["cyan_dim"]};
    background: {C["panel"]};
}}
QLineEdit::placeholder {{
    color: {C["muted"]};
}}

/* ── Buttons — base ── */
QPushButton {{
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    border-radius: 10px;
    padding: 9px 20px;
    border: 1px solid {C["border2"]};
    background: {C["panel"]};
    color: {C["muted"]};
}}
QPushButton:hover {{
    color: {C["text"]};
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.04);
}}
QPushButton:pressed {{
    background: rgba(255,255,255,0.02);
}}
QPushButton:disabled {{
    opacity: 0.35;
}}

/* ── Buttons — accent variants ── */
QPushButton#btn_copy {{
    color: {C["green"]};
    border: 1px solid rgba(0,255,157,0.25);
    background: rgba(0,255,157,0.06);
}}
QPushButton#btn_copy:hover {{
    background: rgba(0,255,157,0.12);
    border-color: rgba(0,255,157,0.45);
}}
QPushButton#btn_copy:pressed {{
    background: rgba(0,255,157,0.07);
}}

QPushButton#btn_move {{
    color: {C["cyan"]};
    border: 1px solid rgba(0,212,255,0.25);
    background: rgba(0,212,255,0.06);
}}
QPushButton#btn_move:hover {{
    background: rgba(0,212,255,0.12);
    border-color: rgba(0,212,255,0.45);
}}

QPushButton#btn_delete {{
    color: {C["red"]};
    border: 1px solid rgba(255,68,102,0.25);
    background: rgba(255,68,102,0.06);
}}
QPushButton#btn_delete:hover {{
    background: rgba(255,68,102,0.13);
    border-color: rgba(255,68,102,0.45);
}}

/* ── Progress bar ── */
QProgressBar {{
    background: {C["panel"]};
    border: 1px solid {C["border"]};
    border-radius: 6px;
    height: 6px;
    text-align: center;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {C["cyan"]}, stop:1 {C["green"]});
    border-radius: 5px;
}}

/* ── Divider ── */
QFrame#divider {{
    background: {C["border"]};
    max-height: 1px;
    border: none;
}}
"""


# ─── Animated fade-in helper ──────────────────────────────────────────
def fade_in(widget: QWidget, duration: int = 280):
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


# ─── Custom glow progress bar ─────────────────────────────────────────
class GlowProgressBar(QProgressBar):
    """Thin progress bar with animated glow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self.setTextVisible(False)
        self._glow = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer.start(30)

    def _pulse(self):
        self._glow = (self._glow + 0.04) % (2 * 3.14159)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()

        # Track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C["panel"]))
        path = QPainterPath()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 2, 2)
        p.drawPath(path)

        if self.maximum() > 0 and self.value() > 0:
            fill_w = int(r.width() * self.value() / self.maximum())
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0, QColor("#00d4ff"))
            grad.setColorAt(1, QColor("#00ff9d"))
            p.setBrush(grad)
            chunk = QPainterPath()
            chunk.addRoundedRect(0, 0, fill_w, r.height(), 2, 2)
            p.drawPath(chunk)

            # Glow overlay
            import math

            alpha = int(30 + 20 * math.sin(self._glow))
            glow_color = QColor(0, 212, 255, alpha)
            p.setBrush(glow_color)
            p.drawPath(chunk)

        p.end()


# ─── File ops worker ──────────────────────────────────────────────────
def fast_copy(src, dst, cb=None):
    total = os.path.getsize(src)
    copied = 0
    with open(src, "rb") as s, open(dst, "wb") as d:
        while True:
            buf = s.read(COPY_BUFFER)
            if not buf:
                break
            d.write(buf)
            copied += len(buf)
            if cb:
                cb(copied, total)
    shutil.copystat(src, dst)


class FileOpsWorker(threading.Thread):
    def __init__(self, ops, on_progress=None, on_done=None):
        super().__init__(daemon=True)
        self.operations = ops
        self.on_progress = on_progress
        self.on_done = on_done
        self.cancelled = False
        self.errors = []

    def run(self):
        total = len(self.operations)
        for i, (op, src, dst) in enumerate(self.operations):
            if self.cancelled:
                break
            name = os.path.basename(src)
            try:
                if op == "copy":
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                        fast_copy(src, dst)
                elif op == "move":
                    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                    shutil.move(src, dst)
                elif op == "delete":
                    if os.path.isdir(src):
                        shutil.rmtree(src)
                    else:
                        os.remove(src)
            except Exception as e:
                self.errors.append(f"{name}: {e}")
            if self.on_progress:
                self.on_progress(i + 1, total, name)
        if self.on_done:
            self.on_done(self.errors)


# ─── Separator line ───────────────────────────────────────────────────
def make_divider():
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


# ─── Main window ──────────────────────────────────────────────────────
class FileOpsWindow(QMainWindow):
    _progress_sig = pyqtSignal(int, int, str)
    _done_sig = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NEXUS FILE OPS")
        self.setMinimumSize(680, 580)
        self.resize(720, 600)
        self.setAcceptDrops(True)
        self.source_paths: list[str] = []
        self.worker = None

        self._progress_sig.connect(self._on_progress)
        self._done_sig.connect(self._on_done)

        self.setStyleSheet(STYLESHEET)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("card")
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(16)

        # ── Header ──────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(0)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        t = QLabel("NEXUS FILE OPS")
        t.setObjectName("title")
        s = QLabel("COPY · MOVE · DELETE · FAST")
        s.setObjectName("sub")
        title_col.addWidget(t)
        title_col.addWidget(s)

        hdr.addLayout(title_col)
        hdr.addStretch()

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {C['green']}; font-size: 10px;")
        hdr.addWidget(self.status_dot)

        self.status_lbl = QLabel(" READY")
        self.status_lbl.setObjectName("status")
        hdr.addWidget(self.status_lbl)

        lay.addLayout(hdr)
        lay.addWidget(make_divider())

        # ── Queue label ─────────────────────────
        ql = QLabel("QUEUE")
        ql.setObjectName("section_label")
        lay.addWidget(ql)

        # ── Drop zone ───────────────────────────
        self.drop_zone = QLabel("DROP FILES OR FOLDERS HERE")
        self.drop_zone.setObjectName("drop_zone")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setMinimumHeight(130)
        self.drop_zone.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.drop_zone)

        # ── File list (hidden until files added) ─
        self.file_list = QListWidget()
        self.file_list.setVisible(False)
        self.file_list.setMinimumHeight(130)
        self.file_list.setMaximumHeight(200)
        lay.addWidget(self.file_list)

        # ── Add / clear buttons ─────────────────
        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(8)

        btn_add = QPushButton("+ ADD FILES")
        btn_add.clicked.connect(self._add_files)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row1.addWidget(btn_add)

        btn_add_folder = QPushButton("+ FOLDER")
        btn_add_folder.clicked.connect(self._add_folder)
        btn_add_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row1.addWidget(btn_add_folder)

        btn_row1.addStretch()

        btn_clear = QPushButton("CLEAR")
        btn_clear.clicked.connect(self._clear_files)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row1.addWidget(btn_clear)

        lay.addLayout(btn_row1)
        lay.addWidget(make_divider())

        # ── Destination ─────────────────────────
        dl = QLabel("DESTINATION")
        dl.setObjectName("section_label")
        lay.addWidget(dl)

        dst_row = QHBoxLayout()
        dst_row.setSpacing(8)
        self.dst_input = QLineEdit()
        self.dst_input.setPlaceholderText("select destination folder…")
        dst_row.addWidget(self.dst_input, stretch=1)
        btn_browse = QPushButton("BROWSE")
        btn_browse.clicked.connect(self._browse_dst)
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        dst_row.addWidget(btn_browse)
        lay.addLayout(dst_row)

        lay.addWidget(make_divider())

        # ── Operation buttons ────────────────────
        ops_row = QHBoxLayout()
        ops_row.setSpacing(8)
        ops_row.addStretch()

        self.btn_copy = QPushButton("COPY")
        self.btn_copy.setObjectName("btn_copy")
        self.btn_copy.setFixedHeight(38)
        self.btn_copy.setMinimumWidth(100)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(lambda: self._run_op("copy"))
        ops_row.addWidget(self.btn_copy)

        self.btn_move = QPushButton("MOVE")
        self.btn_move.setObjectName("btn_move")
        self.btn_move.setFixedHeight(38)
        self.btn_move.setMinimumWidth(100)
        self.btn_move.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_move.clicked.connect(lambda: self._run_op("move"))
        ops_row.addWidget(self.btn_move)

        self.btn_delete = QPushButton("DELETE")
        self.btn_delete.setObjectName("btn_delete")
        self.btn_delete.setFixedHeight(38)
        self.btn_delete.setMinimumWidth(100)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(lambda: self._run_op("delete"))
        ops_row.addWidget(self.btn_delete)

        lay.addLayout(ops_row)

        # ── Progress ────────────────────────────
        self.progress = GlowProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

    # ── Drag & Drop ───────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_zone.setProperty("active", "true")
            self.drop_zone.style().polish(self.drop_zone)

    def dragLeaveEvent(self, _):
        self.drop_zone.setProperty("active", "false")
        self.drop_zone.style().polish(self.drop_zone)

    def dropEvent(self, event: QDropEvent):
        self.drop_zone.setProperty("active", "false")
        self.drop_zone.style().polish(self.drop_zone)
        added = False
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and p not in self.source_paths:
                self.source_paths.append(p)
                added = True
        if added:
            self._refresh_list()

    # ── File management ───────────────────────────────────────────────
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Files")
        for p in paths:
            if p not in self.source_paths:
                self.source_paths.append(p)
        if paths:
            self._refresh_list()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder and folder not in self.source_paths:
            self.source_paths.append(folder)
            self._refresh_list()

    def _browse_dst(self):
        folder = QFileDialog.getExistingDirectory(self, "Destination")
        if folder:
            self.dst_input.setText(folder)

    def _clear_files(self):
        self.source_paths.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.file_list.clear()
        for p in self.source_paths:
            is_dir = os.path.isdir(p)
            icon = "▸ DIR" if is_dir else "  FILE"
            size_str = ""
            if os.path.isfile(p):
                sz = os.path.getsize(p)
                if sz > 1_000_000_000:
                    size_str = f"  {sz / 1_000_000_000:.1f} GB"
                elif sz > 1_000_000:
                    size_str = f"  {sz / 1_000_000:.1f} MB"
                elif sz > 1_000:
                    size_str = f"  {sz / 1_000:.1f} KB"
                else:
                    size_str = f"  {sz} B"

            item = QListWidgetItem(f"{icon}   {os.path.basename(p)}{size_str}")
            item.setForeground(QColor(C["cyan"] if is_dir else C["text"]))
            self.file_list.addItem(item)

        has = len(self.source_paths) > 0
        self.file_list.setVisible(has)
        self.drop_zone.setVisible(not has)

        count = len(self.source_paths)
        self._set_status(
            f"{count} ITEM{'S' if count != 1 else ''} QUEUED" if has else "READY",
            C["muted"],
        )

    # ── Operations ────────────────────────────────────────────────────
    def _run_op(self, op_type: str):
        if not self.source_paths:
            self._set_status("NO FILES SELECTED", C["red"])
            return
        dst = self.dst_input.text().strip()
        if op_type != "delete" and not dst:
            self._set_status("SELECT A DESTINATION FIRST", C["red"])
            return

        ops = []
        for src in self.source_paths:
            if op_type == "delete":
                ops.append(("delete", src, ""))
            else:
                ops.append((op_type, src, os.path.join(dst, os.path.basename(src))))

        self.progress.setMaximum(len(ops))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        for b in [self.btn_copy, self.btn_move, self.btn_delete]:
            b.setEnabled(False)

        self._set_status("WORKING…", C["cyan"])
        self.status_dot.setStyleSheet(f"color: {C['cyan']}; font-size: 10px;")

        self.worker = FileOpsWorker(
            ops,
            on_progress=lambda d, t, n: self._progress_sig.emit(d, t, n),
            on_done=lambda errs: self._done_sig.emit(errs),
        )
        self.worker.start()

    def _on_progress(self, done, total, name):
        self.progress.setValue(done)
        self._set_status(f"{name}  [{done}/{total}]", C["cyan"])

    def _on_done(self, errors):
        for b in [self.btn_copy, self.btn_move, self.btn_delete]:
            b.setEnabled(True)

        if errors:
            self._set_status(f"{len(errors)} ERROR(S) — CHECK PERMISSIONS", C["red"])
            self.status_dot.setStyleSheet(f"color: {C['red']}; font-size: 10px;")
        else:
            self._set_status("ALL DONE  ✓", C["green"])
            self.status_dot.setStyleSheet(f"color: {C['green']}; font-size: 10px;")
            self.source_paths.clear()
            self._refresh_list()

        QTimer.singleShot(2800, lambda: self.progress.setVisible(False))
        QTimer.singleShot(
            4000,
            lambda: (
                self._set_status("READY", C["muted"]),
                self.status_dot.setStyleSheet(f"color: {C['green']}; font-size: 10px;"),
            ),
        )

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(f" {text}")
        self.status_lbl.setStyleSheet(
            f"font-family: 'JetBrains Mono','Consolas','Courier New'; "
            f"font-size: 11px; letter-spacing: 1px; color: {color};"
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Try to set a nice base palette so Fusion doesn't bleed through
    from PyQt6.QtGui import QPalette

    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(C["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(C["panel"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(C["surface"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(C["panel"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(C["cyan_dim"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(C["cyan"]))
    app.setPalette(pal)

    win = FileOpsWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
