"""Nexus File Tools — File Ops & Archiver in one window.

Tabs:
  FILE OPS  — copy / move / delete with fast buffered I/O
  ARCHIVER  — 7-zip-powered compress / extract with full option control

Auto-detects what can be done when files are dropped (archives → extract,
regular files → compress). Requires 7-Zip for .7z / .rar / .iso / .zst etc.
"""

import argparse
import ctypes
import gzip
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

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

from src.common.config import ARCHIVER_SETTINGS, FILE_OPS_SETTINGS, ICON_PATH
from src.common.theme import ThemeManager, WindowThemeBridge
from src.common.theme_template import TOOL_SHEET

# ──────────────────────────────────────────────────────────────────────
# Archive backend (formerly src/archiver/backend.py)
# ──────────────────────────────────────────────────────────────────────

# All extensions we can at least extract
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
    ".rar",
    ".iso",
    ".cab",
    ".wim",
    ".arj",
    ".lzh",
    ".xz",
    ".zst",
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
    "Store": "-mx0",
    "Fastest": "-mx1",
    "Fast": "-mx3",
    "Normal": "-mx5",
    "Maximum": "-mx7",
    "Ultra": "-mx9",
}

# Dictionary size → 7z -md flag
MD_MAP = {
    "256 KB": "-md256k",
    "1 MB": "-md1m",
    "4 MB": "-md4m",
    "16 MB": "-md16m",
    "32 MB": "-md32m",
    "64 MB": "-md64m",
    "128 MB": "-md128m",
    "256 MB": "-md256m",
    "512 MB": "-md512m",
    "1 GB": "-md1024m",
}

# Thread count → 7z -mmt flag
MT_MAP = {
    "Auto": "-mmt",
    "1": "-mmt1",
    "2": "-mmt2",
    "4": "-mmt4",
    "8": "-mmt8",
    "16": "-mmt16",
}


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class ArchiveCapabilities:
    fmt: str
    can_extract: bool
    can_create: bool
    needs_7z: bool
    supports_password: bool
    has_7z: bool

    def as_dict(self) -> dict:
        return {
            "fmt": self.fmt,
            "can_extract": self.can_extract,
            "can_create": self.can_create,
            "needs_7z": self.needs_7z,
            "supports_password": self.supports_password,
            "has_7z": self.has_7z,
        }


@dataclass(frozen=True)
class CreateOptions:
    fmt: str = "zip"
    password: str = ""
    level: str = "Normal"
    dict_size: str = "16 MB"
    threads: str = "Auto"
    solid: bool = True


class ArchiverBackend:
    def __init__(self):
        self._seven_zip_path = self.find_7z()

    @property
    def seven_zip_path(self) -> str | None:
        return self._seven_zip_path

    @property
    def has_7z(self) -> bool:
        return self._seven_zip_path is not None

    @staticmethod
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
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        return None

    @staticmethod
    def is_archive(path: str) -> bool:
        """Return True if path is a file format we can handle as an archive."""
        low = path.lower()
        return any(low.endswith(ext) for ext in ARCHIVE_EXTENSIONS)

    @staticmethod
    def detect_format(path: str) -> str:
        """Detect archive format string from filename."""
        low = path.lower()
        for ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"):
            if low.endswith(ext):
                return {"tgz": "tar.gz", "tbz2": "tar.bz2", "txz": "tar.xz"}.get(
                    ext.lstrip("."), ext.lstrip(".")
                )
        for ext in (
            ".7z",
            ".rar",
            ".iso",
            ".cab",
            ".wim",
            ".arj",
            ".lzh",
            ".zst",
            ".xz",
            ".zip",
            ".tar",
            ".gz",
        ):
            if low.endswith(ext):
                return ext.lstrip(".")
        return "zip"

    def get_capabilities(self, path: str) -> ArchiveCapabilities:
        """Return capabilities for an archive path."""
        fmt = self.detect_format(path)
        caps = FORMAT_CAPS.get(fmt, (False, False, False, False, False))
        ep, cp, e7, c7, pw = caps
        return ArchiveCapabilities(
            fmt=fmt,
            can_extract=ep or (e7 and self.has_7z),
            can_create=cp or (c7 and self.has_7z),
            needs_7z=not ep and e7,
            supports_password=pw and self.has_7z,
            has_7z=self.has_7z,
        )

    def list_archive_contents(self, archive_path: str) -> list[str]:
        """Return a list of member names inside an archive (best-effort)."""
        fmt = self.detect_format(archive_path)
        try:
            if fmt == "zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    return zf.namelist()
            if fmt.startswith("tar"):
                mode_map = {
                    "tar": "r:",
                    "tar.gz": "r:gz",
                    "tar.bz2": "r:bz2",
                    "tar.xz": "r:xz",
                }
                with tarfile.open(archive_path, mode_map.get(fmt, "r:*")) as tf:
                    return tf.getnames()
            if self._seven_zip_path:
                result = subprocess.run(
                    [self._seven_zip_path, "l", "-slt", archive_path],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                return re.findall(r"^Path = (.+)$", result.stdout, re.MULTILINE)[1:]
        except Exception:
            pass
        return []

    @staticmethod
    def _run_7z_with_progress(cmd: list[str], on_progress: ProgressCallback | None) -> str:
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
            match = re.search(r"\b(\d{1,3})%", line)
            if match and on_progress:
                on_progress(int(match.group(1)), 100)
        proc.wait()
        if proc.returncode != 0:
            return "".join(last_err[-10:]).strip() or "7z operation failed"
        return ""

    def extract_archive(
        self,
        archive_path: str,
        dest_dir: str,
        password: str = "",
        on_progress: ProgressCallback | None = None,
    ) -> list[str]:
        """Extract an archive. Returns list of errors (empty = success)."""
        errors: list[str] = []
        fmt = self.detect_format(archive_path)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            use_7z = (not FORMAT_CAPS.get(fmt, (False,))[0]) or (fmt == "7z")
            if use_7z:
                if not self._seven_zip_path:
                    return [
                        f"7-Zip not found — cannot extract .{fmt} files. Install 7-Zip."
                    ]
                cmd = [self._seven_zip_path, "x", archive_path, f"-o{dest_dir}", "-y"]
                if password:
                    cmd.append(f"-p{password}")
                err = self._run_7z_with_progress(cmd, on_progress)
                if err:
                    errors.append(err)
            elif fmt.startswith("tar"):
                mode_map = {
                    "tar": "r:",
                    "tar.gz": "r:gz",
                    "tar.bz2": "r:bz2",
                    "tar.xz": "r:xz",
                }
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
            else:
                pwd_bytes = password.encode() if password else None
                with zipfile.ZipFile(archive_path, "r") as zf:
                    members = zf.infolist()
                    total = len(members)
                    for i, member in enumerate(members):
                        try:
                            zf.extract(member, dest_dir, pwd=pwd_bytes)
                        except RuntimeError as exc:
                            if "password" in str(exc).lower():
                                errors.append("Invalid or missing password")
                                break
                            raise
                        if on_progress:
                            on_progress(i + 1, total)
        except Exception as exc:
            errors.append(str(exc))
        return errors

    @staticmethod
    def _collect_zip_files(sources: list[str]) -> list[tuple[str, str]]:
        all_files = []
        for src in sources:
            if os.path.isdir(src):
                for root, _, files in os.walk(src):
                    for file_name in files:
                        fp = os.path.join(root, file_name)
                        arcname = os.path.join(
                            os.path.basename(src),
                            os.path.relpath(fp, src),
                        )
                        all_files.append((fp, arcname))
            else:
                all_files.append((src, os.path.basename(src)))
        return all_files

    def create_archive(
        self,
        sources: list[str],
        output_path: str,
        options: CreateOptions,
        on_progress: ProgressCallback | None = None,
    ) -> list[str]:
        """Create an archive from source files/dirs. Returns errors."""
        errors: list[str] = []
        try:
            use_7z = options.fmt == "7z" or (options.fmt == "zip" and options.password)
            if use_7z:
                if not self._seven_zip_path:
                    return [
                        "7-Zip not found — install it to create .7z or encrypted .zip."
                    ]
                cmd = [self._seven_zip_path, "a", output_path] + sources
                cmd.append(MX_MAP.get(options.level, "-mx5"))
                if options.fmt == "7z":
                    if options.level != "Store":
                        cmd.append(MD_MAP.get(options.dict_size, "-md16m"))
                    cmd.append(MT_MAP.get(options.threads, "-mmt"))
                    cmd.append("-ms=on" if options.solid else "-ms=off")
                if options.password:
                    cmd.append(f"-p{options.password}")
                    if options.fmt == "7z":
                        cmd.append("-mhe=on")
                err = self._run_7z_with_progress(cmd, on_progress)
                if err:
                    errors.append(err)
            elif options.fmt.startswith("tar"):
                mode_map = {
                    "tar": "w:",
                    "tar.gz": "w:gz",
                    "tar.bz2": "w:bz2",
                    "tar.xz": "w:xz",
                }
                with tarfile.open(output_path, mode_map.get(options.fmt, "w:")) as tf:
                    for i, src in enumerate(sources):
                        tf.add(src, arcname=os.path.basename(src))
                        if on_progress:
                            on_progress(i + 1, len(sources))
            elif options.fmt == "gz":
                if len(sources) != 1 or os.path.isdir(sources[0]):
                    return [
                        "gzip only supports single files — use tar.gz for multiple files."
                    ]
                with open(sources[0], "rb") as fin, gzip.open(output_path, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                if on_progress:
                    on_progress(1, 1)
            else:
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    all_files = self._collect_zip_files(sources)
                    total = len(all_files)
                    for i, (fp, arcname) in enumerate(all_files):
                        zf.write(fp, arcname)
                        if on_progress:
                            on_progress(i + 1, total)
        except Exception as exc:
            errors.append(str(exc))
        return errors


BACKEND = ArchiverBackend()
_7Z_PATH = BACKEND.seven_zip_path


def is_archive(path: str) -> bool:
    return BACKEND.is_archive(path)


def detect_format(path: str) -> str:
    return BACKEND.detect_format(path)


def get_capabilities(path: str) -> dict:
    return BACKEND.get_capabilities(path).as_dict()


def list_archive_contents(archive_path: str) -> list[str]:
    return BACKEND.list_archive_contents(archive_path)


def extract_archive(
    archive_path: str,
    dest_dir: str,
    password: str = "",
    on_progress: ProgressCallback | None = None,
) -> list[str]:
    return BACKEND.extract_archive(archive_path, dest_dir, password, on_progress)


def create_archive(
    sources: list[str],
    output_path: str,
    fmt: str = "zip",
    password: str = "",
    level: str = "Normal",
    dict_size: str = "16 MB",
    threads: str = "Auto",
    solid: bool = True,
    on_progress: ProgressCallback | None = None,
) -> list[str]:
    options = CreateOptions(
        fmt=fmt,
        password=password,
        level=level,
        dict_size=dict_size,
        threads=threads,
        solid=solid,
    )
    return BACKEND.create_archive(sources, output_path, options, on_progress)


COPY_BUFFER = 8 * 1024 * 1024


# ──────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────


def fade_in(widget: QWidget, duration: int = 260):
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def fmt_size(sz: int) -> str:
    if sz > 1_000_000_000:
        return f"{sz / 1_000_000_000:.1f} GB"
    if sz > 1_000_000:
        return f"{sz / 1_000_000:.1f} MB"
    if sz > 1_000:
        return f"{sz / 1_000:.1f} KB"
    return f"{sz} B"


class GlowProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mgr = ThemeManager()
        self.setFixedHeight(4)
        self.setTextVisible(False)
        self._glow = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer.start(30)

    def _pulse(self):
        self._glow = (self._glow + 0.04) % (2 * math.pi)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.mgr["bg_overlay"]))
        track = QPainterPath()
        track.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 2, 2)
        p.drawPath(track)
        if self.maximum() > 0 and self.value() > 0:
            fill_w = int(r.width() * self.value() / self.maximum())
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0, QColor(self.mgr["accent"]))
            grad.setColorAt(1, QColor(self.mgr["success"]))
            p.setBrush(grad)
            chunk = QPainterPath()
            chunk.addRoundedRect(0, 0, fill_w, r.height(), 2, 2)
            p.drawPath(chunk)
            glow = QColor(self.mgr["accent"])
            glow.setAlpha(int(30 + 20 * math.sin(self._glow)))
            p.setBrush(glow)
            p.drawPath(chunk)
        p.end()


def make_divider() -> QFrame:
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


# ──────────────────────────────────────────────────────────────────────
# File Ops worker (threaded)
# ──────────────────────────────────────────────────────────────────────


def fast_copy(src: str, dst: str, cb=None):
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
        self.errors: list[str] = []

    def run(self):
        total = len(self.operations)
        for i, (op, src, dst) in enumerate(self.operations):
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


# ──────────────────────────────────────────────────────────────────────
# Main combined window
# ──────────────────────────────────────────────────────────────────────


class FileToolsWindow(QMainWindow):
    # File-ops signals
    _fo_progress = pyqtSignal(int, int, str)
    _fo_done = pyqtSignal(list)
    # Archiver signals
    _arc_progress = pyqtSignal(int, int)
    _arc_done = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        self.mgr = ThemeManager()

        self.setWindowTitle("NEXUS FILE TOOLS")
        self.setMinimumSize(720, 640)
        self.resize(760, 680)
        self.setAcceptDrops(True)

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        # State
        self._tab = "fileops"  # "fileops" | "archiver"
        self.fo_sources: list[str] = []
        self.arc_sources: list[str] = []
        self.source_paths: list[str] = []
        self._worker = None

        # Wire signals
        self._fo_progress.connect(self._fo_on_progress)
        self._fo_done.connect(self._fo_on_done)
        self._arc_progress.connect(self._arc_on_progress)
        self._arc_done.connect(self._arc_on_done)
        self.mgr.theme_changed.connect(self._apply_theme)

        self._build_ui()
        self._apply_theme()
        self._load_settings()
        self._switch_tab("fileops")
        self._theme_bridge = WindowThemeBridge(
            self.mgr, self
        )  # Win32 titlebar + palette

    # ── Settings ──────────────────────────────────────────────────────

    def _load_settings(self):
        for path, widget in [
            (FILE_OPS_SETTINGS, self.fo_dst_input),
            (ARCHIVER_SETTINGS, self.arc_dst_input),
        ]:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        widget.setText(json.load(f).get("last_dst", ""))
                except Exception:
                    pass

    def _save_settings(self):
        for path, widget in [
            (FILE_OPS_SETTINGS, self.fo_dst_input),
            (ARCHIVER_SETTINGS, self.arc_dst_input),
        ]:
            try:
                with open(path, "w") as f:
                    json.dump({"last_dst": widget.text()}, f)
            except Exception:
                pass

    # ── Theme ─────────────────────────────────────────────────────────

    def _apply_theme(self):
        extra = """
            QPushButton#tab_active {
                color: {{accent}};
                border-bottom: 2px solid {{accent}};
                background: transparent;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 3px;
                padding: 6px 18px;
                border-radius: 0;
            }
            QPushButton#tab_inactive {
                color: {{text_secondary}};
                border-bottom: 2px solid transparent;
                background: transparent;
                font-size: 11px;
                letter-spacing: 3px;
                padding: 6px 18px;
                border-radius: 0;
            }
            QPushButton#tab_inactive:hover {
                color: {{text_primary}};
                border-bottom: 2px solid {{border_light}};
            }
            QPushButton#btn_copy {
                color: {{success}};
                border: 1px solid {{success_border}};
                background: {{success_glow}};
            }
            QPushButton#btn_copy:hover { background: {{success_hover_glow}}; }
            QPushButton#btn_move {
                color: {{accent}};
                border: 1px solid {{accent_border}};
                background: {{accent_glow}};
            }
            QPushButton#btn_move:hover { background: {{accent_hover_glow}}; }
            QPushButton#btn_delete {
                color: {{danger}};
                border: 1px solid {{danger_border}};
                background: {{danger_glow}};
            }
            QPushButton#btn_delete:hover { background: {{danger_hover_glow}}; }
            QPushButton#btn_compress {
                color: {{accent}};
                border: 1px solid {{accent_border}};
                background: {{accent_glow}};
            }
            QPushButton#btn_compress:hover { background: {{accent_hover_glow}}; }
            QPushButton#btn_extract {
                color: {{success}};
                border: 1px solid {{success_border}};
                background: {{success_glow}};
            }
            QPushButton#btn_extract:hover { background: {{success_hover_glow}}; }
            QPushButton#btn_pwd_toggle {
                color: {{text_secondary}};
                background: transparent;
                border: none;
                padding: 0 6px;
                font-size: 12px;
            }
        """
        self.mgr.apply_to_widget(self, TOOL_SHEET + extra)
        self.status_dot.setStyleSheet(f"color: {self.mgr['success']}; font-size: 10px;")
        self.arc_opts_frame.setStyleSheet(
            f"background: {self.mgr['bg_overlay']}; border-radius: 10px;"
            f" border: 1px solid {self.mgr['border_light']};"
        )

    # ── UI construction ───────────────────────────────────────────────

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

        self._card_lay = QVBoxLayout(card)
        self._card_lay.setContentsMargins(28, 20, 28, 22)
        self._card_lay.setSpacing(0)

        self._build_header()
        self._card_lay.addWidget(make_divider())
        self._card_lay.addSpacing(4)

        # File Ops pane
        self._fo_pane = QWidget()
        fo_layout = QVBoxLayout(self._fo_pane)
        fo_layout.setContentsMargins(0, 0, 0, 0)
        fo_layout.setSpacing(14)
        self._build_fileops_pane(fo_layout)
        self._card_lay.addWidget(self._fo_pane)

        # Archiver pane
        self._arc_pane = QWidget()
        arc_layout = QVBoxLayout(self._arc_pane)
        arc_layout.setContentsMargins(0, 0, 0, 0)
        arc_layout.setSpacing(14)
        self._build_archiver_pane(arc_layout)
        self._card_lay.addWidget(self._arc_pane)

        # Shared progress bar at bottom
        self._card_lay.addStretch()
        self.progress = GlowProgressBar()
        self.progress.setVisible(False)
        self._card_lay.addWidget(self.progress)

    def _build_header(self):
        hdr = QHBoxLayout()
        hdr.setSpacing(0)
        hdr.setContentsMargins(0, 0, 0, 12)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        self.title_lbl = QLabel("NEXUS FILE TOOLS")
        self.title_lbl.setObjectName("title")
        self.sub_lbl = QLabel("FILE OPS · ARCHIVER")
        self.sub_lbl.setObjectName("sub")
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.sub_lbl)
        hdr.addLayout(title_col)
        hdr.addStretch()

        self.status_dot = QLabel("●")
        hdr.addWidget(self.status_dot)
        self.status_lbl = QLabel(" READY")
        self.status_lbl.setObjectName("status")
        hdr.addWidget(self.status_lbl)

        self._card_lay.addLayout(hdr)

        # Tab switcher row
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.setContentsMargins(0, 0, 0, 0)

        self.btn_tab_fo = QPushButton("FILE OPS")
        self.btn_tab_fo.clicked.connect(lambda: self._switch_tab("fileops"))
        self.btn_tab_fo.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_tab_arc = QPushButton("ARCHIVER")
        self.btn_tab_arc.clicked.connect(lambda: self._switch_tab("archiver"))
        self.btn_tab_arc.setCursor(Qt.CursorShape.PointingHandCursor)

        tab_row.addWidget(self.btn_tab_fo)
        tab_row.addWidget(self.btn_tab_arc)
        tab_row.addStretch()

        self._card_lay.addLayout(tab_row)
        self._card_lay.addSpacing(6)

    def _switch_tab(self, tab: str):
        self._tab = tab
        is_fo = tab == "fileops"
        self._fo_pane.setVisible(is_fo)
        self._arc_pane.setVisible(not is_fo)
        self.btn_tab_fo.setObjectName("tab_active" if is_fo else "tab_inactive")
        self.btn_tab_arc.setObjectName("tab_inactive" if is_fo else "tab_active")
        for btn in (self.btn_tab_fo, self.btn_tab_arc):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._set_status("READY", self.mgr["text_secondary"])

    # ── File Ops pane ──────────────────────────────────────────────────

    def _build_fileops_pane(self, lay: QVBoxLayout):
        ql = QLabel("QUEUE")
        ql.setObjectName("section_label")
        lay.addWidget(ql)

        self.fo_drop_zone = QLabel("DROP FILES OR FOLDERS HERE")
        self.fo_drop_zone.setObjectName("drop_zone")
        self.fo_drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fo_drop_zone.setMinimumHeight(120)
        self.fo_drop_zone.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.fo_drop_zone)

        self.fo_file_list = QListWidget()
        self.fo_file_list.setVisible(False)
        self.fo_file_list.setMinimumHeight(120)
        self.fo_file_list.setMaximumHeight(190)
        lay.addWidget(self.fo_file_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_add = QPushButton("+ ADD FILES")
        btn_add.clicked.connect(self._fo_add_files)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_folder = QPushButton("+ FOLDER")
        btn_folder.clicked.connect(self._fo_add_folder)
        btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear = QPushButton("CLEAR")
        btn_clear.clicked.connect(self._fo_clear)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_folder)
        btn_row.addStretch()
        btn_row.addWidget(btn_clear)
        lay.addLayout(btn_row)

        lay.addWidget(make_divider())

        dl = QLabel("DESTINATION")
        dl.setObjectName("section_label")
        lay.addWidget(dl)

        dst_row = QHBoxLayout()
        dst_row.setSpacing(8)
        self.fo_dst_input = QLineEdit()
        self.fo_dst_input.setPlaceholderText("select destination folder…")
        dst_row.addWidget(self.fo_dst_input, stretch=1)
        btn_browse = QPushButton("BROWSE")
        btn_browse.clicked.connect(self._fo_browse_dst)
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        dst_row.addWidget(btn_browse)
        lay.addLayout(dst_row)

        lay.addWidget(make_divider())

        ops_row = QHBoxLayout()
        ops_row.setSpacing(8)
        ops_row.addStretch()
        for label, name, op in [
            ("COPY", "btn_copy", "copy"),
            ("MOVE", "btn_move", "move"),
            ("DELETE", "btn_delete", "delete"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName(name)
            btn.setFixedHeight(38)
            btn.setMinimumWidth(100)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, o=op: self._fo_run(o))
            setattr(self, name, btn)
            ops_row.addWidget(btn)
        lay.addLayout(ops_row)

    # ── Archiver pane ──────────────────────────────────────────────────

    def _build_archiver_pane(self, lay: QVBoxLayout):
        ql = QLabel("QUEUE")
        ql.setObjectName("section_label")
        lay.addWidget(ql)

        self.arc_drop_zone = QLabel(
            "DROP ARCHIVES TO EXTRACT  ·  OR FILES / FOLDERS TO COMPRESS"
        )
        self.arc_drop_zone.setObjectName("drop_zone")
        self.arc_drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.arc_drop_zone.setMinimumHeight(120)
        self.arc_drop_zone.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.arc_drop_zone)

        self.arc_file_list = QListWidget()
        self.arc_file_list.setVisible(False)
        self.arc_file_list.setMinimumHeight(120)
        self.arc_file_list.setMaximumHeight(190)
        lay.addWidget(self.arc_file_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_add = QPushButton("+ ADD")
        btn_add.clicked.connect(self._arc_add)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear = QPushButton("CLEAR")
        btn_clear.clicked.connect(self._arc_clear)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(btn_add)
        btn_row.addStretch()

        self.arc_pwd_input = QLineEdit()
        self.arc_pwd_input.setPlaceholderText("PASSWORD (optional)")
        self.arc_pwd_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.arc_pwd_input.setFixedWidth(160)
        btn_row.addWidget(self.arc_pwd_input)

        btn_pwd_toggle = QPushButton("👁")
        btn_pwd_toggle.setObjectName("btn_pwd_toggle")
        btn_pwd_toggle.setFixedWidth(28)
        btn_pwd_toggle.setCheckable(True)
        btn_pwd_toggle.toggled.connect(
            lambda checked: self.arc_pwd_input.setEchoMode(
                QLineEdit.EchoMode.Normal
                if checked
                else QLineEdit.EchoMode.PasswordEchoOnEdit
            )
        )
        btn_row.addWidget(btn_pwd_toggle)
        btn_row.addWidget(btn_clear)
        lay.addLayout(btn_row)

        lay.addWidget(make_divider())

        ol = QLabel("OUTPUT FOLDER")
        ol.setObjectName("section_label")
        lay.addWidget(ol)

        dst_row = QHBoxLayout()
        dst_row.setSpacing(8)
        self.arc_dst_input = QLineEdit()
        self.arc_dst_input.setPlaceholderText("blank = same directory as source")
        dst_row.addWidget(self.arc_dst_input, stretch=1)
        btn_browse = QPushButton("BROWSE")
        btn_browse.clicked.connect(self._arc_browse_dst)
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        dst_row.addWidget(btn_browse)
        lay.addLayout(dst_row)

        lay.addWidget(make_divider())

        # Advanced options (collapsible)
        opts_header = QHBoxLayout()
        opts_lbl = QLabel("OPTIONS")
        opts_lbl.setObjectName("section_label")
        opts_header.addWidget(opts_lbl)
        opts_header.addStretch()
        self.btn_opts_toggle = QPushButton("⚙ ADVANCED")
        self.btn_opts_toggle.setFixedHeight(22)
        self.btn_opts_toggle.setStyleSheet("font-size: 8px; padding: 0 10px;")
        self.btn_opts_toggle.setCheckable(True)
        self.btn_opts_toggle.clicked.connect(
            lambda: self.arc_opts_frame.setVisible(self.btn_opts_toggle.isChecked())
        )
        opts_header.addWidget(self.btn_opts_toggle)
        lay.addLayout(opts_header)

        self.arc_opts_frame = QFrame()
        self.arc_opts_frame.setVisible(False)
        opts_lay = QHBoxLayout(self.arc_opts_frame)
        opts_lay.setContentsMargins(14, 10, 14, 10)
        opts_lay.setSpacing(16)

        for attr, label, items, default in [
            ("combo_lvl", "LEVEL", list(MX_MAP.keys()), "Normal"),
            ("combo_dict", "DICT SIZE", list(MD_MAP.keys()), "16 MB"),
            ("combo_mt", "THREADS", list(MT_MAP.keys()), "Auto"),
        ]:
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName("section_label")
            col.addWidget(lbl)
            combo = QComboBox()
            combo.addItems(items)
            combo.setCurrentText(default)
            col.addWidget(combo)
            setattr(self, attr, combo)
            opts_lay.addLayout(col)

        solid_col = QVBoxLayout()
        solid_lbl = QLabel("SOLID")
        solid_lbl.setObjectName("section_label")
        solid_col.addWidget(solid_lbl)
        self.chk_solid = QCheckBox("Solid archive")
        self.chk_solid.setChecked(True)
        solid_col.addWidget(self.chk_solid)
        opts_lay.addLayout(solid_col)
        lay.addWidget(self.arc_opts_frame)

        # Format selector + action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.arc_fmt_combo = QComboBox()
        for f in CREATABLE_FORMATS:
            if f != "7z" or _7Z_PATH:
                self.arc_fmt_combo.addItem(f)
        self.arc_fmt_combo.setFixedWidth(110)
        action_row.addWidget(self.arc_fmt_combo)
        action_row.addStretch()

        self.btn_compress = QPushButton("COMPRESS")
        self.btn_compress.setObjectName("btn_compress")
        self.btn_compress.setFixedHeight(38)
        self.btn_compress.setMinimumWidth(120)
        self.btn_compress.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_compress.clicked.connect(self._arc_compress)
        action_row.addWidget(self.btn_compress)

        self.btn_extract = QPushButton("EXTRACT")
        self.btn_extract.setObjectName("btn_extract")
        self.btn_extract.setFixedHeight(38)
        self.btn_extract.setMinimumWidth(120)
        self.btn_extract.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_extract.clicked.connect(self._arc_extract)
        action_row.addWidget(self.btn_extract)

        lay.addLayout(action_row)

    # ── Drag & Drop (dispatches to active tab) ─────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            dz = self.fo_drop_zone if self._tab == "fileops" else self.arc_drop_zone
            dz.setProperty("active", "true")
            dz.style().polish(dz)

    def dragLeaveEvent(self, _):
        for dz in (self.fo_drop_zone, self.arc_drop_zone):
            dz.setProperty("active", "false")
            dz.style().polish(dz)

    def dropEvent(self, event: QDropEvent):
        for dz in (self.fo_drop_zone, self.arc_drop_zone):
            dz.setProperty("active", "false")
            dz.style().polish(dz)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if self._tab == "fileops":
            for p in paths:
                if p not in self.fo_sources:
                    self.fo_sources.append(p)
            self._fo_refresh()
        else:
            for p in paths:
                if p not in self.arc_sources:
                    self.arc_sources.append(p)
            self._arc_refresh()

    # ── File Ops actions ──────────────────────────────────────────────

    def _fo_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Files")
        for p in paths:
            if p not in self.fo_sources:
                self.fo_sources.append(p)
        if paths:
            self._fo_refresh()

    def _fo_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder and folder not in self.fo_sources:
            self.fo_sources.append(folder)
            self._fo_refresh()

    def _fo_browse_dst(self):
        folder = QFileDialog.getExistingDirectory(self, "Destination")
        if folder:
            self.fo_dst_input.setText(folder)
            self._save_settings()

    def _fo_clear(self):
        self.fo_sources.clear()
        self._fo_refresh()

    def _fo_refresh(self):
        self.fo_file_list.clear()
        for p in self.fo_sources:
            is_dir = os.path.isdir(p)
            icon = "▸ DIR" if is_dir else "  FILE"
            size = f"  {fmt_size(os.path.getsize(p))}" if os.path.isfile(p) else ""
            item = QListWidgetItem(f"{icon}   {os.path.basename(p)}{size}")
            item.setForeground(
                QColor(self.mgr["accent"] if is_dir else self.mgr["text_primary"])
            )
            self.fo_file_list.addItem(item)
        has = bool(self.fo_sources)
        self.fo_file_list.setVisible(has)
        self.fo_drop_zone.setVisible(not has)
        n = len(self.fo_sources)
        self._set_status(
            f"{n} ITEM{'S' if n != 1 else ''} QUEUED" if has else "READY",
            self.mgr["text_secondary"],
        )

    def _refresh_list(self):
        """Compat for external callers expecting source_paths + _refresh_list."""
        if self.source_paths:
            self.fo_sources = list(self.source_paths)
            self.arc_sources = list(self.source_paths)
        self._fo_refresh()
        self._arc_refresh()

    def _fo_run(self, op: str):
        if not self.fo_sources:
            self._set_status("NO FILES SELECTED", self.mgr["danger"])
            return
        dst = self.fo_dst_input.text().strip()
        if op != "delete" and not dst:
            self._set_status("SELECT A DESTINATION FIRST", self.mgr["danger"])
            return
        ops = []
        for src in self.fo_sources:
            if op == "delete":
                ops.append(("delete", src, ""))
            else:
                ops.append((op, src, os.path.join(dst, os.path.basename(src))))
        self.progress.setMaximum(len(ops))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        for nm in ("btn_copy", "btn_move", "btn_delete"):
            getattr(self, nm).setEnabled(False)
        self._set_status("WORKING…", self.mgr["accent"])
        self.status_dot.setStyleSheet(f"color: {self.mgr['accent']}; font-size: 10px;")
        self._worker = FileOpsWorker(
            ops,
            on_progress=lambda d, t, n: self._fo_progress.emit(d, t, n),
            on_done=lambda errs: self._fo_done.emit(errs),
        )
        self._worker.start()

    def _fo_on_progress(self, done, total, name):
        self.progress.setValue(done)
        self._set_status(f"{name}  [{done}/{total}]", self.mgr["accent"])

    def _fo_on_done(self, errors):
        for nm in ("btn_copy", "btn_move", "btn_delete"):
            getattr(self, nm).setEnabled(True)
        if errors:
            self._set_status(
                f"{len(errors)} ERROR(S) — CHECK PERMISSIONS", self.mgr["danger"]
            )
            self.status_dot.setStyleSheet(
                f"color: {self.mgr['danger']}; font-size: 10px;"
            )
        else:
            self._set_status("ALL DONE ✓", self.mgr["success"])
            self.status_dot.setStyleSheet(
                f"color: {self.mgr['success']}; font-size: 10px;"
            )
            self.fo_sources.clear()
            self._fo_refresh()
        QTimer.singleShot(2800, lambda: self.progress.setVisible(False))
        QTimer.singleShot(4000, self._reset_status)

    # ── Archiver actions ──────────────────────────────────────────────

    def _arc_add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Files or Archives")
        for p in paths:
            if p not in self.arc_sources:
                self.arc_sources.append(p)
        if not paths:
            folder = QFileDialog.getExistingDirectory(self, "Select Folder")
            if folder and folder not in self.arc_sources:
                self.arc_sources.append(folder)
        self._arc_refresh()

    def _arc_browse_dst(self):
        folder = QFileDialog.getExistingDirectory(self, "Output Folder")
        if folder:
            self.arc_dst_input.setText(folder)
            self._save_settings()

    def _arc_clear(self):
        self.arc_sources.clear()
        self._arc_refresh()

    def _arc_refresh(self):
        self.arc_file_list.clear()
        for p in self.arc_sources:
            is_arc = is_archive(p)
            is_dir = os.path.isdir(p)
            caps = get_capabilities(p) if is_arc else {}
            arc_fmt = detect_format(p).upper() if is_arc else ""
            badge = ""
            if is_arc:
                if not caps.get("can_extract", False):
                    badge = " ⚠ NEEDS 7Z"
                elif caps.get("needs_7z", False):
                    badge = " [7Z]"
            icon = f"📦 {arc_fmt}" if is_arc else ("📁" if is_dir else "📄")
            size = f"  {fmt_size(os.path.getsize(p))}" if os.path.isfile(p) else ""
            item = QListWidgetItem(f"{icon}   {os.path.basename(p)}{size}{badge}")
            color = (
                self.mgr["danger"]
                if "⚠" in badge
                else (
                    self.mgr["accent"]
                    if is_arc
                    else (self.mgr["success"] if is_dir else self.mgr["text_primary"])
                )
            )
            item.setForeground(QColor(color))
            self.arc_file_list.addItem(item)

        has = bool(self.arc_sources)
        self.arc_file_list.setVisible(has)
        self.arc_drop_zone.setVisible(not has)
        n = len(self.arc_sources)

        if has:
            archives = [p for p in self.arc_sources if is_archive(p)]
            non_arcs = [p for p in self.arc_sources if not is_archive(p)]
            unextractable = [
                p for p in archives if not get_capabilities(p)["can_extract"]
            ]

            if unextractable:
                self._set_status(
                    f"⚠  NEED 7-ZIP FOR {detect_format(unextractable[0]).upper()}",
                    self.mgr["danger"],
                )
            elif non_arcs and not archives:
                self._set_status(
                    f"↑  {n} FILE(S) — READY TO COMPRESS", self.mgr["accent"]
                )
            elif archives and not non_arcs:
                self._set_status(
                    f"↓  {n} ARCHIVE(S) — READY TO EXTRACT", self.mgr["success"]
                )
            else:
                self._set_status(
                    f"{n} ITEMS MIXED  ({len(archives)} arc · {len(non_arcs)} file)",
                    self.mgr["text_secondary"],
                )
        else:
            self._set_status("READY", self.mgr["text_secondary"])

    def _arc_compress(self):
        if not self.arc_sources:
            self._set_status("NO FILES SELECTED!", self.mgr["danger"])
            return
        dst = self.arc_dst_input.text().strip() or os.path.dirname(self.arc_sources[0])
        fmt = self.arc_fmt_combo.currentText()
        ext_map = {
            "zip": ".zip",
            "7z": ".7z",
            "tar": ".tar",
            "tar.gz": ".tar.gz",
            "tar.bz2": ".tar.bz2",
            "tar.xz": ".tar.xz",
            "gz": ".gz",
        }
        ext = ext_map.get(fmt, f".{fmt}")
        base = os.path.splitext(os.path.basename(self.arc_sources[0]))[0]
        if base.endswith(".tar"):
            base = base[:-4]
        name = "archive" if len(self.arc_sources) > 1 else base
        out_path = os.path.join(dst, name + ext)

        self._arc_set_busy(True)
        pwd = self.arc_pwd_input.text().strip()
        level = self.combo_lvl.currentText()
        dict_sz = self.combo_dict.currentText()
        threads = self.combo_mt.currentText()
        solid = self.chk_solid.isChecked()

        def worker():
            errors = create_archive(
                self.arc_sources,
                out_path,
                fmt,
                password=pwd,
                level=level,
                dict_size=dict_sz,
                threads=threads,
                solid=solid,
                on_progress=lambda d, t: self._arc_progress.emit(d, t),
            )
            self._arc_done.emit(errors, f"Created: {os.path.basename(out_path)}")

        threading.Thread(target=worker, daemon=True).start()

    def _arc_extract(self):
        archives = [p for p in self.arc_sources if is_archive(p)]
        if not archives:
            self._set_status("NO ARCHIVES IN QUEUE!", self.mgr["danger"])
            return
        bad = [p for p in archives if not get_capabilities(p)["can_extract"]]
        if bad:
            self._set_status(
                f"Cannot extract {detect_format(bad[0]).upper()} — install 7-Zip",
                self.mgr["danger"],
            )
            return

        dst = self.arc_dst_input.text().strip()
        pwd = self.arc_pwd_input.text().strip()
        self._arc_set_busy(True)

        def worker():
            all_errors: list[str] = []
            for arc in archives:
                out = dst or os.path.dirname(arc)
                all_errors.extend(
                    extract_archive(
                        arc,
                        out,
                        password=pwd,
                        on_progress=lambda d, t: self._arc_progress.emit(d, t),
                    )
                )
            self._arc_done.emit(all_errors, f"Extracted {len(archives)} archive(s)")

        threading.Thread(target=worker, daemon=True).start()

    def _arc_set_busy(self, busy: bool):
        self.progress.setVisible(busy)
        self.progress.setValue(0)
        self.btn_compress.setEnabled(not busy)
        self.btn_extract.setEnabled(not busy)
        if busy:
            self._set_status("WORKING…", self.mgr["accent"])
            self.status_dot.setStyleSheet(
                f"color: {self.mgr['accent']}; font-size: 10px;"
            )

    def _arc_on_progress(self, done, total):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self._set_status(f"PROCESSING… [{done}/{total}]", self.mgr["accent"])

    def _arc_on_done(self, errors, message):
        self._arc_set_busy(False)
        if errors:
            self._set_status(f"ERROR: {errors[0][:50]}", self.mgr["danger"])
            self.status_dot.setStyleSheet(
                f"color: {self.mgr['danger']}; font-size: 10px;"
            )
        else:
            self._set_status(f"{message} ✓", self.mgr["success"])
            self.status_dot.setStyleSheet(
                f"color: {self.mgr['success']}; font-size: 10px;"
            )
            self.arc_sources.clear()
            self._arc_refresh()
        QTimer.singleShot(2800, lambda: self.progress.setVisible(False))
        QTimer.singleShot(4000, self._reset_status)

    # ── Shared status helpers ──────────────────────────────────────────

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(f" {text}")
        self.status_lbl.setStyleSheet(
            "font-family: 'JetBrains Mono','Consolas','Courier New';"
            f" font-size: 11px; letter-spacing: 1px; color: {color};"
        )

    def _reset_status(self):
        self._set_status("READY", self.mgr["text_secondary"])
        self.status_dot.setStyleSheet(f"color: {self.mgr['success']}; font-size: 10px;")


# ──────────────────────────────────────────────────────────────────────
# Entry point  (also used by archiver __main__.py)
# ──────────────────────────────────────────────────────────────────────


def main():
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.filetools")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tab",
        choices=["fileops", "archiver"],
        default="fileops",
        help="Which tab to open on launch",
    )
    args, _ = parser.parse_known_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    mgr = ThemeManager()
    app.setPalette(mgr.get_palette())
    win = FileToolsWindow()
    if args.tab != "fileops":
        win._switch_tab(args.tab)
    win.show()
    sys.exit(app.exec())


def main_archiver():
    """Entry point that opens directly on the Archiver tab."""
    sys.argv += ["--tab", "archiver"]
    main()


if __name__ == "__main__":
    main()
