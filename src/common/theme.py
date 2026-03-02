"""Centralized theme manager for all Nexus tools.

Usage everywhere:
    from src.common.theme import ThemeManager
    mgr = ThemeManager()          # always returns the same singleton
    mgr.theme_changed.connect(...)
    mgr.apply_to_widget(widget, QSS_TEMPLATE)

For WebEngine-based tools:
    from src.common.theme import ThemeManager, WebThemeBridge
    bridge = WebThemeBridge(mgr, web_view)
    # That's it — theme is injected before first paint and kept in sync.
"""

import json
import os
import sys

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
        if os.path.exists(self.settings_file):
            self._watcher.addPath(self.settings_file)
        theme_path = os.path.join(self.themes_dir, self.current_theme_name)
        if os.path.exists(theme_path):
            for fname in os.listdir(theme_path):
                if fname.endswith((".json", ".css", ".qss")):
                    self._watcher.addPath(os.path.join(theme_path, fname))

    def _on_file_changed(self, path: str):
        # Normalizes to handle Windows paths correctly
        if os.path.normpath(path) == os.path.normpath(self.settings_file):
            self.load_settings()
            self.load_theme(self.current_theme_name, save=False)
        else:
            self.load_theme(self.current_theme_name, save=False)
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
    def load_theme(self, name: str, save: bool = True):
        theme_file = os.path.join(self.themes_dir, name, "theme.json")
        if not os.path.exists(theme_file):
            self.theme_data = self._default_dark()
            return
        try:
            with open(theme_file) as f:
                self.theme_data = json.load(f)
            self.current_theme_name = name
            if save:
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

    def build_web_css(self, alpha_variants: dict | None = None) -> str:
        """Build a CSS variable string suitable for injection into a WebEngine page.

        Converts all theme.json color keys to CSS vars (underscore → hyphen),
        appends computed rgba alpha variants, and adds shadow/grain vars.

        ``alpha_variants`` maps CSS-var-name → (theme_key, alpha_float).
        If omitted the standard set used by Chronos is applied.
        """
        _DEFAULT_ALPHAS = {
            "warning-dim": ("warning", 0.1),
            "warning-glow": ("warning", 0.2),
            "danger-dim": ("danger", 0.15),
            "danger-glow": ("danger", 0.06),
            "success-dim": ("success", 0.15),
            "success-glow": ("success", 0.06),
            "accent-dim": ("accent", 0.15),
            "accent-glow-bg": ("accent", 0.06),
            "accent-hover-dim": ("accent_hover", 0.15),
            "accent-pressed-dim": ("accent_pressed", 0.15),
        }
        alphas = alpha_variants if alpha_variants is not None else _DEFAULT_ALPHAS
        colors = self.theme_data.get("colors", {})
        parts: list[str] = []

        for name, color in colors.items():
            parts.append(f"--{name.replace('_', '-')}: {color}")

        for css_var, (theme_key, alpha) in alphas.items():
            val = colors.get(theme_key, "")
            rgb = _hex_to_rgb(val)
            if rgb:
                r, g, b = rgb
                parts.append(f"--{css_var}: rgba({r},{g},{b},{alpha})")

        if self.is_dark:
            parts += [
                "--shadow-sm: 0 2px 8px rgba(0,0,0,0.6)",
                "--shadow-md: 0 8px 32px rgba(0,0,0,0.7)",
                "--shadow-lg: 0 24px 64px rgba(0,0,0,0.8)",
                "--grain-opacity: 0.025",
            ]
        else:
            parts += [
                "--shadow-sm: 0 2px 8px rgba(0,0,0,0.08)",
                "--shadow-md: 0 8px 32px rgba(0,0,0,0.12)",
                "--shadow-lg: 0 24px 64px rgba(0,0,0,0.18)",
                "--grain-opacity: 0.01",
            ]

        scheme = "dark" if self.is_dark else "light"
        parts.append(f"color-scheme: {scheme}")
        return "; ".join(parts)

    def get_palette(self) -> QPalette:
        """Build a QPalette from the current theme colors."""
        pal = QApplication.palette()
        T = self.theme_data.get("colors", {})

        def _set(role, key):
            if key in T:
                pal.setColor(role, QColor(T[key]))

        R = QPalette.ColorRole
        _set(R.Window, "bg_base")
        _set(R.WindowText, "text_primary")
        _set(R.Base, "bg_elevated")
        _set(R.Text, "text_primary")
        _set(R.Button, "bg_control")
        _set(R.ButtonText, "text_primary")
        _set(R.Highlight, "accent")
        _set(R.HighlightedText, "text_on_accent")
        return pal


# ---------------------------------------------------------------------------
# Win32 titlebar theming
# ---------------------------------------------------------------------------
def apply_win32_titlebar(win_id: int, bg_hex: str, is_dark: bool) -> None:
    """Set the Win32 titlebar color and dark-mode flag for a window.

    Works on Windows 11 (build 22000+) for caption color;
    dark-mode flag works from Windows 10 20H1 onward.
    No-ops silently on non-Windows or if ctypes fails.
    """
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes
        import ctypes.wintypes

        dwmapi = ctypes.windll.dwmapi
        hwnd = ctypes.wintypes.HWND(win_id)

        # Ensure the window is shown and handled by the OS
        # Sometimes a tiny delay helps for initial window creation
        def _apply():
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            dark = ctypes.c_int(1 if is_dark else 0)
            dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)
            )

            # DWMWA_CAPTION_COLOR = 35  (Windows 11+)
            rgb = _hex_to_rgb(bg_hex)
            if rgb:
                r, g, b = rgb
                # COLORREF is 0x00BBGGRR (Windows uses BGR)
                colorref = ctypes.c_int(r | (g << 8) | (b << 16))
                dwmapi.DwmSetWindowAttribute(
                    hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref)
                )

        _apply()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Private helper (used by build_web_css)
# ---------------------------------------------------------------------------
def _hex_to_rgb(h: str) -> tuple[int, int, int] | None:
    """Convert '#RRGGBB' string to (r, g, b). Returns None on failure."""
    if not h or not isinstance(h, str):
        return None
    h = h.strip()
    if h.startswith(("rgb", "rgba", "hsl")):
        return None
    h = h.lstrip("#")
    if len(h) < 6:
        # Resolve shorthand #RGB to #RRGGBB
        if len(h) == 3:
            h = "".join([c * 2 for c in h])
        else:
            return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Bridges — plug-and-play theme injection
# ---------------------------------------------------------------------------


class WindowThemeBridge:
    """Connects a ThemeManager to a QMainWindow or QWidget top-level.

    Automatically handles:
    - QSS substitution and application
    - QPalette sync (for native widgets)
    - Windows 11 title bar coloring (same as Chronos)
    - Live updates when the theme changes

    Usage::

        self._theme_bridge = WindowThemeBridge(ThemeManager(), self, TOOL_SHEET)
    """

    def __init__(
        self,
        mgr: "_ThemeManager",
        window,
        qss_template: str | None = None,
        titlebar_color_key: str = "bg_base",
    ):
        from PyQt6.QtCore import QTimer

        self._mgr = mgr
        self._win = window
        self._qss = qss_template
        self._color_key = titlebar_color_key

        # Connect signals
        mgr.theme_changed.connect(self.apply)

        # Initial apply with a tiny delay to ensure winId is valid and window is initialized
        QTimer.singleShot(0, self.apply)

    def apply(self):
        if not self._win:
            return

        # 1. Apply QSS
        if self._qss:
            self._mgr.apply_to_widget(self._win, self._qss)

        # 2. Apply Palette
        self._win.setPalette(self._mgr.get_palette())

        # 3. Apply Win32 titlebar
        if sys.platform == "win32":
            try:
                # Use the specific color key (usually bg_base or bg_elevated)
                color = self._mgr[self._color_key]
                apply_win32_titlebar(int(self._win.winId()), color, self._mgr.is_dark)
            except Exception:
                pass


class WebThemeBridge:
    """Connects a ThemeManager to a QWebEngineView."""

    _SCRIPT_NAME = "nexus_web_theme"

    def __init__(self, mgr: "_ThemeManager", view, alpha_variants: dict | None = None):
        from PyQt6.QtGui import QColor
        from PyQt6.QtWebEngineCore import QWebEngineScript

        self._mgr = mgr
        self._view = view
        self._alpha_variants = alpha_variants
        self._QColor = QColor
        self._QWebEngineScript = QWebEngineScript

        # Set Qt background color to match theme (prevents white flash)
        view.page().setBackgroundColor(QColor(mgr["bg_base"]))

        # Inject script
        self._inject_script()

        # Re-apply on every page load and on theme change
        view.loadFinished.connect(lambda ok: self._on_load(ok))
        mgr.theme_changed.connect(self._on_theme_changed)

        # Apply titlebar after the event loop starts
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(0, self._apply_titlebar)

    def _build_js(self) -> str:
        css = self._mgr.build_web_css(self._alpha_variants)
        return f"document.documentElement.style.cssText = `{css}`;"

    def _inject_script(self):
        QWebEngineScript = self._QWebEngineScript
        js = self._build_js()
        script = QWebEngineScript()
        script.setName(self._SCRIPT_NAME)
        script.setSourceCode(js)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        page_scripts = self._view.page().scripts()
        for existing in page_scripts.toList():
            if existing.name() == self._SCRIPT_NAME:
                page_scripts.remove(existing)
                break
        page_scripts.insert(script)

    def _on_load(self, ok: bool):
        if not ok:
            return
        self._view.page().runJavaScript(self._build_js())
        self._view.page().setBackgroundColor(self._QColor(self._mgr["bg_base"]))
        self._apply_titlebar()

    def _apply_titlebar(self):
        win = self._view.window()
        if win:
            apply_win32_titlebar(
                int(win.winId()), self._mgr["bg_base"], self._mgr.is_dark
            )

    def _on_theme_changed(self):
        self._inject_script()
        self._view.page().runJavaScript(self._build_js())
        self._view.page().setBackgroundColor(self._QColor(self._mgr["bg_base"]))
        self._apply_titlebar()
