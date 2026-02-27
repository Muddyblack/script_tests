"""Nexus File Ops — fast copy / move / delete with progress UI.

Uses large-buffer shutil operations to bypass slow Windows shell copy.
Supports drag-drop, multi-file operations, and progress tracking.
"""

import os
import shutil
import sys
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.config import ASSETS_DIR

ICON_PATH = os.path.join(ASSETS_DIR, "nexus_icon.png")

# Large buffer for fast copy (8 MB)
COPY_BUFFER = 8 * 1024 * 1024


def fast_copy(src: str, dst: str, progress_callback=None) -> None:
    """Copy a file using a large buffer for speed."""
    total = os.path.getsize(src)
    copied = 0

    if os.path.isdir(src):
        # For directories, walk and copy
        for root, _dirs, files in os.walk(src):
            rel_root = os.path.relpath(root, src)
            dst_root = os.path.join(dst, rel_root) if rel_root != "." else dst
            os.makedirs(dst_root, exist_ok=True)
            for f in files:
                s = os.path.join(root, f)
                d = os.path.join(dst_root, f)
                _copy_single(s, d)
                copied += os.path.getsize(s)
                if progress_callback:
                    progress_callback(copied, total)
    else:
        _copy_single(src, dst, progress_callback)


def _copy_single(src: str, dst: str, progress_callback=None) -> None:
    """Copy a single file with large buffer."""
    total = os.path.getsize(src)
    copied = 0
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            buf = fsrc.read(COPY_BUFFER)
            if not buf:
                break
            fdst.write(buf)
            copied += len(buf)
            if progress_callback:
                progress_callback(copied, total)
    # Preserve metadata
    shutil.copystat(src, dst)


class FileOpsWorker(threading.Thread):
    """Runs file operations in a background thread."""

    def __init__(self, operations: list, on_progress=None, on_done=None):
        super().__init__(daemon=True)
        self.operations = operations  # List of (op_type, src, dst)
        self.on_progress = on_progress
        self.on_done = on_done
        self.current_file = ""
        self.total_files = len(operations)
        self.completed = 0
        self.errors = []
        self.cancelled = False

    def run(self):
        for op_type, src, dst in self.operations:
            if self.cancelled:
                break
            self.current_file = os.path.basename(src)
            try:
                if op_type == "copy":
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        fast_copy(src, dst)
                elif op_type == "move":
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)
                elif op_type == "delete":
                    if os.path.isdir(src):
                        shutil.rmtree(src)
                    else:
                        os.remove(src)
            except Exception as e:
                self.errors.append(f"{src}: {e}")
            self.completed += 1
            if self.on_progress:
                self.on_progress(self.completed, self.total_files, self.current_file)

        if self.on_done:
            self.on_done(self.errors)


# ──────────────────────────────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────────────────────────────
DARK_STYLE = """
QWidget { background: #0f172a; color: #e2e8f0; font-family: 'Outfit', 'Inter', 'Segoe UI'; }
QFrame#main_frame {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(30,41,59,245), stop:1 rgba(15,23,42,250));
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 18px;
}
QLabel#title { font-size: 18px; font-weight: 700; color: #60a5fa; }
QLabel#subtitle { font-size: 11px; color: #64748b; }
QLabel#status { font-size: 12px; color: #94a3b8; }
QLabel#drop_label {
    font-size: 14px; color: #64748b;
    border: 2px dashed rgba(255,255,255,0.1);
    border-radius: 14px; padding: 30px;
}
QListWidget {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 12px; padding: 6px;
    font-size: 12px;
}
QListWidget::item { padding: 6px 10px; border-radius: 8px; }
QListWidget::item:selected { background: rgba(96,165,250,0.15); }
QPushButton {
    background: rgba(96,165,250,0.12);
    border: 1px solid rgba(96,165,250,0.25);
    border-radius: 10px; padding: 8px 18px;
    color: #60a5fa; font-weight: 600; font-size: 12px;
}
QPushButton:hover { background: rgba(96,165,250,0.22); }
QPushButton#danger { background: rgba(239,68,68,0.12); border-color: rgba(239,68,68,0.25); color: #ef4444; }
QPushButton#danger:hover { background: rgba(239,68,68,0.22); }
QPushButton#success { background: rgba(34,197,94,0.12); border-color: rgba(34,197,94,0.25); color: #22c55e; }
QPushButton#success:hover { background: rgba(34,197,94,0.22); }
QLineEdit {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px; padding: 8px 14px;
    color: #e2e8f0; font-size: 13px;
}
QProgressBar {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px; height: 18px;
    text-align: center; color: #e2e8f0; font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3b82f6, stop:1 #8b5cf6);
    border-radius: 7px;
}
"""


class FileOpsWindow(QMainWindow):
    """Nexus File Operations — fast copy / move / delete GUI."""

    progress_signal = pyqtSignal(int, int, str)
    done_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus File Ops")
        self.resize(700, 520)
        self.setAcceptDrops(True)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setStyleSheet(DARK_STYLE)
        self.source_paths: list[str] = []
        self.worker = None

        self.progress_signal.connect(self._on_progress)
        self.done_signal.connect(self._on_done)

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)

        frame = QFrame()
        frame.setObjectName("main_frame")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 0, 0, 180))
        frame.setGraphicsEffect(shadow)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Nexus File Ops")
        title.setObjectName("title")
        hdr.addWidget(title)
        hdr.addStretch()
        sub = QLabel("Fast copy • move • delete")
        sub.setObjectName("subtitle")
        hdr.addWidget(sub)
        layout.addLayout(hdr)

        # Drop zone / file list
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(160)
        layout.addWidget(self.file_list)

        self.drop_label = QLabel(
            "Drop files or folders here\nor click 'Add Files' below"
        )
        self.drop_label.setObjectName("drop_label")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.drop_label)

        # Destination row
        dst_row = QHBoxLayout()
        dst_lbl = QLabel("Destination:")
        dst_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        dst_row.addWidget(dst_lbl)
        self.dst_input = QLineEdit()
        self.dst_input.setPlaceholderText("Choose destination folder…")
        dst_row.addWidget(self.dst_input, stretch=1)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self._browse_dst)
        dst_row.addWidget(btn_browse)
        layout.addLayout(dst_row)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Add Files")
        btn_add.clicked.connect(self._add_files)
        btn_row.addWidget(btn_add)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_files)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setObjectName("success")
        self.btn_copy.clicked.connect(lambda: self._run_op("copy"))
        btn_row.addWidget(self.btn_copy)

        self.btn_move = QPushButton("Move")
        self.btn_move.clicked.connect(lambda: self._run_op("move"))
        btn_row.addWidget(self.btn_move)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(lambda: self._run_op("delete"))
        btn_row.addWidget(self.btn_delete)

        layout.addLayout(btn_row)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_lbl = QLabel("Ready — drop files to start")
        self.status_lbl.setObjectName("status")
        layout.addWidget(self.status_lbl)

        root.addWidget(frame)

    # ── Drag & Drop ──
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_label.setStyleSheet("border: 2px dashed #60a5fa; color: #60a5fa;")

    def dragLeaveEvent(self, event):
        self.drop_label.setStyleSheet("")

    def dropEvent(self, event: QDropEvent):
        self.drop_label.setStyleSheet("")
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and path not in self.source_paths:
                self.source_paths.append(path)
        self._refresh_list()

    # ── Actions ──
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Files")
        for p in paths:
            if p not in self.source_paths:
                self.source_paths.append(p)
        if not paths:
            folder = QFileDialog.getExistingDirectory(self, "Select Folder")
            if folder and folder not in self.source_paths:
                self.source_paths.append(folder)
        self._refresh_list()

    def _browse_dst(self):
        folder = QFileDialog.getExistingDirectory(self, "Destination Folder")
        if folder:
            self.dst_input.setText(folder)

    def _clear_files(self):
        self.source_paths.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.file_list.clear()
        for p in self.source_paths:
            icon = "📁" if os.path.isdir(p) else "📄"
            size = ""
            if os.path.isfile(p):
                s = os.path.getsize(p)
                if s > 1_000_000_000:
                    size = f"  ({s / 1_000_000_000:.1f} GB)"
                elif s > 1_000_000:
                    size = f"  ({s / 1_000_000:.1f} MB)"
                elif s > 1_000:
                    size = f"  ({s / 1_000:.1f} KB)"
            self.file_list.addItem(f"{icon}  {os.path.basename(p)}{size}")
        self.drop_label.setVisible(len(self.source_paths) == 0)
        self.file_list.setVisible(len(self.source_paths) > 0)
        self.status_lbl.setText(f"{len(self.source_paths)} item(s) queued")

    def _run_op(self, op_type: str):
        if not self.source_paths:
            self.status_lbl.setText("No files selected!")
            return
        if op_type != "delete":
            dst = self.dst_input.text().strip()
            if not dst:
                self.status_lbl.setText("Please select a destination!")
                return

        ops = []
        for src in self.source_paths:
            if op_type == "delete":
                ops.append(("delete", src, ""))
            else:
                dst_path = os.path.join(
                    self.dst_input.text().strip(), os.path.basename(src)
                )
                ops.append((op_type, src, dst_path))

        self.progress.setVisible(True)
        self.progress.setMaximum(len(ops))
        self.progress.setValue(0)
        self.btn_copy.setEnabled(False)
        self.btn_move.setEnabled(False)
        self.btn_delete.setEnabled(False)

        self.worker = FileOpsWorker(
            ops,
            on_progress=lambda done, total, name: self.progress_signal.emit(
                done, total, name
            ),
            on_done=lambda errors: self.done_signal.emit(errors),
        )
        self.worker.start()

    def _on_progress(self, done, total, name):
        self.progress.setValue(done)
        self.status_lbl.setText(f"Processing: {name}  ({done}/{total})")

    def _on_done(self, errors):
        self.btn_copy.setEnabled(True)
        self.btn_move.setEnabled(True)
        self.btn_delete.setEnabled(True)
        if errors:
            self.status_lbl.setText(f"Done with {len(errors)} error(s)")
            self.status_lbl.setStyleSheet("color: #ef4444;")
        else:
            self.status_lbl.setText("✓ All operations completed successfully!")
            self.status_lbl.setStyleSheet("color: #22c55e;")
            self.source_paths.clear()
            self._refresh_list()
        QTimer.singleShot(3000, lambda: self.progress.setVisible(False))


def main():
    app = QApplication(sys.argv)
    win = FileOpsWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
