"""Centralized theme manager for all Nexus tools.

Usage everywhere:
    from src.common.theme import ThemeManager
    mgr = ThemeManager()          # always returns the same singleton
    mgr.theme_changed.connect(...)
    mgr.apply_to_widget(widget, QSS_TEMPLATE)
"""

import json
import os

from PyQt6.QtCore import QFileSystemWatcher, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Singleton holder — module-level, avoids __new__ on QObject (which crashes)
# ---------------------------------------------------------------------------
_instance: "_ThemeManager | None" = None


def ThemeManager() -> "_ThemeManager":
    """Return the process-wide ThemeManager singleton, creating it on first call."""
    global _instance
    if _instance is None:
        _instance = _ThemeManager()
    return _instance


# ---------------------------------------------------------------------------
# The real class
# ---------------------------------------------------------------------------

class _ThemeManager(QObject):
    """Singleton theme manager — do NOT instantiate directly; use ThemeManager()."""

    theme_changed = pyqtSignal()

    def __init__(self):
        super().__init__()

        from src.common.config import APPDATA, PROJECT_ROOT

        self.themes_dir = os.path.join(PROJECT_ROOT, "src", "themes")
        self.settings_file = os.path.join(APPDATA, "theme_settings.json")

        self.current_theme_name = "midnight-marina"
        self.theme_data: dict = {}

        os.makedirs(self.themes_dir, exist_ok=True)

        self._watcher = QFileSystemWatcher()
        self._watcher.fileChanged.connect(self._on_file_changed)

        self.load_settings()
        self.load_theme(self.current_theme_name)

    # ------------------------------------------------------------------
    # File watching
    # ------------------------------------------------------------------
    def _update_watcher(self):
        watched = self._watcher.files()
        if watched:
            self._watcher.removePaths(watched)
        theme_path = os.path.join(self.themes_dir, self.current_theme_name)
        if os.path.exists(theme_path):
            for fname in os.listdir(theme_path):
                if fname.endswith((".json", ".css", ".qss")):
                    self._watcher.addPath(os.path.join(theme_path, fname))

    def _on_file_changed(self, path: str):
        self.load_theme(self.current_theme_name)
        self.theme_changed.emit()

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------
    def load_settings(self):
        try:
            with open(self.settings_file) as f:
                data = json.load(f)
                self.current_theme_name = data.get("theme", "midnight-marina")
        except Exception:
            pass

    def save_settings(self):
        try:
            with open(self.settings_file, "w") as f:
                json.dump({"theme": self.current_theme_name}, f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Theme loading
    # ------------------------------------------------------------------
    def load_theme(self, name: str):
        theme_file = os.path.join(self.themes_dir, name, "theme.json")
        if not os.path.exists(theme_file):
            self.theme_data = self._default_dark()
            return
        try:
            with open(theme_file) as f:
                self.theme_data = json.load(f)
            self.current_theme_name = name
            self.save_settings()
            self._update_watcher()
        except Exception as e:
            print(f"[ThemeManager] Error loading theme '{name}': {e}")
            self.theme_data = self._default_dark()

    def _default_dark(self) -> dict:
        return {
            "name": "Classic Dark",
            "dark": True,
            "colors": {
                "bg_base": "#1c1c1c",
                "bg_elevated": "#252525",
                "bg_overlay": "#1a1a1a",
                "bg_control": "#333333",
                "row_alt": "#222222",
                "accent": "#0078d4",
                "accent_subtle": "rgba(0,120,212,0.12)",
                "accent_pressed": "#0063b1",
                "border": "#404040",
                "border_light": "#505050",
                "text_primary": "#f3f3f3",
                "text_secondary": "#ababab",
                "text_disabled": "#6b7280",
                "text_on_accent": "#ffffff",
                "success": "#44ffb1",
                "danger": "#ff4466",
                "warning": "#ffe073",
            },
        }

    # ------------------------------------------------------------------
    # Available themes
    # ------------------------------------------------------------------
    def get_available_themes(self) -> list[tuple[str, str]]:
        """Return [(folder_name, display_name), ...] for every installed theme."""
        themes = []
        try:
            for folder in sorted(os.listdir(self.themes_dir)):
                jf = os.path.join(self.themes_dir, folder, "theme.json")
                if os.path.exists(jf):
                    try:
                        with open(jf) as f:
                            data = json.load(f)
                        themes.append((folder, data.get("name", folder)))
                    except Exception:
                        themes.append((folder, folder))
        except Exception:
            pass
        return themes

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    def __getitem__(self, key: str) -> str:
        # Better fallback: if key is missing, try bg_base, then bg_elevated, then neutral grey
        colors = self.theme_data.get("colors", {})
        if key in colors:
            return colors[key]
        
        # Fallbacks for specific common keys
        if key == "row_alt":
            return colors.get("bg_overlay", colors.get("bg_base", "#1c1c1c"))
        
        return colors.get("bg_base", "#ff00ff")

    @property
    def is_dark(self) -> bool:
        return self.theme_data.get("dark", True)

    def apply_to_widget(self, widget, template_qss: str):
        """Apply a QSS template to a widget, substituting {{color_key}} placeholders."""
        qss = template_qss
        for key, value in self.theme_data.get("colors", {}).items():
            qss = qss.replace(f"{{{{{key}}}}}", value)
            qss = qss.replace(f"var(--{key.replace('_', '-')})", value)
        widget.setStyleSheet(qss)

    def get_palette(self) -> QPalette:
        """Build a QPalette from the current theme colors."""
        pal = QApplication.palette()
        T = self.theme_data.get("colors", {})

        def _set(role, key):
            if key in T:
                pal.setColor(role, QColor(T[key]))

        R = QPalette.ColorRole
        _set(R.Window,          "bg_base")
        _set(R.WindowText,      "text_primary")
        _set(R.Base,            "bg_elevated")
        _set(R.Text,            "text_primary")
        _set(R.Button,          "bg_control")
        _set(R.ButtonText,      "text_primary")
        _set(R.Highlight,       "accent")
        _set(R.HighlightedText, "text_on_accent")
        return pal
