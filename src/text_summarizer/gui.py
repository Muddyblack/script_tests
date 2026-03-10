"""Text Summarizer — PyQt6 GUI.

Redesigned: clean editorial dark theme, algorithm info panel,
YAKE keyword chips, soft highlight system, minimal clutter.
Fully integrated with ThemeManager / TOOL_SHEET.
"""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QTextCharFormat,
    QIcon,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.common.theme import ThemeManager, WindowThemeBridge
from src.common.theme_template import TOOL_SHEET

from .algorithms import (
    ALGORITHMS,
    ALGORITHM_TIPS,
    extract_keywords,
    summarize,
    _split_sentences,
)

# ─────────────────────────────────────────────────────────────────────────────
# Stylesheet
# ─────────────────────────────────────────────────────────────────────────────

_EXTRA_SHEET = """

/* ── Slider ──────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 3px;
    background: {{border}};
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: {{accent}};
    border: none;
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: {{accent}};
    border-radius: 2px;
}

/* ── Keyword chips ───────────────────────────────────── */
QLabel#kw_chip {
    background: transparent;
    color: {{fg_muted}};
    border: 1px solid {{border}};
    border-radius: 3px;
    padding: 1px 7px;
    font-size: 11px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
}
QLabel#kw_chip_hi {
    background: {{accent_subtle}};
    color: {{accent}};
    border: 1px solid {{accent}};
    border-radius: 3px;
    padding: 1px 7px;
    font-size: 11px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-weight: 600;
}

/* ── Stat pills ──────────────────────────────────────── */
QLabel#stat_pill {
    background: {{bg_elevated}};
    color: {{fg_muted}};
    border: 1px solid {{border}};
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 11px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
}
QLabel#stat_pill_accent {
    background: {{accent_subtle}};
    color: {{accent}};
    border: 1px solid {{accent}};
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 11px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-weight: 600;
}

/* ── Algorithm info card ─────────────────────────────── */
QFrame#algo_card {
    background: {{bg_elevated}};
    border: 1px solid {{border}};
    border-left: 3px solid {{accent}};
    border-radius: 6px;
}
QLabel#algo_tip {
    color: {{fg_muted}};
    font-size: 11px;
    padding: 0px 4px;
    background: transparent;
}

/* ── Section divider ─────────────────────────────────── */
QFrame#divider {
    background: {{border}};
    max-height: 1px;
    min-height: 1px;
}

/* ── Keyword scroll area ─────────────────────────────── */
QScrollArea#kw_scroll {
    background: transparent;
    border: none;
}
QScrollArea#kw_scroll > QWidget > QWidget {
    background: transparent;
}
"""

_SHEET = TOOL_SHEET + _EXTRA_SHEET


# ─────────────────────────────────────────────────────────────────────────────
# Worker thread
# ─────────────────────────────────────────────────────────────────────────────

class _SummarizeWorker(QThread):
    done = pyqtSignal(str, list, list)  # summary, indices, keywords

    def __init__(self, text: str, ratio: float, algorithm: str) -> None:
        super().__init__()
        self.text = text
        self.ratio = ratio
        self.algorithm = algorithm

    def run(self) -> None:
        summary, indices = summarize(self.text, self.ratio, self.algorithm)
        keywords = extract_keywords(self.text, top_n=22)
        self.done.emit(summary, indices, keywords)


# ─────────────────────────────────────────────────────────────────────────────
# Chip row widget
# ─────────────────────────────────────────────────────────────────────────────

class _ChipRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 2, 0, 2)
        self._lay.setSpacing(5)

    def set_keywords(self, keywords: list[tuple[str, float]]) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for word, score in keywords:
            chip = QLabel(word)
            chip.setObjectName("kw_chip_hi" if score >= 0.55 else "kw_chip")
            chip.setFixedHeight(20)
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._lay.addWidget(chip)

        self._lay.addStretch()


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class TextSummarizerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text Summarizer")
        self.setMinimumSize(920, 620)
        self.resize(1160, 720)

        from src.common.config import PROJECT_ROOT
        ts_icon_path = os.path.join(PROJECT_ROOT, "assets", "text_summarizer.png")
        if os.path.exists(ts_icon_path):
            self.setWindowIcon(QIcon(ts_icon_path))

        self._worker: _SummarizeWorker | None = None
        self._keywords: list[tuple[str, float]] = []
        self._highlight_on = False

        self._build_ui()

        mgr = ThemeManager()
        self._theme_bridge = WindowThemeBridge(mgr, self, _SHEET)
        mgr.theme_changed.connect(self._apply_theme)
        self._apply_theme()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        vlay = QVBoxLayout(root)
        vlay.setContentsMargins(20, 14, 20, 14)
        vlay.setSpacing(10)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title_lbl = QLabel("TEXT SUMMARIZER")
        title_lbl.setObjectName("title")
        badge = QLabel("offline · no AI")
        badge.setObjectName("stat_pill")
        hdr.addWidget(title_lbl)
        hdr.addSpacing(10)
        hdr.addWidget(badge)
        hdr.addStretch()

        # Action buttons in header
        self._paste_btn = QPushButton("Paste")
        self._paste_btn.setFixedHeight(30)
        self._paste_btn.clicked.connect(self._paste_clipboard)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.clicked.connect(self._clear_all)

        self._copy_btn = QPushButton("Copy Summary")
        self._copy_btn.setFixedHeight(30)
        self._copy_btn.clicked.connect(self._copy_summary)

        self._run_btn = QPushButton("Summarize")
        self._run_btn.setObjectName("btn_accent")
        self._run_btn.setFixedHeight(30)
        self._run_btn.clicked.connect(self._run_summarize)

        hdr.addWidget(self._paste_btn)
        hdr.addWidget(self._clear_btn)
        hdr.addSpacing(4)
        hdr.addWidget(self._copy_btn)
        hdr.addWidget(self._run_btn)
        vlay.addLayout(hdr)

        # ── Controls row ─────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        # Algorithm combo
        algo_lbl = QLabel("Algorithm")
        algo_lbl.setObjectName("section_label")
        self._algo_combo = QComboBox()
        self._algo_combo.setMinimumWidth(170)
        for name in ALGORITHMS:
            self._algo_combo.addItem(name)
        self._algo_combo.setCurrentText("Hybrid")
        self._algo_combo.currentTextChanged.connect(self._on_algo_changed)

        # Compression slider
        ratio_lbl = QLabel("Compression")
        ratio_lbl.setObjectName("section_label")
        self._ratio_slider = QSlider(Qt.Orientation.Horizontal)
        self._ratio_slider.setRange(5, 80)
        self._ratio_slider.setValue(30)
        self._ratio_slider.setFixedWidth(150)
        self._ratio_val_lbl = QLabel("30%")
        self._ratio_val_lbl.setObjectName("status")
        self._ratio_val_lbl.setFixedWidth(32)
        self._ratio_slider.valueChanged.connect(
            lambda v: self._ratio_val_lbl.setText(f"{v}%")
        )

        # Highlight toggle
        self._hi_chk = QCheckBox("Highlight keywords")
        self._hi_chk.setObjectName("status")
        self._hi_chk.stateChanged.connect(self._on_highlight_toggled)

        ctrl.addWidget(algo_lbl)
        ctrl.addWidget(self._algo_combo)
        ctrl.addSpacing(6)
        ctrl.addWidget(ratio_lbl)
        ctrl.addWidget(self._ratio_slider)
        ctrl.addWidget(self._ratio_val_lbl)
        ctrl.addSpacing(6)
        ctrl.addWidget(self._hi_chk)
        ctrl.addStretch()
        vlay.addLayout(ctrl)

        # ── Algorithm info card ──────────────────────────────────────────────
        self._algo_card = QFrame()
        self._algo_card.setObjectName("algo_card")
        self._algo_card.setFixedHeight(44)
        card_lay = QHBoxLayout(self._algo_card)
        card_lay.setContentsMargins(10, 6, 10, 6)
        card_lay.setSpacing(8)

        self._algo_name_lbl = QLabel("Hybrid")
        self._algo_name_lbl.setObjectName("section_label")
        self._algo_name_lbl.setFixedWidth(80)

        self._algo_tip_lbl = QLabel()
        self._algo_tip_lbl.setObjectName("algo_tip")
        self._algo_tip_lbl.setWordWrap(False)
        self._algo_tip_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        card_lay.addWidget(self._algo_name_lbl)
        card_lay.addWidget(self._algo_tip_lbl)
        vlay.addWidget(self._algo_card)
        self._refresh_algo_card("Hybrid")

        # ── Splitter: input | output ─────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(5)
        vlay.addWidget(splitter, stretch=1)

        # Left pane
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.setSpacing(5)

        in_hdr = QHBoxLayout()
        in_lbl = QLabel("INPUT")
        in_lbl.setObjectName("section_label")
        self._in_stat = QLabel("")
        self._in_stat.setObjectName("status")
        in_hdr.addWidget(in_lbl)
        in_hdr.addStretch()
        in_hdr.addWidget(self._in_stat)
        ll.addLayout(in_hdr)

        self._input_edit = QPlainTextEdit()
        self._input_edit.setPlaceholderText(
            "Paste or type text here…\n\nSupports any English text — news, academic, technical, or prose."
        )
        self._input_edit.textChanged.connect(self._update_in_stat)
        ll.addWidget(self._input_edit)
        splitter.addWidget(left)

        # Right pane
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.setSpacing(5)

        out_hdr = QHBoxLayout()
        out_lbl = QLabel("SUMMARY")
        out_lbl.setObjectName("section_label")
        self._out_stat = QLabel("")
        self._out_stat.setObjectName("status")
        out_hdr.addWidget(out_lbl)
        out_hdr.addStretch()
        out_hdr.addWidget(self._out_stat)
        rl.addLayout(out_hdr)

        self._output_edit = QTextEdit()
        self._output_edit.setReadOnly(True)
        self._output_edit.setPlaceholderText("Summary will appear here…")
        rl.addWidget(self._output_edit)
        splitter.addWidget(right)
        splitter.setSizes([520, 520])

        # ── Progress bar ─────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(2)
        self._progress.setTextVisible(False)
        self._progress.hide()
        vlay.addWidget(self._progress)

        # ── Stats row ────────────────────────────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(6)

        self._pill_words   = self._make_pill("—")
        self._pill_sents   = self._make_pill("—")
        self._pill_ratio   = self._make_pill("—")
        self._pill_algo    = self._make_pill("—")
        self._pill_words_lbl  = QLabel("words")
        self._pill_sents_lbl  = QLabel("sentences")
        self._pill_ratio_lbl  = QLabel("reduction")
        self._pill_algo_lbl   = QLabel("method")

        for lbl in (self._pill_words_lbl, self._pill_sents_lbl,
                    self._pill_ratio_lbl, self._pill_algo_lbl):
            lbl.setObjectName("status")

        for val, lbl in [
            (self._pill_words, self._pill_words_lbl),
            (self._pill_sents, self._pill_sents_lbl),
            (self._pill_ratio, self._pill_ratio_lbl),
            (self._pill_algo,  self._pill_algo_lbl),
        ]:
            pair = QHBoxLayout()
            pair.setSpacing(4)
            pair.addWidget(val)
            pair.addWidget(lbl)
            stats_row.addLayout(pair)

        stats_row.addStretch()
        vlay.addLayout(stats_row)

        # ── Divider ──────────────────────────────────────────────────────────
        div = QFrame()
        div.setObjectName("divider")
        vlay.addWidget(div)

        # ── Keywords row ─────────────────────────────────────────────────────
        kw_row = QHBoxLayout()
        kw_lbl = QLabel("KEY TERMS")
        kw_lbl.setObjectName("section_label")
        kw_lbl.setFixedWidth(76)
        kw_row.addWidget(kw_lbl)

        kw_scroll = QScrollArea()
        kw_scroll.setObjectName("kw_scroll")
        kw_scroll.setWidgetResizable(True)
        kw_scroll.setFixedHeight(30)
        kw_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        kw_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        kw_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._chip_row = _ChipRow()
        kw_scroll.setWidget(self._chip_row)
        kw_row.addWidget(kw_scroll)
        vlay.addLayout(kw_row)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_pill(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("stat_pill_accent")
        lbl.setFixedHeight(20)
        return lbl

    def _refresh_algo_card(self, name: str) -> None:
        self._algo_name_lbl.setText(name)
        tip = ALGORITHM_TIPS.get(name, ALGORITHMS.get(name, ""))
        # Trim to one clean sentence for the card
        self._algo_tip_lbl.setText(tip.split(".")[0] + "." if "." in tip else tip)
        self._algo_tip_lbl.setToolTip(tip)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_algo_changed(self, name: str) -> None:
        self._refresh_algo_card(name)

    def _on_highlight_toggled(self, state: int) -> None:
        self._highlight_on = bool(state)
        self._apply_highlights()

    def _update_in_stat(self) -> None:
        text = self._input_edit.toPlainText()
        words = len(text.split())
        sents = len(_split_sentences(text)) if text.strip() else 0
        self._in_stat.setText(f"{words:,} words · {sents} sentences")

    def _paste_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if text:
            self._input_edit.setPlainText(text)

    def _copy_summary(self) -> None:
        text = self._output_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def _clear_all(self) -> None:
        self._input_edit.clear()
        self._output_edit.clear()
        self._keywords = []
        self._chip_row.set_keywords([])
        self._in_stat.setText("")
        self._out_stat.setText("")
        self._pill_words.setText("—")
        self._pill_sents.setText("—")
        self._pill_ratio.setText("—")
        self._pill_algo.setText("—")

    # ── Summarize pipeline ────────────────────────────────────────────────────

    def _run_summarize(self) -> None:
        text = self._input_edit.toPlainText().strip()
        if not text:
            return

        self._run_btn.setEnabled(False)
        self._progress.show()

        ratio = self._ratio_slider.value() / 100
        algorithm = self._algo_combo.currentText()

        if self._worker and self._worker.isRunning():
            self._worker.quit()

        self._worker = _SummarizeWorker(text, ratio, algorithm)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, summary: str, indices: list[int], keywords: list[tuple[str, float]]) -> None:
        self._progress.hide()
        self._run_btn.setEnabled(True)
        self._keywords = keywords

        self._output_edit.setPlainText(summary)
        self._apply_highlights()
        self._chip_row.set_keywords(keywords[:20])

        in_text = self._input_edit.toPlainText()
        in_words = len(in_text.split())
        out_words = len(summary.split())
        in_sents = len(_split_sentences(in_text))
        out_sents = len(indices)
        reduction = round((1 - out_words / max(in_words, 1)) * 100)

        self._pill_words.setText(f"{out_words:,} / {in_words:,}")
        self._pill_sents.setText(f"{out_sents} / {in_sents}")
        self._pill_ratio.setText(f"−{reduction}%")
        self._pill_algo.setText(self._algo_combo.currentText())
        self._out_stat.setText(f"{out_words:,} words")

    # ── Keyword highlighting ───────────────────────────────────────────────────

    def _apply_highlights(self) -> None:
        """Soft, non-distracting keyword highlighting using warm amber tones."""
        doc = self._output_edit.document()
        cursor = QTextCursor(doc)

        # Always clear first
        fmt_clear = QTextCharFormat()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.setCharFormat(fmt_clear)
        cursor.clearSelection()

        if not self._highlight_on or not self._keywords:
            return

        mgr = ThemeManager()
        accent_hex = mgr.theme_data.get("accent", "#e8a045")
        accent = QColor(accent_hex)

        # Tier 1 (score ≥ 0.65): soft background fill + bold
        fmt_strong = QTextCharFormat()
        bg_strong = QColor(accent)
        bg_strong.setAlpha(55)
        fmt_strong.setBackground(bg_strong)
        fmt_strong.setFontWeight(QFont.Weight.Bold)

        # Tier 2 (score 0.35–0.65): very subtle underline tint
        fmt_mid = QTextCharFormat()
        bg_mid = QColor(accent)
        bg_mid.setAlpha(25)
        fmt_mid.setBackground(bg_mid)

        # Tier 3 (score < 0.35): just a faint underline, no background
        fmt_low = QTextCharFormat()
        fmt_low.setFontUnderline(True)
        underline_col = QColor(accent)
        underline_col.setAlpha(120)
        fmt_low.setUnderlineColor(underline_col)
        fmt_low.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.DotLine
        )

        import re
        text = doc.toPlainText()
        for word, score in self._keywords[:18]:
            if score >= 0.65:
                fmt = fmt_strong
            elif score >= 0.35:
                fmt = fmt_mid
            else:
                fmt = fmt_low

            for m in re.finditer(r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE):
                c = QTextCursor(doc)
                c.setPosition(m.start())
                c.setPosition(m.end(), QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(fmt)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        mgr = ThemeManager()
        mgr.apply_to_widget(self, _SHEET)

        from src.common.theme import apply_win32_titlebar
        apply_win32_titlebar(int(self.winId()), mgr["bg_base"], mgr.is_dark)

        if self._highlight_on and self._keywords:
            self._apply_highlights()


# ─────────────────────────────────────────────────────────────────────────────
# Entry points
# ─────────────────────────────────────────────────────────────────────────────

def start_text_summarizer(parent=None) -> TextSummarizerWindow:
    win = TextSummarizerWindow(parent)
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = TextSummarizerWindow()
    win.show()
    sys.exit(app.exec())