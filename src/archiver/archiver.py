"""Nexus Archiver — zip / unzip / tar / 7z with a clean UI.

Supports:
  - .zip  (Python built-in zipfile)
  - .tar / .tar.gz / .tar.bz2 / .tar.xz  (Python built-in tarfile)
  - .7z   (via 7z CLI if installed, auto-detected)
  - .gz   (single-file gzip)

Drag-drop or browse to compress / extract.
"""

import gzip
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import zipfile

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
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
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

from src.common.config import ARCHIVER_SETTINGS, ASSETS_DIR

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

/* ── Input & Combo ── */
QLineEdit, QComboBox {{
    background: {C["panel"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
    padding: 9px 14px;
    color: {C["text"]};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New';
    font-size: 11px;
    selection-background-color: {C["cyan_dim"]};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {C["cyan_dim"]};
    background: {C["panel"]};
}}
QLineEdit::placeholder {{
    color: {C["muted"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {C["surface"]};
    border: 1px solid {C["border"]};
    selection-background-color: {C["cyan_dim"]};
    color: {C["text"]};
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
QPushButton#btn_compress {{
    color: {C["cyan"]};
    border: 1px solid rgba(0,212,255,0.25);
    background: rgba(0,212,255,0.06);
}}
QPushButton#btn_compress:hover {{
    background: rgba(0,212,255,0.12);
    border-color: rgba(0,212,255,0.45);
}}

QPushButton#btn_extract {{
    color: {C["green"]};
    border: 1px solid rgba(0,255,157,0.25);
    background: rgba(0,255,157,0.06);
}}
QPushButton#btn_extract:hover {{
    background: rgba(0,255,157,0.12);
    border-color: rgba(0,255,157,0.45);
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


# ─── Separator line ───────────────────────────────────────────────────
def make_divider():
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


class ArchiverWindow(QMainWindow):
    """Nexus Archiver — compress & extract with a clean UI."""

    progress_signal = pyqtSignal(int, int)
    done_signal = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NEXUS ARCHIVER")
        self.setMinimumSize(680, 580)
        self.resize(720, 600)
        self.setAcceptDrops(True)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.source_paths: list[str] = []
        self.worker = None

        self.progress_signal.connect(self._on_progress)
        self.done_signal.connect(self._on_done)

        self.setStyleSheet(STYLESHEET)
        self._build_ui()
        self._load_settings()

    def _load_settings(self):
        if os.path.exists(ARCHIVER_SETTINGS):
            try:
                with open(ARCHIVER_SETTINGS) as f:
                    data = json.load(f)
                    self.dst_input.setText(data.get("last_dst", ""))
            except Exception:
                pass

    def _save_settings(self):
        try:
            data = {"last_dst": self.dst_input.text()}
            with open(ARCHIVER_SETTINGS, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

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
        t = QLabel("NEXUS ARCHIVER")
        t.setObjectName("title")
        s = QLabel("ZIP · TAR · 7Z · GZIP")
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
        self.drop_zone = QLabel("DROP ARCHIVES TO EXTRACT OR FILES TO COMPRESS")
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

        # ── Add / clear / Password row ──────────
        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(8)

        btn_add = QPushButton("+ ADD")
        btn_add.clicked.connect(self._add_files)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row1.addWidget(btn_add)

        btn_clear = QPushButton("CLEAR")
        btn_clear.clicked.connect(self._clear)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row1.addWidget(btn_clear)

        btn_row1.addStretch()

        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("PASSWORD (OPT.)")
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.pwd_input.setFixedWidth(140)
        btn_row1.addWidget(self.pwd_input)

        lay.addLayout(btn_row1)
        lay.addWidget(make_divider())

        # ── Output ─────────────────────────
        ol = QLabel("OUTPUT")
        ol.setObjectName("section_label")
        lay.addWidget(ol)

        dst_row = QHBoxLayout()
        dst_row.setSpacing(8)
        self.dst_input = QLineEdit()
        self.dst_input.setPlaceholderText("select output folder (blank = same dir)")
        dst_row.addWidget(self.dst_input, stretch=1)
        btn_browse = QPushButton("BROWSE")
        btn_browse.clicked.connect(self._browse_dst)
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        dst_row.addWidget(btn_browse)
        lay.addLayout(dst_row)

        lay.addWidget(make_divider())

        # ── Options ────────────────────
        opts_header = QHBoxLayout()
        opts_label = QLabel("OPTIONS")
        opts_label.setObjectName("section_label")
        opts_header.addWidget(opts_label)
        opts_header.addStretch()

        if _7Z_PATH:
            self.btn_opts_toggle = QPushButton("⚙ 7-ZIP OPTS")
            self.btn_opts_toggle.setFixedHeight(24)
            self.btn_opts_toggle.setStyleSheet("font-size: 8px; padding: 0 10px;")
            self.btn_opts_toggle.setCheckable(True)
            self.btn_opts_toggle.clicked.connect(self._toggle_options)
            opts_header.addWidget(self.btn_opts_toggle)

        lay.addLayout(opts_header)

        # Options panel (Hidden by default)
        self.opts_frame = QFrame()
        self.opts_frame.setVisible(False)
        self.opts_frame.setStyleSheet(f"background: {C['panel']}; border-radius: 10px; border: 1px solid {C['border2']};")
        opts_layout = QHBoxLayout(self.opts_frame)
        opts_layout.setContentsMargins(15, 10, 15, 10)
        opts_layout.setSpacing(15)

        lvl_box = QVBoxLayout()
        lvl_lbl = QLabel("COMPRESSION LEVEL")
        lvl_lbl.setObjectName("section_label")
        lvl_box.addWidget(lvl_lbl)
        self.combo_lvl = QComboBox()
        self.combo_lvl.addItems(["Store", "Fastest", "Fast", "Normal", "Maximum", "Ultra"])
        self.combo_lvl.setCurrentText("Normal")
        lvl_box.addWidget(self.combo_lvl)
        opts_layout.addLayout(lvl_box)

        dict_box = QVBoxLayout()
        dict_lbl = QLabel("DICTIONARY SIZE")
        dict_lbl.setObjectName("section_label")
        dict_box.addWidget(dict_lbl)
        self.combo_dict = QComboBox()
        self.combo_dict.addItems(["1 MB", "16 MB", "32 MB", "64 MB", "128 MB", "256 MB"])
        self.combo_dict.setCurrentText("16 MB")
        dict_box.addWidget(self.combo_dict)
        opts_layout.addLayout(dict_box)

        lay.addWidget(self.opts_frame)

        # ── Format & Action row ──────────
        ops_row = QHBoxLayout()
        ops_row.setSpacing(8)

        formats = ["zip"]
        if _7Z_PATH:
            formats.append("7z")
        formats.extend(["tar.gz", "tar.bz2", "tar.xz", "tar"])

        self.fmt_combo = QComboBox()
        for f in formats:
            self.fmt_combo.addItem(f)
        self.fmt_combo.setFixedWidth(100)
        ops_row.addWidget(self.fmt_combo)

        ops_row.addStretch()

        self.btn_compress = QPushButton("COMPRESS")
        self.btn_compress.setObjectName("btn_compress")
        self.btn_compress.setFixedHeight(38)
        self.btn_compress.setMinimumWidth(120)
        self.btn_compress.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_compress.clicked.connect(self._compress)
        ops_row.addWidget(self.btn_compress)

        self.btn_extract = QPushButton("EXTRACT")
        self.btn_extract.setObjectName("btn_extract")
        self.btn_extract.setFixedHeight(38)
        self.btn_extract.setMinimumWidth(120)
        self.btn_extract.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_extract.clicked.connect(self._extract)
        ops_row.addWidget(self.btn_extract)

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

    def _toggle_options(self):
        self.opts_frame.setVisible(not self.opts_frame.isVisible())

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
            self._save_settings()

    def _clear(self):
        self.source_paths.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.file_list.clear()
        for p in self.source_paths:
            is_arc = is_archive(p)
            is_dir = os.path.isdir(p)
            icon = "📦" if is_arc else ("📁" if is_dir else "📄")

            size_str = ""
            if os.path.isfile(p):
                sz = os.path.getsize(p)
                if sz > 1_000_000_000: size_str = f"  {sz / 1_000_000_000:.1f} GB"
                elif sz > 1_000_000: size_str = f"  {sz / 1_000_000:.1f} MB"
                elif sz > 1_000: size_str = f"  {sz / 1_000:.1f} KB"
                else: size_str = f"  {sz} B"

            item = QListWidgetItem(f"{icon}   {os.path.basename(p)}{size_str}")
            item.setForeground(QColor(C["cyan"] if is_arc else (C["green"] if is_dir else C["text"])))
            self.file_list.addItem(item)

        has = len(self.source_paths) > 0
        self.file_list.setVisible(has)
        self.drop_zone.setVisible(not has)

        count = len(self.source_paths)
        if has:
            if all(is_archive(p) for p in self.source_paths):
                self._set_status(f"{count} ARCHIVE(S) READY TO EXTRACT", C["green"])
            else:
                self._set_status(f"{count} ITEM(S) QUEUED", C["muted"])
        else:
            self._set_status("READY", C["muted"])

    def _compress(self):
        if not self.source_paths:
            self._set_status("NO FILES SELECTED!", C["red"])
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
            self._set_status("NO ARCHIVES SELECTED!", C["red"])
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
        if busy:
            self._set_status("WORKING…", C["cyan"])
            self.status_dot.setStyleSheet(f"color: {C['cyan']}; font-size: 10px;")

    def _on_progress(self, done, total):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self._set_status(f"PROCESSING… [{done}/{total}]", C["cyan"])

    def _on_done(self, errors, message):
        self._set_busy(False)
        if errors:
            self._set_status(f"ERROR: {errors[0][:40]}...", C["red"])
            self.status_dot.setStyleSheet(f"color: {C['red']}; font-size: 10px;")
        else:
            self._set_status(f"{message} ✓", C["green"])
            self.status_dot.setStyleSheet(f"color: {C['green']}; font-size: 10px;")
            self.source_paths.clear()
            self._refresh_list()

        QTimer.singleShot(4000, lambda: (
            self._set_status("READY", C["muted"]),
            self.status_dot.setStyleSheet(f"color: {C['green']}; font-size: 10px;"),
            self.progress.setVisible(False)
        ))

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(f" {text}")
        self.status_lbl.setStyleSheet(
            f"font-family: 'JetBrains Mono','Consolas','Courier New'; "
            f"font-size: 11px; letter-spacing: 1px; color: {color};"
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

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

    win = ArchiverWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
