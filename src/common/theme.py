import json
import os

from PyQt6.QtCore import QFileSystemWatcher, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


class ThemeManager(QObject):
    """Centralized theme manager for all Nexus tools."""

    theme_changed = pyqtSignal()

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()

        from src.common.config import APPDATA, PROJECT_ROOT

        self.themes_dir = os.path.join(PROJECT_ROOT, "src", "themes")
        self.settings_file = os.path.join(APPDATA, "theme_settings.json")

        self.current_theme_name = "midnight-marina"
        self.theme_data = {}

        # Ensure themes directory exists
        if not os.path.exists(self.themes_dir):
            os.makedirs(self.themes_dir, exist_ok=True)

        self.load_settings()
        self.load_theme(self.current_theme_name)

        self.watcher = QFileSystemWatcher()
        self._update_watcher()
        self.watcher.fileChanged.connect(self._on_file_changed)
        self.watcher.directoryChanged.connect(self._on_dir_changed)

        self._initialized = True

    def _update_watcher(self):
        # Remove all existing paths
        paths = self.watcher.files()
        if paths:
            self.watcher.removePaths(paths)

        # Add current theme files
        theme_path = os.path.join(self.themes_dir, self.current_theme_name)
        if os.path.exists(theme_path):
            for f in os.listdir(theme_path):
                if f.endswith((".json", ".css", ".qss")):
                    self.watcher.addPath(os.path.join(theme_path, f))

    def _on_file_changed(self, path):
        print(f"Theme file changed: {path}")
        self.load_theme(self.current_theme_name)
        self.theme_changed.emit()

    def _on_dir_changed(self, path):
        self._update_watcher()

    def load_settings(self):
        if os.path.exists(self.settings_file):
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

    def load_theme(self, name):
        theme_file = os.path.join(self.themes_dir, name, "theme.json")
        if not os.path.exists(theme_file):
            # Fallback to default if not found
            self.theme_data = self.get_default_dark()
            return

        try:
            with open(theme_file) as f:
                self.theme_data = json.load(f)
            self.current_theme_name = name
            self.save_settings()
            self._update_watcher()
        except Exception as e:
            print(f"Error loading theme {name}: {e}")
            self.theme_data = self.get_default_dark()

    def get_default_dark(self):
        return {
            "name": "Classic Dark",
            "dark": True,
            "colors": {
                "bg_base": "#1c1c1c",
                "bg_elevated": "#252525",
                "bg_control": "#333333",
                "accent": "#0078d4",
                "text_primary": "#f3f3f3",
                "text_secondary": "#ababab",
                "border": "#404040",
            },
        }

    def __getitem__(self, key):
        # Allow direct access to colors
        colors = self.theme_data.get("colors", {})
        return colors.get(key, "#ff00ff")  # Neon pink for missing keys

    @property
    def is_dark(self):
        return self.theme_data.get("dark", True)

    def apply_to_widget(self, widget, template_qss):
        """Apply a QSS template to a widget, replacing {{var}} with theme colors."""
        qss = template_qss
        colors = self.theme_data.get("colors", {})
        for key, value in colors.items():
            qss = qss.replace(f"{{{{{key}}}}}", value)
            # Also support legacy var(--name) just in case
            qss = qss.replace(f"var(--{key.replace('_', '-')})", value)

        widget.setStyleSheet(qss)

    def get_palette(self):
        """Build a QPalette for standard dialogs/menus."""
        pal = QApplication.palette()
        T = self.theme_data.get("colors", {})

        def set_col(role, color_key):
            if color_key in T:
                pal.setColor(role, QColor(T[color_key]))

        set_col(QPalette.ColorRole.Window, "bg_base")
        set_col(QPalette.ColorRole.WindowText, "text_primary")
        set_col(QPalette.ColorRole.Base, "bg_elevated")
        set_col(QPalette.ColorRole.Text, "text_primary")
        set_col(QPalette.ColorRole.Button, "bg_control")
        set_col(QPalette.ColorRole.ButtonText, "text_primary")
        set_col(QPalette.ColorRole.Highlight, "accent")
        set_col(QPalette.ColorRole.HighlightedText, "text_on_accent")

        return pal
