"""Hash Tool — file & text hashing with integrity verification.

Features:
• Drag-and-drop file or type/paste text to hash instantly
• MD5 · SHA-1 · SHA-256 · SHA-512  (all shown simultaneously)
• Copy individual hashes with one click
• Verify: paste an expected hash → green ✓ / red ✗ indicator
• Large file hashing is done in a background thread (non-blocking)
• HMAC mode for keyed hashing
"""

import hashlib
import hmac
import os
import sys

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeyEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from src.common.config import ICON_PATH
except ImportError:
    ICON_PATH = ""

from src.common.theme import ThemeManager, WindowThemeBridge
from src.common.theme_template import TOOL_SHEET

CHUNK = 8 * 1024 * 1024  # 8 MB read chunks

_EXTRA = """
QTabWidget::pane {
    border: 1px solid {{border}};
    border-radius: 12px;
    background: {{bg_overlay}};
    top: -1px;
}
QTabBar::tab {
    background: {{bg_control}};
    color: {{text_secondary}};
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    border: 1px solid {{border}};
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 8px 20px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: {{bg_overlay}};
    color: {{accent}};
    border-color: {{border_focus}};
}
QTabBar::tab:hover:!selected {
    background: {{bg_control_hov}};
    color: {{text_primary}};
}
QFrame#drop_card {
    background: {{bg_overlay}};
    border: 2px dashed {{border_light}};
    border-radius: 14px;
    min-height: 120px;
}
QFrame#drop_card[active="true"] {
    border: 2px solid {{accent}};
    background: {{accent_subtle}};
}
QLabel#drop_hint {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 13px;
    letter-spacing: 1px;
    color: {{text_secondary}};
    background: transparent;
}
QLineEdit#input_text {
    background: {{bg_control}};
    border: 1px solid {{border}};
    border-radius: 10px;
    padding: 10px 14px;
    color: {{text_primary}};
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 12px;
    selection-background-color: {{accent_subtle}};
}
QLineEdit#input_text:focus { border: 1px solid {{border_focus}}; }
QLineEdit#hash_out {
    background: {{bg_elevated}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 8px 12px;
    color: {{text_primary}};
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
    selection-background-color: {{accent_subtle}};
}
QLineEdit#hash_out:read-only { color: {{text_secondary}}; }
QLineEdit#verify_in {
    background: {{bg_control}};
    border: 1px solid {{border}};
    border-radius: 8px;
    padding: 8px 12px;
    color: {{text_primary}};
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 11px;
}
QLineEdit#verify_in:focus { border: 1px solid {{border_focus}}; }
QLineEdit#verify_ok  { border: 1px solid {{success}}; color: {{success}}; }
QLineEdit#verify_err { border: 1px solid {{danger}};  color: {{danger}};  }
QPushButton#copy_btn {
    background: {{bg_control}};
    color: {{text_secondary}};
    border: 1px solid {{border}};
    border-radius: 6px;
    padding: 4px 10px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1px;
    min-width: 52px;
}
QPushButton#copy_btn:hover { background: {{bg_control_hov}}; color: {{accent}}; border: 1px solid {{border_focus}}; }
QPushButton#action_btn {
    background: {{accent}};
    color: {{text_on_accent}};
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton#action_btn:hover { background: {{accent_hover}}; }
QPushButton#action_btn:pressed { background: {{accent_pressed}}; }
QProgressBar {
    background: {{bg_control}};
    border: 1px solid {{border}};
    border-radius: 4px;
    height: 4px;
    text-align: center;
    color: transparent;
    font-size: 1px;
}
QProgressBar::chunk { background: {{accent}}; border-radius: 4px; }
QLabel#alg_label {
    font-family: 'JetBrains Mono','Consolas','Courier New';
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 3px;
    color: {{text_secondary}};
    min-width: 60px;
}
"""


# ── File hashing worker ───────────────────────────────────────────────────────


class FileHashWorker(QThread):
    result = pyqtSignal(dict)
    progress = pyqtSignal(int)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        try:
            size = os.path.getsize(self._path)
            algos = {
                "MD5": hashlib.md5(),
                "SHA-1": hashlib.sha1(),
                "SHA-256": hashlib.sha256(),
                "SHA-512": hashlib.sha512(),
            }
            done = 0
            with open(self._path, "rb") as f:
                while chunk := f.read(CHUNK):
                    for h in algos.values():
                        h.update(chunk)
                    done += len(chunk)
                    if size:
                        self.progress.emit(int(done * 100 / size))
            self.result.emit({k: v.hexdigest() for k, v in algos.items()})
        except Exception as e:
            self.result.emit({"error": str(e)})


# ── Hash row widget ───────────────────────────────────────────────────────────


class HashRow(QWidget):
    """Single algorithm label + result field + copy button."""

    def __init__(self, alg: str, parent=None):
        super().__init__(parent)
        self.alg = alg
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lbl = QLabel(alg)
        lbl.setObjectName("alg_label")
        lbl.setFixedWidth(70)
        lay.addWidget(lbl)

        self.field = QLineEdit()
        self.field.setObjectName("hash_out")
        self.field.setReadOnly(True)
        self.field.setPlaceholderText("—")
        lay.addWidget(self.field, stretch=1)

        self.copy_btn = QPushButton("COPY")
        self.copy_btn.setObjectName("copy_btn")
        self.copy_btn.clicked.connect(self._copy)
        lay.addWidget(self.copy_btn)

    def set_value(self, val: str):
        self.field.setReadOnly(False)
        self.field.setText(val)
        self.field.setObjectName("hash_out")
        self.field.setReadOnly(True)
        self.field.style().unpolish(self.field)
        self.field.style().polish(self.field)

    def _copy(self):
        txt = self.field.text()
        if txt:
            QApplication.clipboard().setText(txt)
            self.copy_btn.setText("✓")
            QTimer.singleShot(1400, lambda: self.copy_btn.setText("COPY"))

    def value(self) -> str:
        return self.field.text()


# ── Drop target ───────────────────────────────────────────────────────────────


class DropZone(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drop_card")
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl = QLabel("Drop a file here  ·  or browse below")
        self._lbl.setObjectName("drop_hint")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._lbl)

    def set_text(self, text: str):
        self._lbl.setText(text)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setProperty("active", "true")
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, e):
        self.setProperty("active", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, e: QDropEvent):
        self.setProperty("active", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isfile(path):
                self.file_dropped.emit(path)


# ── Main Window ───────────────────────────────────────────────────────────────


class HashTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self._mgr = ThemeManager()
        self._worker: FileHashWorker | None = None
        self._current_file = ""

        self.setWindowTitle("Hash Tool")
        if ICON_PATH and os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(680, 600)
        self.resize(760, 680)

        self._build_ui()
        self._apply_theme()
        self._mgr.theme_changed.connect(self._apply_theme)
        self._theme_bridge = WindowThemeBridge(self._mgr, self)  # Win32 titlebar + palette
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
        t = QLabel("HASH TOOL")
        t.setObjectName("title")
        s = QLabel("MD5 · SHA-1 · SHA-256 · SHA-512")
        s.setObjectName("sub")
        s.setAlignment(Qt.AlignmentFlag.AlignBottom)
        hdr.addWidget(t)
        hdr.addSpacing(10)
        hdr.addWidget(s)
        hdr.addStretch()
        out.addLayout(hdr)

        # Tabs
        tabs = QTabWidget()

        # ── File tab ──────────────────────────────────────────────────────────
        file_page = QWidget()
        flay = QVBoxLayout(file_page)
        flay.setContentsMargins(14, 14, 14, 14)
        flay.setSpacing(12)

        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._hash_file)
        self.drop_zone.setFixedHeight(110)
        flay.addWidget(self.drop_zone)

        # File path row
        path_row = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setObjectName("input_text")
        self.file_path.setPlaceholderText("  File path  (drag above or paste here)")
        self.file_path.returnPressed.connect(
            lambda: self._hash_file(self.file_path.text())
        )
        path_row.addWidget(self.file_path, stretch=1)
        browse_btn = QPushButton("BROWSE")
        browse_btn.setObjectName("action_btn")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        flay.addLayout(path_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(5)
        self.progress.setVisible(False)
        flay.addWidget(self.progress)

        # Hash rows (file)
        self.file_rows: dict[str, HashRow] = {}
        for alg in ("MD5", "SHA-1", "SHA-256", "SHA-512"):
            row = HashRow(alg)
            self.file_rows[alg] = row
            flay.addWidget(row)

        flay.addStretch()
        tabs.addTab(file_page, "FILE")

        # ── Text tab ──────────────────────────────────────────────────────────
        text_page = QWidget()
        tlay = QVBoxLayout(text_page)
        tlay.setContentsMargins(14, 14, 14, 14)
        tlay.setSpacing(12)

        lbl_in = QLabel("INPUT TEXT")
        lbl_in.setObjectName("section_label")
        tlay.addWidget(lbl_in)

        self.text_in = QLineEdit()
        self.text_in.setObjectName("input_text")
        self.text_in.setPlaceholderText("  Type or paste text here…")
        self.text_in.textChanged.connect(self._hash_text)
        tlay.addWidget(self.text_in)

        # HMAC key
        hmac_row = QHBoxLayout()
        hmac_lbl = QLabel("HMAC KEY (optional)")
        hmac_lbl.setObjectName("section_label")
        hmac_row.addWidget(hmac_lbl)
        hmac_row.addStretch()
        tlay.addLayout(hmac_row)

        self.hmac_key = QLineEdit()
        self.hmac_key.setObjectName("input_text")
        self.hmac_key.setPlaceholderText("  Leave empty for plain hash")
        self.hmac_key.textChanged.connect(self._hash_text)
        tlay.addWidget(self.hmac_key)

        # Hash rows (text)
        self.text_rows: dict[str, HashRow] = {}
        for alg in ("MD5", "SHA-1", "SHA-256", "SHA-512"):
            row = HashRow(alg)
            self.text_rows[alg] = row
            tlay.addWidget(row)

        tlay.addStretch()
        tabs.addTab(text_page, "TEXT")

        out.addWidget(tabs)

        # Verify section
        verify_frame = QFrame()
        verify_frame.setObjectName("card")
        vlay = QVBoxLayout(verify_frame)
        vlay.setContentsMargins(14, 10, 14, 10)
        vlay.setSpacing(6)
        vlbl = QLabel("VERIFY HASH")
        vlbl.setObjectName("section_label")
        vlay.addWidget(vlbl)
        self.verify_in = QLineEdit()
        self.verify_in.setObjectName("verify_in")
        self.verify_in.setPlaceholderText("  Paste expected hash here to compare…")
        self.verify_in.textChanged.connect(self._verify)
        vlay.addWidget(self.verify_in)
        self.verify_lbl = QLabel("")
        self.verify_lbl.setObjectName("status")
        vlay.addWidget(self.verify_lbl)
        out.addWidget(verify_frame)

    def _apply_theme(self):
        self._mgr.apply_to_widget(self, TOOL_SHEET + _EXTRA)

    # ── File hashing ──────────────────────────────────────────────────────────

    def _browse(self):
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self._hash_file(path)

    def _hash_file(self, path: str):
        path = path.strip().strip('"')
        if not os.path.isfile(path):
            self.drop_zone.set_text(f"✗  Not found: {os.path.basename(path)}")
            return
        self.file_path.setText(path)
        self._current_file = path
        size_mb = os.path.getsize(path) / 1024 / 1024
        self.drop_zone.set_text(
            f"⟳  Hashing: {os.path.basename(path)}  ({size_mb:.1f} MB)"
        )
        self.progress.setVisible(True)
        self.progress.setValue(0)
        for row in self.file_rows.values():
            row.set_value("…")

        if self._worker and self._worker.isRunning():
            self._worker.quit()
        self._worker = FileHashWorker(path, self)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.result.connect(self._on_file_hashed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_file_hashed(self, hashes: dict):
        self.progress.setVisible(False)
        if "error" in hashes:
            self.drop_zone.set_text(f"✗  Error: {hashes['error']}")
            return
        for alg, val in hashes.items():
            if alg in self.file_rows:
                self.file_rows[alg].set_value(val)
        name = os.path.basename(self._current_file)
        self.drop_zone.set_text(f"✓  {name}")
        self._verify()

    # ── Text hashing ──────────────────────────────────────────────────────────

    def _hash_text(self):
        text = self.text_in.text()
        key = self.hmac_key.text().encode()
        data = text.encode()
        algos = {
            "MD5": (hashlib.md5, "md5"),
            "SHA-1": (hashlib.sha1, "sha1"),
            "SHA-256": (hashlib.sha256, "sha256"),
            "SHA-512": (hashlib.sha512, "sha512"),
        }
        for alg, (fn, _name) in algos.items():
            h = hmac.new(key, data, fn).hexdigest() if key else fn(data).hexdigest()
            self.text_rows[alg].set_value(h)
        self._verify()

    # ── Verify ────────────────────────────────────────────────────────────────

    def _verify(self):
        expected = self.verify_in.text().strip().lower()
        if not expected:
            self.verify_lbl.setText("")
            self.verify_in.setObjectName("verify_in")
            self.verify_in.style().unpolish(self.verify_in)
            self.verify_in.style().polish(self.verify_in)
            return

        all_hashes: list[str] = []
        for rows in (self.file_rows, self.text_rows):
            for row in rows.values():
                all_hashes.append(row.value().lower())

        if expected in all_hashes:
            idx = all_hashes.index(expected)
            algs = ["MD5", "SHA-1", "SHA-256", "SHA-512"]
            matched_alg = algs[idx % 4]
            self.verify_lbl.setText(f"✓  MATCH — {matched_alg}")
            self.verify_lbl.setStyleSheet("color: #44FFB1; font-weight: 700;")
            self.verify_in.setObjectName("verify_ok")
        else:
            self.verify_lbl.setText("✗  No match")
            self.verify_lbl.setStyleSheet("color: #D95C5C; font-weight: 700;")
            self.verify_in.setObjectName("verify_err")
        self.verify_in.style().unpolish(self.verify_in)
        self.verify_in.style().polish(self.verify_in)

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(e)


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
    win = HashTool()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
