"""Nexus File Tools — File Ops & Archiver in one window.

Tabs:
  FILE OPS  — copy / move / delete with fast buffered I/O
  ARCHIVER  — 7-zip-powered compress / extract with full option control

Auto-detects what can be done when files are dropped (archives → extract,
regular files → compress). Requires 7-Zip for .7z / .rar / .iso / .zst etc.
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

from src.archiver.archiver import (
    _7Z_PATH,
    CREATABLE_FORMATS,
    MD_MAP,
    MT_MAP,
    MX_MAP,
    create_archive,
    detect_format,
    extract_archive,
    get_capabilities,
    is_archive,
)
from src.common.config import ARCHIVER_SETTINGS, FILE_OPS_SETTINGS, ICON_PATH
from src.common.theme import ThemeManager
from src.common.theme_template import TOOL_SHEET

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
        import math

        self._glow = (self._glow + 0.04) % (2 * math.pi)
        self.update()

    def paintEvent(self, _):
        import math

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

    # ── Settings ──────────────────────────────────────────────────────

    def _load_settings(self):
        import json

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
        import json

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
        self.status_dot.setStyleSheet(
            f"color: {self.mgr['success']}; font-size: 10px;"
        )
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
            ("combo_lvl",  "LEVEL",     list(MX_MAP.keys()), "Normal"),
            ("combo_dict", "DICT SIZE", list(MD_MAP.keys()), "16 MB"),
            ("combo_mt",   "THREADS",   list(MT_MAP.keys()), "Auto"),
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
            unextractable = [p for p in archives if not get_capabilities(p)["can_extract"]]

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
            "zip": ".zip", "7z": ".7z", "tar": ".tar",
            "tar.gz": ".tar.gz", "tar.bz2": ".tar.bz2",
            "tar.xz": ".tar.xz", "gz": ".gz",
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
                self.arc_sources, out_path, fmt,
                password=pwd, level=level, dict_size=dict_sz,
                threads=threads, solid=solid,
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
                        arc, out, password=pwd,
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
        self.status_dot.setStyleSheet(
            f"color: {self.mgr['success']}; font-size: 10px;"
        )


# ──────────────────────────────────────────────────────────────────────
# Entry point  (also used by archiver __main__.py)
# ──────────────────────────────────────────────────────────────────────


def main():
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "nexus.filetools"
        )
    import argparse

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


if __name__ == "__main__":
    main()
