"""
    Public API for img_to_text
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QMimeData, QPoint, QRect, QThreadPool, QTimer
from PyQt6.QtGui import QClipboard, QGuiApplication, QImage
from PyQt6.QtWidgets import QApplication, QFileDialog

from . import _settings as S
from ._capture import capture_virtual_desktop
from ._colors import C
from ._dialogs import ImageOcrDialog
from ._overlay import SnipOverlay
from ._settings import SnipRecord, recent_snips
from ._toast import OcrPreviewTooltip, Toast
from ._worker import OcrWorker

# ── Clipboard helpers ──────────────────────────────────────────────────────

def _copy_text(text: str) -> None:
    mime = QMimeData()
    mime.setText(text)
    QApplication.clipboard().setMimeData(mime, QClipboard.Mode.Clipboard)


def _copy_image(image: QImage) -> None:
    QApplication.clipboard().setImage(image)


def _save_image_dialog(image: QImage) -> bool:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path, _ = QFileDialog.getSaveFileName(
        None,
        "Save Snip",
        str(Path.home() / "Pictures" / f"snip_{ts}.png"),
        "Images (*.png *.jpg)",
    )
    if path:
        image.save(path)
        return True
    return False


def _share_image(image: QImage) -> None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        image.save(tmp.name)
        tmp_path = tmp.name
    import subprocess
    import sys

    if sys.platform == "linux":
        _copy_image(image)
        with contextlib.suppress(Exception):
            subprocess.Popen(["xdg-open", tmp_path])
    else:
        os.startfile(tmp_path)


def _open_in_editor(text: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="snip_", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(text)
    import sys

    if sys.platform == "win32":
        os.startfile(tmp.name)
    else:
        import subprocess

        with contextlib.suppress(Exception):
            subprocess.Popen(["xdg-open", tmp.name])


# ── Snip-to-text entry point ───────────────────────────────────────────────

def start_snip_to_text(
    *,
    nexus=None,
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    """Show the full-screen snip overlay; OCR result is copied to clipboard."""

    def _status(msg: str) -> None:
        if nexus is not None and hasattr(nexus, "status_lbl"):
            nexus.status_lbl.setText(msg)
            nexus.status_lbl.repaint()

    def _pool() -> QThreadPool:
        return (
            nexus.thread_pool
            if nexus and hasattr(nexus, "thread_pool")
            else QThreadPool.globalInstance()
        )

    def _handle(action: str, image: QImage, anchor: QPoint) -> None:
        if action == "cancel":
            return
        if action == "image":
            _copy_image(image)
            Toast.show_toast("Image Copied", "🖼️")
            return
        if action == "save":
            if _save_image_dialog(image):
                _status("✓ Saved")
                Toast.show_toast("Saved", "💾", C.SUCCESS)
            return
        if action == "share":
            _share_image(image)
            Toast.show_toast("Image Shared", "📤")
            return

        raw_mode = action == "text_raw"
        one_line_mode = action == "text_one_line"
        langs = ["en"] if S.ocr_code_mode else list(S.ocr_langs)
        symbol_mode = S.ocr_symbol_priority
        code_fix_mode = S.ocr_code_fix
        mode_label = "(code)" if S.ocr_code_mode else f"({'+'.join(langs)})"
        if symbol_mode:
            mode_label = f"{mode_label}+sym"
        if code_fix_mode:
            mode_label = f"{mode_label}+fix"
        _status(f"⏳ Recognising {mode_label}…")
        tip = OcrPreviewTooltip(anchor)
        tip.show()
        w = OcrWorker(
            image,
            raw_output=raw_mode,
            languages=langs,
            symbol_priority=symbol_mode,
            one_line_output=one_line_mode,
            code_fix=code_fix_mode,
        )

        def _ok(payload: object) -> None:
            if isinstance(payload, dict):
                text = str(payload.get("text", ""))
                confidence = float(payload.get("confidence", 0.0))
            else:
                text = str(payload or "")
                confidence = 0.0

            tip.set_text(text, confidence)
            if not text:
                _status("⚠️ No text")
                Toast.show_toast("No text", "⚠️", C.ERROR)
                return
            recent_snips.appendleft(SnipRecord(datetime.now(), text, image))
            _copy_text(text)
            if confidence > 0:
                _status(f"✓ Text copied ({int(confidence * 100)}%)")
            else:
                _status("✓ Text copied")
            Toast.show_toast("Text copied", "📋")

        w.signals.success.connect(_ok)
        w.signals.error.connect(
            lambda e: (
                tip.close(),
                _status(f"❌ {e}"),
                Toast.show_toast(f"Error: {e}", "❌", C.ERROR),
            )
        )
        _pool().start(w)

    def _on_taken(rect: QRect, action: str, overlay: SnipOverlay) -> None:
        img = overlay.crop_selection(rect)
        vgeo = (
            QGuiApplication.screens()[0].virtualGeometry()
            if QGuiApplication.screens()
            else QRect()
        )
        anchor = QPoint(rect.right() + vgeo.x(), rect.bottom() + vgeo.y())
        QTimer.singleShot(50, lambda: _handle(action, img, anchor))

    if nexus and hasattr(nexus, "hide"):
        nexus.hide()
    QTimer.singleShot(
        150,
        lambda: (
            data := capture_virtual_desktop(),
            ov := SnipOverlay(data[0], data[1]),
            ov.snip_taken.connect(lambda r, a: _on_taken(r, a, ov)),
            ov.show(),
            ov.raise_(),
            ov.activateWindow(),
            setattr(ov, "_ref", ov),
        ),
    )


def get_recent_snips() -> list[SnipRecord]:
    """Return up to the last 10 snip records (newest first)."""
    return list(recent_snips)


# ── File / paste OCR entry point ───────────────────────────────────────────

def start_file_to_text(*, nexus=None) -> ImageOcrDialog:
    """Open the Image OCR dialog (file-open / drag-drop / paste mode)."""
    dlg = ImageOcrDialog(nexus=nexus)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    dlg._ref = dlg  # keep alive
    return dlg
