from __future__ import annotations

import json

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from .algorithms import ALGORITHM_TIPS, ALGORITHMS, extract_keywords, summarize


class _Worker(QThread):
    done = pyqtSignal(str, list, list)   # summary, indices, keywords

    def __init__(self, text: str, ratio: float, algo: str):
        super().__init__()
        self._text  = text
        self._ratio = ratio
        self._algo  = algo

    def run(self):
        summary, indices = summarize(self._text, self._ratio, self._algo)
        keywords = extract_keywords(self._text, top_n=24)
        self.done.emit(summary, indices, keywords)


class Bridge(QObject):
    """JS \u2194 Python bridge for Text Summarizer."""

    # Signals consumed by JS
    summaryReady  = pyqtSignal(str)          # JSON payload \u2192 result
    themeChanged  = pyqtSignal(str)          # JSON color map
    findResult    = pyqtSignal(int, int)     # (current, total)

    # Signals consumed by Python
    findRequest   = pyqtSignal(str, bool)    # (text, forward)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _Worker | None = None

    @pyqtSlot(str, float, str)
    def runSummarize(self, text: str, ratio: float, algo: str):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
        self._worker = _Worker(text, ratio, algo)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, summary: str, indices: list, keywords: list):
        payload = json.dumps({
            "summary":  summary,
            "indices":  indices,
            "keywords": keywords,
        })
        self.summaryReady.emit(payload)

    @pyqtSlot(str)
    def copyText(self, text: str):
        QApplication.clipboard().setText(text)

    @pyqtSlot(str, bool)
    def findText(self, text: str, forward: bool = True):
        self.findRequest.emit(text, forward)

    @pyqtSlot(result=str)
    def getAlgorithms(self) -> str:
        return json.dumps([
            {"id": k, "desc": v, "tip": ALGORITHM_TIPS.get(k, "")}
            for k, v in ALGORITHMS.items()
        ])

    @pyqtSlot(result=str)
    def getClipboard(self) -> str:
        return QApplication.clipboard().text()

    def pushTheme(self, colors: dict):
        self.themeChanged.emit(json.dumps(colors))
