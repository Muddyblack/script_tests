"""Nexus Archiver — backend + standalone window.

Formats supported:
  Python (always):  .zip  .tar  .tar.gz  .tar.bz2  .tar.xz  .gz
  7-Zip (if found): .7z   .zip(pw)  .rar  .iso  .cab  .wim  .arj  .lzh  .xz  .zst
"""

import gzip
import json
import os
import re
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
    QCheckBox,
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
from src.common.theme import ThemeManager
from src.common.theme_template import TOOL_SHEET

ICON_PATH = os.path.join(ASSETS_DIR, "nexus_icon.png")

# All extensions we can at least extract
ARCHIVE_EXTENSIONS = {
    ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2",
    ".tar.xz", ".txz", ".gz", ".7z",
    ".rar", ".iso", ".cab", ".wim", ".arj", ".lzh", ".xz", ".zst",
}

# (can_extract_python, can_create_python, can_extract_7z, can_create_7z, supports_password_7z)
# fmt: off
FORMAT_CAPS: dict[str, tuple[bool, bool, bool, bool, bool]] = {
    "zip":     (True,  True,  True,  True,  True ),
    "7z":      (False, False, True,  True,  True ),
    "tar":     (True,  True,  False, False, False),
    "tar.gz":  (True,  True,  False, False, False),
    "tar.bz2": (True,  True,  False, False, False),
    "tar.xz":  (True,  True,  False, False, False),
    "gz":      (True,  True,  False, False, False),
    "rar":     (False, False, True,  False, False),
    "iso":     (False, False, True,  False, False),
    "cab":     (False, False, True,  False, False),
    "wim":     (False, False, True,  False, False),
    "arj":     (False, False, True,  False, False),
    "lzh":     (False, False, True,  False, False),
    "xz":      (False, False, True,  False, False),
    "zst":     (False, False, True,  False, False),
}
# fmt: on

# Formats that can be created (shown in the format combo)
CREATABLE_FORMATS = ["zip", "7z", "tar.gz", "tar.bz2", "tar.xz", "tar", "gz"]

# Compression level → 7z -mx flag
MX_MAP = {
    "Store":   "-mx0",
    "Fastest": "-mx1",
    "Fast":    "-mx3",
    "Normal":  "-mx5",
    "Maximum": "-mx7",
    "Ultra":   "-mx9",
}

# Dictionary size → 7z -md flag
MD_MAP = {
    "256 KB": "-md256k",
    "1 MB":   "-md1m",
    "4 MB":   "-md4m",
    "16 MB":  "-md16m",
    "32 MB":  "-md32m",
    "64 MB":  "-md64m",
    "128 MB": "-md128m",
    "256 MB": "-md256m",
    "512 MB": "-md512m",
    "1 GB":   "-md1024m",
}

# Thread count → 7z -mmt flag
MT_MAP = {
    "Auto": "-mmt",
    "1":    "-mmt1",
    "2":    "-mmt2",
    "4":    "-mmt4",
    "8":    "-mmt8",
    "16":   "-mmt16",
}


# ──────────────────────────────────────────────────────────────────────
# Backend
# ──────────────────────────────────────────────────────────────────────


def find_7z() -> str | None:
    """Try to locate 7z binary on the system."""
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
    """Return True if path is a file format we can handle as an archive."""
    low = path.lower()
    return any(low.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def detect_format(path: str) -> str:
    """Detect archive format string from filename."""
    low = path.lower()
    for ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"):
        if low.endswith(ext):
            # normalise to canonical form
            return {"tgz": "tar.gz", "tbz2": "tar.bz2", "txz": "tar.xz"}.get(
                ext.lstrip("."), ext.lstrip(".")
            )
    for ext in (".7z", ".rar", ".iso", ".cab", ".wim", ".arj", ".lzh", ".zst", ".xz",
                ".zip", ".tar", ".gz"):
        if low.endswith(ext):
            return ext.lstrip(".")
    return "zip"


def get_capabilities(path: str) -> dict:
    """Return a dict describing what can be done with this file.

    Keys: can_extract, can_create, needs_7z, supports_password, fmt
    """
    fmt = detect_format(path)
    caps = FORMAT_CAPS.get(fmt, (False, False, False, False, False))
    ep, cp, e7, c7, pw = caps
    has_7z = _7Z_PATH is not None
    return {
        "fmt": fmt,
        "can_extract": ep or (e7 and has_7z),
        "can_create": cp or (c7 and has_7z),
        "needs_7z": not ep and e7,
        "supports_password": pw and has_7z,
        "has_7z": has_7z,
    }


def list_archive_contents(archive_path: str) -> list[str]:
    """Return a list of member names inside an archive (best-effort)."""
    fmt = detect_format(archive_path)
    try:
        if fmt == "zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                return zf.namelist()
        elif fmt.startswith("tar"):
            mode_map = {"tar": "r:", "tar.gz": "r:gz", "tar.bz2": "r:bz2", "tar.xz": "r:xz"}
            with tarfile.open(archive_path, mode_map.get(fmt, "r:*")) as tf:
                return tf.getnames()
        elif _7Z_PATH:
            result = subprocess.run(
                [_7Z_PATH, "l", "-slt", archive_path],
                capture_output=True, text=True, timeout=15,
            )
            return re.findall(r"^Path = (.+)$", result.stdout, re.MULTILINE)[1:]
    except Exception:
        pass
    return []


def _run_7z_with_progress(cmd: list[str], on_progress) -> str:
    """Run 7z command, parse `XX%` lines for progress. Returns stderr on failure."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    last_err = []
    for line in proc.stdout:
        last_err.append(line)
        m = re.search(r"\b(\d{1,3})%", line)
        if m and on_progress:
            on_progress(int(m.group(1)), 100)
    proc.wait()
    if proc.returncode != 0:
        return "".join(last_err[-10:]).strip() or "7z operation failed"
    return ""


def extract_archive(
    archive_path: str,
    dest_dir: str,
    password: str = "",
    on_progress=None,
) -> list[str]:
    """Extract an archive. Returns list of errors (empty = success)."""
    errors = []
    fmt = detect_format(archive_path)
    caps = get_capabilities(archive_path)
    try:
        os.makedirs(dest_dir, exist_ok=True)
        use_7z = (not FORMAT_CAPS.get(fmt, (False,))[0]) or (fmt == "7z")
        if use_7z:
            if not _7Z_PATH:
                return [f"7-Zip not found — cannot extract .{fmt} files. Install 7-Zip."]
            cmd = [_7Z_PATH, "x", archive_path, f"-o{dest_dir}", "-y"]
            if password:
                cmd.append(f"-p{password}")
            err = _run_7z_with_progress(cmd, on_progress)
            if err:
                errors.append(err)
        elif fmt.startswith("tar"):
            mode_map = {"tar": "r:", "tar.gz": "r:gz", "tar.bz2": "r:bz2", "tar.xz": "r:xz"}
            with tarfile.open(archive_path, mode_map.get(fmt, "r:*")) as tf:
                members = tf.getmembers()
                total = len(members)
                for i, member in enumerate(members):
                    tf.extract(member, dest_dir, filter="data")
                    if on_progress:
                        on_progress(i + 1, total)
        elif fmt == "gz":
            base = os.path.basename(archive_path)
            out_name = base[:-3] if base.endswith(".gz") else base + ".out"
            out_path = os.path.join(dest_dir, out_name)
            with gzip.open(archive_path, "rb") as fin, open(out_path, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            if on_progress:
                on_progress(1, 1)
        else:  # zip (python)
            pwd_bytes = password.encode() if password else None
            with zipfile.ZipFile(archive_path, "r") as zf:
                members = zf.infolist()
                total = len(members)
                for i, member in enumerate(members):
                    try:
                        zf.extract(member, dest_dir, pwd=pwd_bytes)
                    except RuntimeError as e:
                        if "password" in str(e).lower():
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
    level: str = "Normal",
    dict_size: str = "16 MB",
    threads: str = "Auto",
    solid: bool = True,
    on_progress=None,
) -> list[str]:
    """Create an archive from source files/dirs. Returns errors."""
    errors = []
    try:
        use_7z = fmt == "7z" or (fmt == "zip" and password)
        if use_7z:
            if not _7Z_PATH:
                return ["7-Zip not found — install it to create .7z or encrypted .zip."]
            cmd = [_7Z_PATH, "a", output_path] + sources
            cmd.append(MX_MAP.get(level, "-mx5"))
            if fmt == "7z":
                if level != "Store":
                    cmd.append(MD_MAP.get(dict_size, "-md16m"))
                cmd.append(MT_MAP.get(threads, "-mmt"))
                if solid:
                    cmd.append("-ms=on")
                else:
                    cmd.append("-ms=off")
            if password:
                cmd.append(f"-p{password}")
                if fmt == "7z":
                    cmd.append("-mhe=on")  # encrypt headers too
            err = _run_7z_with_progress(cmd, on_progress)
            if err:
                errors.append(err)
        elif fmt.startswith("tar"):
            mode_map = {"tar": "w:", "tar.gz": "w:gz", "tar.bz2": "w:bz2", "tar.xz": "w:xz"}
            with tarfile.open(output_path, mode_map.get(fmt, "w:")) as tf:
                for i, src in enumerate(sources):
                    tf.add(src, arcname=os.path.basename(src))
                    if on_progress:
                        on_progress(i + 1, len(sources))
        elif fmt == "gz":
            if len(sources) != 1 or os.path.isdir(sources[0]):
                return ["gzip only supports single files — use tar.gz for multiple files."]
            with open(sources[0], "rb") as fin, gzip.open(output_path, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            if on_progress:
                on_progress(1, 1)
        else:  # zip (python, no password)
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
        self.mgr = ThemeManager()

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
        p.setBrush(QColor(self.mgr["bg_overlay"]))
        path = QPainterPath()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 2, 2)
        p.drawPath(path)

        if self.maximum() > 0 and self.value() > 0:
            fill_w = int(r.width() * self.value() / self.maximum())
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0, QColor(self.mgr["accent"]))
            grad.setColorAt(1, QColor(self.mgr["success"]))
            p.setBrush(grad)
            chunk = QPainterPath()
            chunk.addRoundedRect(0, 0, fill_w, r.height(), 2, 2)
            p.drawPath(chunk)

            # Glow overlay
            import math

            alpha = int(30 + 20 * math.sin(self._glow))
            glow_color = QColor(self.mgr["accent"])
            # Reconstruct color with alpha to avoid QColor(r,g,b,a) mismatch in some PyQt versions if passing string
            glow_color.setAlpha(alpha)
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
        self.mgr = ThemeManager()
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
        self.mgr.theme_changed.connect(self._apply_theme)

        self._build_ui()
        self._apply_theme()
        self._load_settings()

    def _apply_theme(self):
        self.mgr.apply_to_widget(self, TOOL_SHEET)
        # Update dot color
        self.status_dot.setStyleSheet(f"color: {self.mgr['success']}; font-size: 10px;")
        self.opts_frame.setStyleSheet(
            f"background: {self.mgr['bg_overlay']}; border-radius: 10px; border: 1px solid {self.mgr['border_light']};"
        )

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
        opts_layout = QHBoxLayout(self.opts_frame)
        opts_layout.setContentsMargins(15, 10, 15, 10)
        opts_layout.setSpacing(15)

        lvl_box = QVBoxLayout()
        lvl_lbl = QLabel("COMPRESSION LEVEL")
        lvl_lbl.setObjectName("section_label")
        lvl_box.addWidget(lvl_lbl)
        self.combo_lvl = QComboBox()
        self.combo_lvl.addItems(
            ["Store", "Fastest", "Fast", "Normal", "Maximum", "Ultra"]
        )
        self.combo_lvl.setCurrentText("Normal")
        lvl_box.addWidget(self.combo_lvl)
        opts_layout.addLayout(lvl_box)

        dict_box = QVBoxLayout()
        dict_lbl = QLabel("DICTIONARY SIZE")
        dict_lbl.setObjectName("section_label")
        dict_box.addWidget(dict_lbl)
        self.combo_dict = QComboBox()
        self.combo_dict.addItems(list(MD_MAP.keys()))
        self.combo_dict.setCurrentText("16 MB")
        dict_box.addWidget(self.combo_dict)
        opts_layout.addLayout(dict_box)

        mt_box = QVBoxLayout()
        mt_lbl = QLabel("THREADS")
        mt_lbl.setObjectName("section_label")
        mt_box.addWidget(mt_lbl)
        self.combo_mt = QComboBox()
        self.combo_mt.addItems(list(MT_MAP.keys()))
        self.combo_mt.setCurrentText("Auto")
        mt_box.addWidget(self.combo_mt)
        opts_layout.addLayout(mt_box)

        solid_box = QVBoxLayout()
        solid_lbl = QLabel("SOLID")
        solid_lbl.setObjectName("section_label")
        solid_box.addWidget(solid_lbl)
        self.chk_solid = QCheckBox("Solid archive")
        self.chk_solid.setChecked(True)
        solid_box.addWidget(self.chk_solid)
        opts_layout.addLayout(solid_box)

        lay.addWidget(self.opts_frame)

        # ── Format & Action row ──────────
        ops_row = QHBoxLayout()
        ops_row.setSpacing(8)

        formats = [f for f in CREATABLE_FORMATS if f not in ("7z",) or _7Z_PATH]

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
            arc_fmt = detect_format(p).upper() if is_arc else ""
            icon = f"📦 {arc_fmt}" if is_arc else ("📁" if is_dir else "📄")

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
            item.setForeground(
                QColor(
                    self.mgr["accent"]
                    if is_arc
                    else (self.mgr["success"] if is_dir else self.mgr["text_primary"])
                )
            )
            self.file_list.addItem(item)

        has = len(self.source_paths) > 0
        self.file_list.setVisible(has)
        self.drop_zone.setVisible(not has)

        count = len(self.source_paths)
        if has:
            all_arc = all(is_archive(p) for p in self.source_paths)
            any_arc = any(is_archive(p) for p in self.source_paths)
            # Auto-hint based on content
            if all_arc:
                # Check if all can be extracted (some may need 7z)
                missing_7z = [
                    p for p in self.source_paths
                    if not get_capabilities(p)["can_extract"]
                ]
                if missing_7z:
                    self._set_status(
                        f"NEED 7-ZIP FOR {os.path.splitext(missing_7z[0])[1].upper()}",
                        self.mgr["danger"]
                    )
                else:
                    self._set_status(
                        f"↓  {count} ARCHIVE(S) — HIT EXTRACT",
                        self.mgr["success"]
                    )
            elif any_arc:
                self._set_status(
                    f"{count} ITEM(S) MIXED — CHOOSE ACTION",
                    self.mgr["text_secondary"]
                )
            else:
                self._set_status(f"↑  {count} FILE(S) — HIT COMPRESS", self.mgr["accent"])
        else:
            self._set_status("READY", self.mgr["text_secondary"])

    def _compress(self):
        if not self.source_paths:
            self._set_status("NO FILES SELECTED!", self.mgr["danger"])
            return
        dst = self.dst_input.text().strip()
        if not dst:
            dst = os.path.dirname(self.source_paths[0])

        fmt = self.fmt_combo.currentText()
        # Build the proper extension
        ext_map = {
            "zip": ".zip", "7z": ".7z", "tar": ".tar",
            "tar.gz": ".tar.gz", "tar.bz2": ".tar.bz2",
            "tar.xz": ".tar.xz", "gz": ".gz",
        }
        ext = ext_map.get(fmt, f".{fmt}")
        name = os.path.splitext(os.path.basename(self.source_paths[0]))[0]
        # strip any double extension like .tar
        if name.endswith(".tar"):
            name = name[:-4]
        if len(self.source_paths) > 1:
            name = "archive"
        out_path = os.path.join(dst, name + ext)

        self._set_busy(True)
        pwd = self.pwd_input.text().strip()
        level = self.combo_lvl.currentText() if hasattr(self, "combo_lvl") else "Normal"
        dict_sz = self.combo_dict.currentText() if hasattr(self, "combo_dict") else "16 MB"
        threads = self.combo_mt.currentText() if hasattr(self, "combo_mt") else "Auto"
        solid = self.chk_solid.isChecked() if hasattr(self, "chk_solid") else True

        def worker():
            errors = create_archive(
                self.source_paths,
                out_path,
                fmt,
                password=pwd,
                level=level,
                dict_size=dict_sz,
                threads=threads,
                solid=solid,
                on_progress=lambda done, total: self.progress_signal.emit(done, total),
            )
            self.done_signal.emit(errors, f"Created: {os.path.basename(out_path)}")

        threading.Thread(target=worker, daemon=True).start()

    def _extract(self):
        archives = [p for p in self.source_paths if is_archive(p)]
        if not archives:
            self._set_status("NO ARCHIVES SELECTED!", self.mgr["danger"])
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
            self._set_status("WORKING…", self.mgr["accent"])
            self.status_dot.setStyleSheet(
                f"color: {self.mgr['accent']}; font-size: 10px;"
            )

    def _on_progress(self, done, total):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self._set_status(f"PROCESSING… [{done}/{total}]", self.mgr["accent"])

    def _on_done(self, errors, message):
        self._set_busy(False)
        if errors:
            self._set_status(f"ERROR: {errors[0][:40]}...", self.mgr["danger"])
            self.status_dot.setStyleSheet(
                f"color: {self.mgr['danger']}; font-size: 10px;"
            )
        else:
            self._set_status(f"{message} ✓", self.mgr["success"])
            self.status_dot.setStyleSheet(
                f"color: {self.mgr['success']}; font-size: 10px;"
            )
            self.source_paths.clear()
            self._refresh_list()

        QTimer.singleShot(
            4000,
            lambda: (
                self._set_status("READY", self.mgr["text_secondary"]),
                self.status_dot.setStyleSheet(
                    f"color: {self.mgr['success']}; font-size: 10px;"
                ),
                self.progress.setVisible(False),
            ),
        )

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(f" {text}")
        self.status_lbl.setStyleSheet(
            f"font-family: 'JetBrains Mono','Consolas','Courier New'; "
            f"font-size: 11px; letter-spacing: 1px; color: {color};"
        )


def main():
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.archiver")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    mgr = ThemeManager()
    app.setPalette(mgr.get_palette())

    win = ArchiverWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
