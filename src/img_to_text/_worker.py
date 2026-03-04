"""Qt thread-pool OCR worker (QRunnable) used by both the overlay and dialog UIs."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal
from PyQt6.QtGui import QImage

from . import _settings as S
from .extractor import ocr_qimage_with_meta


class _Signals(QObject):
    success = pyqtSignal(object)
    error = pyqtSignal(str)


class OcrWorker(QRunnable):
    """Runs OCR in a background thread and emits ``signals.success`` or ``signals.error``."""

    def __init__(
        self,
        image: QImage,
        *,
        raw_output: bool = False,
        languages: list[str] | None = None,
        symbol_priority: bool = False,
        one_line_output: bool = False,
        code_fix: bool = False,
    ) -> None:
        super().__init__()
        self.image = image
        self.raw_output = raw_output
        self.languages = languages or list(S.ocr_langs)
        self.symbol_priority = symbol_priority
        self.one_line_output = one_line_output
        self.code_fix = code_fix
        self.signals = _Signals()

    def run(self) -> None:
        try:
            self.signals.success.emit(
                ocr_qimage_with_meta(
                    self.image,
                    languages=self.languages,
                    raw_output=self.raw_output,
                    symbol_priority=self.symbol_priority,
                    one_line_output=self.one_line_output,
                    code_fix=self.code_fix,
                )
            )
        except Exception as e:
            self.signals.error.emit(str(e).strip() or e.__class__.__name__)
