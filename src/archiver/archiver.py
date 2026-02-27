"""Nexus Archiver — zip / unzip / tar / 7z with a clean UI.

Supports:
  - .zip  (Python built-in zipfile)
  - .tar / .tar.gz / .tar.bz2 / .tar.xz  (Python built-in tarfile)
  - .7z   (via 7z CLI if installed, auto-detected)
  - .gz   (single-file gzip)

Drag-drop or browse to compress / extract.
"""

import gzip
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import zipfile

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
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

ARCHIVE_EXTENSIONS = {
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
    ".gz",
    ".7z",
}

# ──────────────────────────────────────────────────────────────────────
# Backend
# ──────────────────────────────────────────────────────────────────────


def find_7z() -> str | None:
    """Try to locate 7z binary on the system (Windows and Linux)."""
    candidates = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        "/usr/bin/7z",
        "/bin/7z",
        "/usr/local/bin/7z",
        shutil.which("7z") or "",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


_7Z_PATH = find_7z()


def is_archive(path: str) -> bool:
    """Check if a path looks like an archive we can handle."""
    low = path.lower()
    return any(low.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def _detect_format(path: str) -> str:
    low = path.lower()
    if low.endswith(".7z"):
        return "7z"
    if low.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    if low.endswith((".tar.bz2", ".tbz2")):
        return "tar.bz2"
    if low.endswith((".tar.xz", ".txz")):
        return "tar.xz"
    if low.endswith(".tar"):
        return "tar"
    if low.endswith(".gz"):
        return "gz"
    if low.endswith(".zip"):
        return "zip"
    return "zip"


def extract_archive(
    archive_path: str, dest_dir: str, password: str = "", on_progress=None
) -> list[str]:
    """Extract an archive. Returns list of errors (empty = success)."""
    errors = []
    fmt = _detect_format(archive_path)
    try:
        if fmt == "7z":
            if not _7Z_PATH:
                return [
                    "7-Zip is not installed. Please install it to extract .7z files."
                ]
            cmd = [_7Z_PATH, "x", archive_path, f"-o{dest_dir}", "-y"]
            if password:
                cmd.append(f"-p{password}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                errors.append(result.stderr or "7z extraction failed")
        elif fmt.startswith("tar"):
            mode = {
                "tar": "r:",
                "tar.gz": "r:gz",
                "tar.bz2": "r:bz2",
                "tar.xz": "r:xz",
            }[fmt]
            with tarfile.open(archive_path, mode) as tf:
                members = tf.getmembers()
                total = len(members)
                for i, member in enumerate(members):
                    tf.extract(member, dest_dir)
                    if on_progress:
                        on_progress(i + 1, total)
        elif fmt == "gz":
            # Single file gzip
            base = os.path.basename(archive_path)
            out_name = base[:-3] if base.endswith(".gz") else base + ".out"
            out_path = os.path.join(dest_dir, out_name)
            with gzip.open(archive_path, "rb") as fin, open(out_path, "wb") as fout:
                shutil.copyfileobj(fin, fout)
        else:  # zip
            pwd_bytes = password.encode("utf-8") if password else None
            with zipfile.ZipFile(archive_path, "r") as zf:
                members = zf.infolist()
                total = len(members)
                for i, member in enumerate(members):
                    try:
                        zf.extract(member, dest_dir, pwd=pwd_bytes)
                    except RuntimeError as e:
                        if "Bad password" in str(e) or "password required" in str(e):
                            errors.append("Invalid or missing password")
                            break
                        raise
                    if on_progress:
                        on_progress(i + 1, total)
    except Exception as e:
        errors.append(str(e))
    return errors


def create_archive(
    sources: list[str],
    output_path: str,
    fmt: str = "zip",
    password: str = "",
    on_progress=None,
) -> list[str]:
    """Create an archive from source files/dirs. Returns errors."""
    errors = []
    try:
        use_7z = fmt == "7z" or (fmt == "zip" and password)
        if use_7z:
            if not _7Z_PATH:
                return [
                    "7-Zip is not installed. Install it to create .7z or encrypted .zip archives."
                ]
            cmd = [_7Z_PATH, "a", output_path] + sources

            # Dictionary Size and Compression Level (only if fmt is 7z, not fallback zip)
            if fmt == "7z":
                level = getattr(sys, "_7z_level", "Normal")
                dict_size = getattr(sys, "_7z_dict", "16 MB")

                # Compression level mappings
                mx_map = {
                    "Store": "-mx0",
                    "Fastest": "-mx1",
                    "Fast": "-mx3",
                    "Normal": "-mx5",
                    "Maximum": "-mx7",
                    "Ultra": "-mx9",
                }
                cmd.append(mx_map.get(level, "-mx5"))

                # Dictionary size mappings (only if not Store)
                if level != "Store":
                    md_map = {
                        "1 MB": "-md1m",
                        "16 MB": "-md16m",
                        "32 MB": "-md32m",
                        "64 MB": "-md64m",
                        "128 MB": "-md128m",
                        "256 MB": "-md256m",
                    }
                    cmd.append(md_map.get(dict_size, "-md16m"))

            if password:
                cmd.append(f"-p{password}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                errors.append(result.stderr or "Archive creation failed")
        elif fmt.startswith("tar"):
            mode = {
                "tar": "w:",
                "tar.gz": "w:gz",
                "tar.bz2": "w:bz2",
                "tar.xz": "w:xz",
            }[fmt]
            with tarfile.open(output_path, mode) as tf:
                for i, src in enumerate(sources):
                    tf.add(src, arcname=os.path.basename(src))
                    if on_progress:
                        on_progress(i + 1, len(sources))
        else:  # zip
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                all_files = []
                for src in sources:
                    if os.path.isdir(src):
                        for root, _, files in os.walk(src):
                            for f in files:
                                fp = os.path.join(root, f)
                                arcname = os.path.join(
                                    os.path.basename(src),
                                    os.path.relpath(fp, src),
                                )
                                all_files.append((fp, arcname))
                    else:
                        all_files.append((src, os.path.basename(src)))
                total = len(all_files)
                for i, (fp, arcname) in enumerate(all_files):
                    zf.write(fp, arcname)
                    if on_progress:
                        on_progress(i + 1, total)
    except Exception as e:
        errors.append(str(e))
    return errors


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
QLabel#title { font-size: 18px; font-weight: 700; color: #a78bfa; }
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
QListWidget::item:selected { background: rgba(167,139,250,0.15); }
QPushButton {
    background: rgba(167,139,250,0.12);
    border: 1px solid rgba(167,139,250,0.25);
    border-radius: 10px; padding: 8px 18px;
    color: #a78bfa; font-weight: 600; font-size: 12px;
}
QPushButton:hover { background: rgba(167,139,250,0.22); }
QPushButton#extract { background: rgba(34,197,94,0.12); border-color: rgba(34,197,94,0.25); color: #22c55e; }
QPushButton#extract:hover { background: rgba(34,197,94,0.22); }
QLineEdit {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px; padding: 8px 14px;
    color: #e2e8f0; font-size: 13px;
}
QComboBox {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px; padding: 6px 12px;
    color: #e2e8f0; font-size: 12px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { image: none; border: none; }
QProgressBar {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px; height: 18px;
    text-align: center; color: #e2e8f0; font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #8b5cf6, stop:1 #a78bfa);
    border-radius: 7px;
}
"""


class ArchiverWindow(QMainWindow):
    """Nexus Archiver — compress & extract with a clean UI."""

    progress_signal = pyqtSignal(int, int)
    done_signal = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus Archiver")
        self.resize(700, 540)
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
        title = QLabel("Nexus Archiver")
        title.setObjectName("title")
        hdr.addWidget(title)
        hdr.addStretch()

        formats = ["zip"]
        if _7Z_PATH:
            formats.append("7z")
        formats.extend(["tar.gz", "tar.bz2", "tar.xz", "tar"])

        sub = QLabel("zip • tar • " + ("7z • " if _7Z_PATH else "") + "gzip")
        sub.setObjectName("subtitle")
        hdr.addWidget(sub)
        layout.addLayout(hdr)

        # 7z detection
        if _7Z_PATH:
            z7_lbl = QLabel(f"✓ 7-Zip detected: {_7Z_PATH}")
            z7_lbl.setStyleSheet("font-size: 10px; color: #22c55e;")
            layout.addWidget(z7_lbl)

        # File list / drop zone
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(140)
        layout.addWidget(self.file_list)

        self.drop_label = QLabel(
            "Drop archives to EXTRACT\nor drop files/folders to COMPRESS"
        )
        self.drop_label.setObjectName("drop_label")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.drop_label)

        # Output row
        dst_row = QHBoxLayout()
        dst_lbl = QLabel("Output:")
        dst_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        dst_row.addWidget(dst_lbl)
        self.dst_input = QLineEdit()
        self.dst_input.setPlaceholderText("Output folder (or leave blank for same dir)")
        dst_row.addWidget(self.dst_input, stretch=1)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self._browse_dst)
        dst_row.addWidget(btn_browse)
        layout.addLayout(dst_row)

        # Format selector + action buttons
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Add")
        btn_add.clicked.connect(self._add_files)
        btn_row.addWidget(btn_add)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()

        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("Password (opt.)")
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.pwd_input.setMaximumWidth(120)
        btn_row.addWidget(self.pwd_input)

        if _7Z_PATH:
            self.btn_opts = QPushButton("⚙️")
            self.btn_opts.setToolTip("Compression Options (7z only)")
            self.btn_opts.setMaximumWidth(40)
            self.btn_opts.clicked.connect(self._toggle_options)
            btn_row.addWidget(self.btn_opts)

        fmt_lbl = QLabel("Format:")
        fmt_lbl.setStyleSheet("font-size: 12px;")
        btn_row.addWidget(fmt_lbl)
        self.fmt_combo = QComboBox()
        for f in formats:
            self.fmt_combo.addItem(f)
        btn_row.addWidget(self.fmt_combo)

        self.btn_compress = QPushButton("Compress")
        self.btn_compress.clicked.connect(self._compress)
        btn_row.addWidget(self.btn_compress)

        self.btn_extract = QPushButton("Extract")
        self.btn_extract.setObjectName("extract")
        self.btn_extract.clicked.connect(self._extract)
        btn_row.addWidget(self.btn_extract)

        layout.addLayout(btn_row)

        # Options panel (Hidden by default)
        self.opts_frame = QFrame()
        self.opts_frame.setVisible(False)
        opts_layout = QHBoxLayout(self.opts_frame)
        opts_layout.setContentsMargins(0, 0, 0, 0)

        opts_layout.addStretch()

        lbl_lvl = QLabel("Level:")
        opts_layout.addWidget(lbl_lvl)
        self.combo_lvl = QComboBox()
        self.combo_lvl.addItems(
            ["Store", "Fastest", "Fast", "Normal", "Maximum", "Ultra"]
        )
        self.combo_lvl.setCurrentText("Normal")
        opts_layout.addWidget(self.combo_lvl)

        lbl_dict = QLabel(" Dictionary:")
        opts_layout.addWidget(lbl_dict)
        self.combo_dict = QComboBox()
        self.combo_dict.addItems(
            ["1 MB", "16 MB", "32 MB", "64 MB", "128 MB", "256 MB"]
        )
        self.combo_dict.setCurrentText("16 MB")
        opts_layout.addWidget(self.combo_dict)

        layout.addWidget(self.opts_frame)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_lbl = QLabel("Ready — drop files or archives")
        self.status_lbl.setObjectName("status")
        layout.addWidget(self.status_lbl)

        root.addWidget(frame)

    # ── Drag & Drop ──
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_label.setStyleSheet("border: 2px dashed #a78bfa; color: #a78bfa;")

    def dragLeaveEvent(self, event):
        self.drop_label.setStyleSheet("")

    def _toggle_options(self):
        self.opts_frame.setVisible(not self.opts_frame.isVisible())

    def dropEvent(self, event: QDropEvent):
        self.drop_label.setStyleSheet("")
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and path not in self.source_paths:
                self.source_paths.append(path)
        self._refresh_list()

        # Auto-detect: if all items are archives, suggest extract
        if all(is_archive(p) for p in self.source_paths):
            self.status_lbl.setText("Archive(s) detected — click Extract")
            self.status_lbl.setStyleSheet("color: #22c55e;")

    # ── Actions ──
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Files or Archives")
        for p in paths:
            if p not in self.source_paths:
                self.source_paths.append(p)
        if not paths:
            folder = QFileDialog.getExistingDirectory(self, "Select Folder")
            if folder and folder not in self.source_paths:
                self.source_paths.append(folder)
        self._refresh_list()

    def _browse_dst(self):
        folder = QFileDialog.getExistingDirectory(self, "Output Folder")
        if folder:
            self.dst_input.setText(folder)

    def _clear(self):
        self.source_paths.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.file_list.clear()
        for p in self.source_paths:
            icon = "📦" if is_archive(p) else ("📁" if os.path.isdir(p) else "📄")
            self.file_list.addItem(f"{icon}  {os.path.basename(p)}")
        self.drop_label.setVisible(len(self.source_paths) == 0)
        self.file_list.setVisible(len(self.source_paths) > 0)
        self.status_lbl.setText(f"{len(self.source_paths)} item(s) queued")
        self.status_lbl.setStyleSheet("")

    def _compress(self):
        if not self.source_paths:
            self.status_lbl.setText("No files selected!")
            return
        dst = self.dst_input.text().strip()
        if not dst:
            dst = os.path.dirname(self.source_paths[0])

        fmt = self.fmt_combo.currentText()
        ext = "." + fmt if not fmt.startswith(".") else fmt
        if fmt.startswith("tar"):
            ext = ".tar." + fmt.split(".")[-1] if "." in fmt else ".tar"

        name = os.path.splitext(os.path.basename(self.source_paths[0]))[0]
        if len(self.source_paths) > 1:
            name = "archive"
        out_path = os.path.join(dst, name + ext)

        self._set_busy(True)
        pwd = self.pwd_input.text().strip()

        # Hacky way to pass options to the backend without changing signature drastically
        if hasattr(self, "combo_lvl"):
            sys._7z_level = self.combo_lvl.currentText()
            sys._7z_dict = self.combo_dict.currentText()

        def worker():
            errors = create_archive(
                self.source_paths,
                out_path,
                fmt,
                password=pwd,
                on_progress=lambda done, total: self.progress_signal.emit(done, total),
            )
            self.done_signal.emit(errors, f"Created: {os.path.basename(out_path)}")

        threading.Thread(target=worker, daemon=True).start()

    def _extract(self):
        archives = [p for p in self.source_paths if is_archive(p)]
        if not archives:
            self.status_lbl.setText("No archives selected!")
            return

        dst = self.dst_input.text().strip()
        pwd = self.pwd_input.text().strip()
        self._set_busy(True)

        def worker():
            all_errors = []
            for _idx, arc in enumerate(archives):
                out = dst or os.path.dirname(arc)
                errors = extract_archive(
                    arc,
                    out,
                    password=pwd,
                    on_progress=lambda done, total: self.progress_signal.emit(
                        done, total
                    ),
                )
                all_errors.extend(errors)
            self.done_signal.emit(
                all_errors,
                f"Extracted {len(archives)} archive(s)",
            )

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy: bool):
        self.progress.setVisible(busy)
        self.progress.setValue(0)
        self.btn_compress.setEnabled(not busy)
        self.btn_extract.setEnabled(not busy)

    def _on_progress(self, done, total):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.status_lbl.setText(f"Processing… {done}/{total}")

    def _on_done(self, errors, message):
        self._set_busy(False)
        if errors:
            self.status_lbl.setText(f"Done with errors: {'; '.join(errors[:2])}")
            self.status_lbl.setStyleSheet("color: #ef4444;")
        else:
            self.status_lbl.setText(f"✓ {message}")
            self.status_lbl.setStyleSheet("color: #22c55e;")
        QTimer.singleShot(4000, lambda: self.progress.setVisible(False))


def main():
    app = QApplication(sys.argv)
    win = ArchiverWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
