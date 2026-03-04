"""Image OCR dialog: drag-drop / paste / file-open image area and result view."""
from __future__ import annotations

import os
import urllib.parse
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QThreadPool, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.common.config import OCR_ICON_PATH
from src.common.theme import ThemeManager, apply_win32_titlebar

from . import _settings as S
from ._colors import C, _c_rgba
from ._overlay import LangBar
from ._toast import Toast
from ._worker import OcrWorker

# ── Upload button style ────────────────────────────────────────────────────

_UPLOAD_BTN_STYLE = """
QPushButton {{
    background: {bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 0 14px;
    font: 9pt 'Segoe UI';
}}
QPushButton:hover {{
    background: {hover};
    border-color: {hover};
    color: #fff;
}}
QPushButton:disabled {{
    background: {bg_dis};
    color: {fg_dis};
    border-color: {border_dis};
}}
"""


def _copy_text_to_clipboard(text: str) -> None:
    from PyQt6.QtCore import QMimeData
    from PyQt6.QtGui import QClipboard

    mime = QMimeData()
    mime.setText(text)
    QApplication.clipboard().setMimeData(mime, QClipboard.Mode.Clipboard)


# ── Drop / click image input area ─────────────────────────────────────────


class _DropImageArea(QLabel):
    """Click-to-open / drag-drop / paste image zone with live preview."""

    image_ready = pyqtSignal(QImage)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._current_image: QImage | None = None
        self._IDLE_STYLE = ""
        self._HOVER_STYLE = ""
        self._LOADED_STYLE = ""
        self._set_idle()

    # ------------------------------------------------------------------
    def _set_idle(self) -> None:
        self._current_image = None
        self.setText(
            "📂  Drop image here\n   or click to open file\n   or Ctrl+V to paste"
        )
        self.setStyleSheet(self._IDLE_STYLE)
        self.setPixmap(QPixmap())

    def set_image(self, image: QImage) -> None:
        self._current_image = image
        self._refresh_preview()
        self.setStyleSheet(self._LOADED_STYLE)

    def current_image(self) -> QImage | None:
        return self._current_image

    def _refresh_preview(self) -> None:
        if self._current_image is None:
            return
        avail = self.size() - QSize(20, 20)
        if avail.width() <= 0 or avail.height() <= 0:
            return
        pm = QPixmap.fromImage(self._current_image).scaled(
            avail,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pm)

    # ------------------------------------------------------------------
    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self._open_file_dialog()

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif *.webp)",
        )
        if not path:
            return
        img = QImage(path)
        if not img.isNull():
            self.set_image(img)
            self.image_ready.emit(img)

    # ------------------------------------------------------------------
    def dragEnterEvent(self, ev) -> None:
        md = ev.mimeData()
        if md.hasUrls() or md.hasImage():
            ev.acceptProposedAction()
            self.setStyleSheet(self._HOVER_STYLE)

    def dragLeaveEvent(self, ev) -> None:
        if self._current_image:
            self.setStyleSheet(self._LOADED_STYLE)
        else:
            self.setStyleSheet(self._IDLE_STYLE)

    def dragMoveEvent(self, ev) -> None:
        ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        md = ev.mimeData()
        img: QImage | None = None

        if md.hasUrls():
            for url in md.urls():
                local = url.toLocalFile()
                if local:
                    candidate = QImage(local)
                    if not candidate.isNull():
                        img = candidate
                        break

        if img is None and md.hasImage():
            raw = md.imageData()
            if raw:
                candidate = QImage(raw)
                if not candidate.isNull():
                    img = candidate

        if img:
            self.set_image(img)
            self.image_ready.emit(img)
            ev.acceptProposedAction()
        else:
            if self._current_image:
                self.setStyleSheet(self._LOADED_STYLE)
            else:
                self._set_idle()

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._refresh_preview()

    def _apply_theme(self) -> None:
        mgr = ThemeManager()
        bg_val = mgr["bg_overlay"] if mgr.is_dark else mgr["bg_elevated"]
        accent = mgr["accent"]
        text_dim = mgr["text_secondary"]
        border = mgr["border"]

        self._IDLE_STYLE = (
            f"background: {bg_val};"
            f" border: 2px dashed {border};"
            " border-radius: 10px;"
            f" color: {text_dim};"
            " font: 11pt 'Segoe UI';"
        )
        self._HOVER_STYLE = (
            f"background: {bg_val}; border: 2px solid {accent}; border-radius: 10px;"
        )
        self._LOADED_STYLE = (
            f"background: {mgr['bg_base']}; border: 2px solid {border};"
            " border-radius: 10px;"
        )
        if not self._current_image:
            self.setStyleSheet(self._IDLE_STYLE)
        else:
            self.setStyleSheet(self._LOADED_STYLE)
            self._refresh_preview()


# ── ImageOcrDialog ─────────────────────────────────────────────────────────


class ImageOcrDialog(QWidget):
    """Standalone OCR window — open any image file, drag-drop, or paste to extract text."""

    def __init__(self, *, nexus=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nexus = nexus
        self._current_image: QImage | None = None
        self._ocr_running = False

        self.setWindowTitle("Image → Text  (OCR)")
        if os.path.exists(OCR_ICON_PATH):
            self.setWindowIcon(QIcon(OCR_ICON_PATH))

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(980, 640)

        self._build_ui()
        self._apply_theme()

        ThemeManager().theme_changed.connect(self._apply_theme)

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        mgr = ThemeManager()
        apply_win32_titlebar(int(self.winId()), mgr["bg_base"], mgr.is_dark)

    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        mgr = ThemeManager()
        bg = mgr["bg_base"]
        text_col = mgr["text_primary"]
        text_sec = mgr["text_secondary"]
        border = mgr["border"]
        is_dark = mgr.is_dark

        ov_sm = _c_rgba(mgr, "text_primary", 15 if is_dark else 10)
        ov_md = _c_rgba(mgr, "text_primary", 25 if is_dark else 20)
        scrl = _c_rgba(mgr, "text_primary", 30 if is_dark else 40)
        scrl_h = _c_rgba(mgr, "text_primary", 60 if is_dark else 80)

        self.setStyleSheet(
            f"ImageOcrDialog {{ background: {bg}; color: {text_col}; }}"
            f"QLabel {{ background: transparent; color: {text_col}; }}"
        )
        apply_win32_titlebar(int(self.winId()), bg, is_dark)

        btn_bg = ov_sm
        btn_fg = text_sec
        btn_border = ov_md
        btn_dis_bg = _c_rgba(mgr, "text_primary", 8)
        btn_dis_fg = _c_rgba(mgr, "text_primary", 40)

        common_params = {
            "bg": btn_bg,
            "fg": btn_fg,
            "border": btn_border,
            "bg_dis": btn_dis_bg,
            "fg_dis": btn_dis_fg,
            "border_dis": btn_dis_bg,
        }

        self._open_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["accent"], **common_params)
        )
        self._paste_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["accent_pressed"], **common_params)
        )
        self._run_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["success"], **common_params)
        )
        self._copy_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["accent"], **common_params)
        )
        self._save_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["accent_pressed"], **common_params)
        )
        self._clear_btn.setStyleSheet(
            _UPLOAD_BTN_STYLE.format(hover=mgr["danger"], **common_params)
        )

        self._text_edit.setStyleSheet(
            f"QTextEdit {{"
            f" background: {ov_sm};"
            f" border: 1px solid {border};"
            f" border-radius: 8px;"
            f" color: {text_col}; font: 10pt 'Consolas', 'Courier New';"
            f" padding: 8px;"
            f"}}"
            f"QScrollBar:vertical {{ background: transparent; width: 6px; }}"
            f"QScrollBar::handle:vertical {{ background: {scrl}; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {scrl_h}; }}"
        )

        self._lang_bar.setStyleSheet(
            f"background: {mgr['bg_elevated']}; border-radius: 7px;"
            f" border: 1px solid {border};"
        )
        self._img_area._apply_theme()
        self._result_hdr.setStyleSheet(
            f"font: bold 9pt 'Segoe UI'; color: {mgr['text_secondary']};"
        )

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(10)

        # ── Top toolbar ──────────────────────────────────────────────
        tbar = QHBoxLayout()
        tbar.setSpacing(6)

        self._open_btn = QPushButton("📂  Open File")
        self._open_btn.setFixedHeight(32)
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self._open_file)

        self._paste_btn = QPushButton("📋  Paste  (Ctrl+V)")
        self._paste_btn.setFixedHeight(32)
        self._paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paste_btn.clicked.connect(self._paste_image)

        self._run_btn = QPushButton("▶  Run OCR")
        self._run_btn.setFixedHeight(32)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_ocr)

        self._lang_bar = LangBar(self)

        tbar.addWidget(self._open_btn)
        tbar.addWidget(self._paste_btn)
        tbar.addSpacing(8)
        tbar.addWidget(self._lang_bar)
        tbar.addStretch()
        tbar.addWidget(self._run_btn)
        root.addLayout(tbar)

        # ── Main split: image ◀ | ▶ text ────────────────────────────
        split = QHBoxLayout()
        split.setSpacing(12)

        self._img_area = _DropImageArea(self)
        self._img_area.image_ready.connect(self._on_image_loaded)
        split.addWidget(self._img_area, 1)

        right_root = QVBoxLayout()
        right_root.setSpacing(6)

        self._result_hdr = QLabel("Extracted Text")
        right_root.addWidget(self._result_hdr)

        self._text_edit = QTextEdit(self)
        self._text_edit.setPlaceholderText("OCR result will appear here…")
        self._text_edit.setMinimumWidth(300)
        right_root.addWidget(self._text_edit, 1)

        act_row = QHBoxLayout()
        act_row.setSpacing(6)

        self._copy_btn = QPushButton("📋  Copy Text")
        self._copy_btn.setFixedHeight(30)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(self._copy_text)

        self._save_btn = QPushButton("💾  Save Text")
        self._save_btn.setFixedHeight(30)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.clicked.connect(self._save_text)

        self._clear_btn = QPushButton("✕  Clear")
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_all)

        act_row.addWidget(self._copy_btn)
        act_row.addWidget(self._save_btn)
        act_row.addStretch()
        act_row.addWidget(self._clear_btn)
        right_root.addLayout(act_row)

        right_container = QWidget(self)
        right_container.setLayout(right_root)
        right_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        split.addWidget(right_container, 1)

        root.addLayout(split, 1)

        # ── Status bar ───────────────────────────────────────────────
        self._status = QLabel(
            "Open or drop an image to begin  ·  supports PNG, JPG, BMP, TIFF, WebP"
        )
        self._status.setStyleSheet(
            "color: rgba(255,255,255,0.28); font: 8pt 'Segoe UI';"
        )
        root.addWidget(self._status)

    # ------------------------------------------------------------------
    def keyPressEvent(self, ev) -> None:
        key, mods = ev.key(), ev.modifiers()
        ctrl = Qt.KeyboardModifier.ControlModifier
        if key == Qt.Key.Key_V and mods == ctrl:
            self._paste_image()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and mods == ctrl:
            self._run_ocr()
        elif key == Qt.Key.Key_O and mods == ctrl:
            self._open_file()
        else:
            super().keyPressEvent(ev)

    # ------------------------------------------------------------------
    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.repaint()

    def _open_file(self) -> None:
        self._img_area._open_file_dialog()

    def _paste_image(self) -> None:
        clipboard = QApplication.clipboard()
        md = clipboard.mimeData()
        img: QImage | None = None

        # 1. Direct image data
        if md.hasImage():
            cand = clipboard.image()
            if cand and not cand.isNull():
                img = cand

        # 2. File URLs / URI-list
        if (not img or img.isNull()) and (
            md.hasUrls() or md.hasFormat("text/uri-list")
        ):
            urls = list(md.urls())
            if not urls and md.hasFormat("text/uri-list"):
                raw_uris = bytes(md.data("text/uri-list")).decode("utf-8", "ignore")
                for line in raw_uris.splitlines():
                    if line.strip():
                        urls.append(QUrl(line.strip()))

            for url in urls:
                path = url.toLocalFile()
                if not path or not os.path.exists(path):
                    raw = url.toString()
                    for prefix in ("file:///", "file://", "file:"):
                        if raw.lower().startswith(prefix):
                            raw = raw[len(prefix):]
                            break
                    path = urllib.parse.unquote(raw)

                if path and os.path.exists(path) and os.path.isfile(path):
                    cand = QImage(path)
                    if not cand.isNull():
                        img = cand
                        break

        # 3. Plain text as path / file URI
        if (not img or img.isNull()) and md.hasText():
            for line in md.text().splitlines():
                text = line.strip().strip('"').strip("'")
                if not text:
                    continue
                if os.path.exists(text) and os.path.isfile(text):
                    cand = QImage(text)
                    if not cand.isNull():
                        img = cand
                        break
                if text.lower().startswith("file:"):
                    raw = text
                    for prefix in ("file:///", "file://", "file:"):
                        if raw.lower().startswith(prefix):
                            raw = raw[len(prefix):]
                            break
                    path = urllib.parse.unquote(raw)
                    if path and os.path.exists(path) and os.path.isfile(path):
                        cand = QImage(path)
                        if not cand.isNull():
                            img = cand
                            break

        if img and not img.isNull():
            if self._current_image is not None:
                res = QMessageBox.question(
                    self,
                    "Replace Image?",
                    "An image is already loaded. Do you want to replace it and clear the current OCR result?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if res != QMessageBox.StandardButton.Yes:
                    return
            self._img_area.set_image(img)
            self._on_image_loaded(img)
        else:
            Toast.show_toast("No image or valid file path in clipboard", "⚠️", C.WARNING)

    def _on_image_loaded(self, img: QImage) -> None:
        self._current_image = img
        self._run_btn.setEnabled(True)
        w, h = img.width(), img.height()
        self._set_status(f"Image loaded  ·  {w} × {h} px  ·  Ctrl+Enter to run OCR")
        self._run_ocr()

    def _run_ocr(self) -> None:
        if self._current_image is None or self._ocr_running:
            return
        self._ocr_running = True
        self._run_btn.setEnabled(False)

        langs = ["en"] if S.ocr_code_mode else list(S.ocr_langs)
        mode_label = "(code)" if S.ocr_code_mode else f"({'+'.join(langs)})"
        self._set_status(f"⏳  Recognising {mode_label}…")

        pool = (
            self._nexus.thread_pool
            if self._nexus and hasattr(self._nexus, "thread_pool")
            else QThreadPool.globalInstance()
        )
        worker = OcrWorker(
            self._current_image,
            languages=langs,
            symbol_priority=S.ocr_symbol_priority,
            code_fix=S.ocr_code_fix,
        )

        def _ok(payload: object) -> None:
            self._ocr_running = False
            self._run_btn.setEnabled(True)
            if isinstance(payload, dict):
                text = str(payload.get("text", ""))
                conf = float(payload.get("confidence", 0.0))
            else:
                text = str(payload or "")
                conf = 0.0
            self._text_edit.setPlainText(text)
            if text:
                conf_str = f"  ·  confidence {int(conf * 100)}%" if conf > 0 else ""
                self._set_status(
                    f"✓  OCR complete{conf_str}  ·  text copied to clipboard"
                )
                _copy_text_to_clipboard(text)
                Toast.show_toast("Text copied", "📋")
            else:
                self._set_status("⚠️  No text detected")
                Toast.show_toast("No text detected", "⚠️", C.WARNING)

        def _err(e: str) -> None:
            self._ocr_running = False
            self._run_btn.setEnabled(True)
            self._set_status(f"❌  {e}")
            Toast.show_toast(f"OCR error: {e}", "❌", C.ERROR)

        worker.signals.status.connect(self._set_status)
        worker.signals.success.connect(_ok)
        worker.signals.error.connect(_err)
        pool.start(worker)

    def _copy_text(self) -> None:
        text = self._text_edit.toPlainText()
        if text.strip():
            _copy_text_to_clipboard(text)
            Toast.show_toast("Text copied", "📋")
        else:
            Toast.show_toast("Nothing to copy", "⚠️", C.WARNING)

    def _save_text(self) -> None:
        text = self._text_edit.toPlainText()
        if not text.strip():
            Toast.show_toast("Nothing to save", "⚠️", C.WARNING)
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save OCR Text",
            str(Path.home() / f"ocr_{ts}.txt"),
            "Text files (*.txt);;All files (*)",
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            Toast.show_toast("Saved", "💾", C.SUCCESS)

    def _clear_all(self) -> None:
        self._current_image = None
        self._img_area.clear()
        self._img_area._set_idle()
        self._text_edit.clear()
        self._run_btn.setEnabled(False)
        self._set_status(
            "Open or drop an image to begin  ·  supports PNG, JPG, BMP, TIFF, WebP"
        )
