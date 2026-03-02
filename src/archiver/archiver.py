"""Nexus Archiver — backend + standalone window.

Formats supported:
  Python (always):  .zip  .tar  .tar.gz  .tar.bz2  .tar.xz  .gz
  7-Zip (if found): .7z   .zip(pw)  .rar  .iso  .cab  .wim  .arj  .lzh  .xz  .zst
"""

import json
import os
import sys
import threading
from pathlib import Path

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

from src.archiver.backend import (
    BACKEND as BACKEND,
)
from src.archiver.backend import (
    CREATABLE_FORMATS as CREATABLE_FORMATS,
)
from src.archiver.backend import (
    MD_MAP as MD_MAP,
)
from src.archiver.backend import (
    MT_MAP as MT_MAP,
)
from src.archiver.backend import (
    MX_MAP as MX_MAP,
)
from src.archiver.backend import (
    CreateOptions as CreateOptions,
)
from src.archiver.backend import (
    create_archive as create_archive,
)
from src.archiver.backend import (
    detect_format as detect_format,
)
from src.archiver.backend import (
    extract_archive as extract_archive,
)
from src.archiver.backend import (
    get_capabilities as get_capabilities,
)
from src.archiver.backend import (
    is_archive as is_archive,
)
from src.common.config import ARCHIVER_SETTINGS, ASSETS_DIR
from src.common.theme import ThemeManager
from src.common.theme_template import TOOL_SHEET

_7Z_PATH = BACKEND.seven_zip_path

ICON_PATH = os.path.join(ASSETS_DIR, "nexus_icon.png")


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
        self.backend = BACKEND
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
        self._set_status_dot(self.mgr["success"])
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

        if self.backend.has_7z:
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

        formats = [
            f for f in CREATABLE_FORMATS if f not in ("7z",) or self.backend.has_7z
        ]

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
            is_arc = self.backend.is_archive(p)
            is_dir = os.path.isdir(p)
            arc_fmt = self.backend.detect_format(p).upper() if is_arc else ""
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
            all_arc = all(self.backend.is_archive(p) for p in self.source_paths)
            any_arc = any(self.backend.is_archive(p) for p in self.source_paths)
            # Auto-hint based on content
            if all_arc:
                # Check if all can be extracted (some may need 7z)
                missing_7z = [
                    p
                    for p in self.source_paths
                    if not self.backend.get_capabilities(p).can_extract
                ]
                if missing_7z:
                    self._set_status(
                        f"NEED 7-ZIP FOR {os.path.splitext(missing_7z[0])[1].upper()}",
                        "danger",
                    )
                else:
                    self._set_status(f"↓  {count} ARCHIVE(S) — HIT EXTRACT", "success")
            elif any_arc:
                self._set_status(f"{count} ITEM(S) MIXED — CHOOSE ACTION", "secondary")
            else:
                self._set_status(f"↑  {count} FILE(S) — HIT COMPRESS", "accent")
        else:
            self._set_status("READY", "secondary")

    def _compress(self):
        if not self.source_paths:
            self._set_status("NO FILES SELECTED!", "danger")
            return
        first_source = Path(self.source_paths[0])
        dst = self.dst_input.text().strip()
        dst_path = Path(dst) if dst else first_source.parent

        fmt = self.fmt_combo.currentText()
        # Build the proper extension
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
        name = first_source.stem
        # strip any double extension like .tar
        if name.endswith(".tar"):
            name = name[:-4]
        if len(self.source_paths) > 1:
            name = "archive"
        out_path = str(dst_path / f"{name}{ext}")

        self._set_busy(True)
        pwd = self.pwd_input.text().strip()
        level = self.combo_lvl.currentText() if hasattr(self, "combo_lvl") else "Normal"
        dict_sz = (
            self.combo_dict.currentText() if hasattr(self, "combo_dict") else "16 MB"
        )
        threads = self.combo_mt.currentText() if hasattr(self, "combo_mt") else "Auto"
        solid = self.chk_solid.isChecked() if hasattr(self, "chk_solid") else True

        def worker():
            options = CreateOptions(
                fmt=fmt,
                password=pwd,
                level=level,
                dict_size=dict_sz,
                threads=threads,
                solid=solid,
            )
            errors = self.backend.create_archive(
                self.source_paths,
                out_path,
                options,
                on_progress=lambda done, total: self.progress_signal.emit(done, total),
            )
            self.done_signal.emit(errors, f"Created: {os.path.basename(out_path)}")

        threading.Thread(target=worker, daemon=True).start()

    def _extract(self):
        archives = [p for p in self.source_paths if self.backend.is_archive(p)]
        if not archives:
            self._set_status("NO ARCHIVES SELECTED!", "danger")
            return

        dst = self.dst_input.text().strip()
        pwd = self.pwd_input.text().strip()
        self._set_busy(True)

        def worker():
            all_errors = []
            for _idx, arc in enumerate(archives):
                out = dst or os.path.dirname(arc)
                errors = self.backend.extract_archive(
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
            self._set_status("WORKING…", "accent")

    def _on_progress(self, done, total):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self._set_status(f"PROCESSING… [{done}/{total}]", "accent")

    def _on_done(self, errors, message):
        self._set_busy(False)
        if errors:
            self._set_status(f"ERROR: {errors[0][:40]}...", "danger")
        else:
            self._set_status(f"{message} ✓", "success")
            self.source_paths.clear()
            self._refresh_list()

        QTimer.singleShot(
            4000,
            lambda: (
                self._set_status("READY", "secondary"),
                self._set_status_dot(self.mgr["success"]),
                self.progress.setVisible(False),
            ),
        )

    def _status_color(self, tone: str) -> str:
        tones = {
            "success": self.mgr["success"],
            "danger": self.mgr["danger"],
            "accent": self.mgr["accent"],
            "secondary": self.mgr["text_secondary"],
        }
        return tones.get(tone, self.mgr["text_secondary"])

    def _set_status_dot(self, color: str):
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 10px;")

    def _set_status(self, text: str, tone: str = "secondary"):
        color = self._status_color(tone)
        self.status_lbl.setText(f" {text}")
        self.status_lbl.setStyleSheet(
            f"font-family: 'JetBrains Mono','Consolas','Courier New'; "
            f"font-size: 11px; letter-spacing: 1px; color: {color};"
        )
        self._set_status_dot(color)


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
