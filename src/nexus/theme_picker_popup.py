"""Nexus Search — main UI widget with all search, navigation, and launch logic."""

import json
import os

from PyQt6.QtCore import (
    Qt,
)
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.common.theme import ThemeManager

# ---------------------------------------------------------------------------
# VS Code-style theme picker popup
# ---------------------------------------------------------------------------


class ThemePickerPopup(QFrame):
    """Floating theme picker — live preview on hover, confirm on click/Enter."""

    def __init__(self, parent: QWidget):
        super().__init__(
            parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(300)

        self._mgr = ThemeManager()
        self._prev_theme = self._mgr.current_theme_name
        self._confirmed = False
        self._themes: list[tuple[str, str]] = []  # (folder, display name)

        self._build_ui()
        self._load_themes()
        self._apply_popup_style()

        # Re-style popup when theme changes (live preview)
        self._mgr.theme_changed.connect(self._apply_popup_style)

        # Ensure the list has focus so arrow keys work immediately
        self._list.setFocus()

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        hdr = QLabel("COLOR THEME")
        hdr.setObjectName("_picker_hdr")
        layout.addWidget(hdr)

        sep = QFrame()
        sep.setObjectName("_picker_sep")
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        self._list = QListWidget()
        self._list.setObjectName("_picker_list")
        self._list.setFrameShape(QListWidget.Shape.NoFrame)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setFixedHeight(272)
        self._list.itemClicked.connect(self._on_click)
        self._list.currentRowChanged.connect(self._on_hover)
        layout.addWidget(self._list)

        hint = QLabel("↑↓  preview   ↵  confirm   Esc  cancel")
        hint.setObjectName("_picker_hint")
        layout.addWidget(hint)

    def _load_themes(self):
        from src.common.config import PROJECT_ROOT

        themes_dir = os.path.join(PROJECT_ROOT, "src", "themes")
        self._themes = []
        try:
            for folder in sorted(os.listdir(themes_dir)):
                jf = os.path.join(themes_dir, folder, "theme.json")
                if os.path.exists(jf):
                    try:
                        with open(jf) as f:
                            data = json.load(f)
                        name = data.get("name", folder)
                    except Exception:
                        name = folder
                    self._themes.append((folder, name))
        except Exception:
            pass

        self._list.clear()
        current = self._mgr.current_theme_name
        for i, (folder, name) in enumerate(self._themes):
            mark = "✓" if folder == current else " "
            item = QListWidgetItem(f"  {mark}   {name}")
            self._list.addItem(item)
            if folder == current:
                self._list.setCurrentRow(i)

    def _apply_popup_style(self):
        c = self._mgr.theme_data.get("colors", {})
        bg = c.get("bg_elevated", "#1e2a3a")
        bg2 = c.get("bg_overlay", "#01121f")
        text = c.get("text_primary", "#cbe0f0")
        text2 = c.get("text_secondary", "#8aa0b0")
        accent = c.get("accent", "#0eadcf")
        accent_s = c.get("accent_subtle", "rgba(14,173,207,0.12)")
        border = c.get("border", "#336380")

        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QFrame#_picker_sep {{
                background: {border};
                max-height: 1px;
                border: none;
            }}
            QLabel#_picker_hdr {{
                color: {text2};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 2px;
                padding: 2px 4px 4px 4px;
                font-family: 'Outfit','Inter','Segoe UI';
            }}
            QLabel#_picker_hint {{
                color: {text2};
                font-size: 9px;
                padding: 4px 4px 2px 4px;
                letter-spacing: 0.5px;
                font-family: 'Outfit','Inter','Segoe UI';
            }}
            QListWidget#_picker_list {{
                background: {bg2};
                border: none;
                outline: none;
                border-radius: 8px;
                font-family: 'Outfit','Inter','Segoe UI';
                font-size: 13px;
                color: {text};
            }}
            QListWidget#_picker_list::item {{
                padding: 8px 12px;
                border-radius: 6px;
            }}
            QListWidget#_picker_list::item:selected {{
                background: {accent_s};
                color: {accent};
                font-weight: 600;
            }}
            QListWidget#_picker_list::item:hover {{
                background: {accent_s};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 3px;
                margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {border};
                border-radius: 2px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def _on_hover(self, row: int):
        """Live-preview the hovered theme."""
        if 0 <= row < len(self._themes):
            folder, _ = self._themes[row]
            self._mgr.load_theme(folder)
            self._mgr.theme_changed.emit()

    def _on_click(self, item):
        """Confirm the selected theme."""
        self._confirmed = True
        self.close()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirmed = True
            self.close()
            event.accept()
        elif key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        elif key == Qt.Key.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
            event.accept()
        elif key == Qt.Key.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
            event.accept()
        elif key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            # Pass to list for page-wise navigation
            self._list.keyPressEvent(event)
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Revert to original theme if not confirmed."""
        self._mgr.theme_changed.disconnect(self._apply_popup_style)
        if not self._confirmed:
            self._mgr.load_theme(self._prev_theme)
            self._mgr.theme_changed.emit()
        super().closeEvent(event)
