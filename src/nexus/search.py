"""Nexus Search — main UI widget with all search, navigation, and launch logic."""

import contextlib
import ctypes
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

import keyboard
from PyQt6.QtCore import (
    QDateTime,
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
)
from PyQt6.QtGui import QColor, QCursor, QDesktopServices, QGuiApplication, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileIconProvider,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.archiver.archiver import ArchiverWindow, is_archive
from src.common.config import (
    APPDATA,
    APPS_CACHE_FILE,
    DB_PATH,
    ICON_PATH,
    PROJECT_ROOT,
    SEARCH_HISTORY_FILE,
    SETTINGS_FILE,
    USAGE_FILE,
    X_EXPLORER_DB,
)

# Import SearchEngine
from src.common.search_engine import SearchEngine
from src.common.theme import ThemeManager
from src.file_ops.file_ops import FileOpsWindow
from src.img_to_text import start_snip_to_text

from .system_commands import (
    execute_system_toggle as _exec_toggle,
)
from .system_commands import (
    kill_all_processes as _kill_all_procs,
)
from .system_commands import (
    kill_process as _kill_proc,
)
from .system_commands import (
    launch_archiver as _launch_archiver,
)
from .system_commands import (
    launch_base64_tool as _launch_base64_tool,
)
from .system_commands import (
    launch_chronos as _launch_chronos,
)
from .system_commands import (
    launch_color_picker as _launch_color_picker,
)
from .system_commands import (
    launch_file_ops as _launch_file_ops,
)
from .system_commands import (
    launch_regex_helper as _launch_regex,
)
from .system_commands import (
    launch_xexplorer as _launch_xexplorer,
)
from .system_commands import (
    log_to_chronos as _log_to_chronos,
)
from .system_commands import (
    trigger_reindex as _trigger_reindex,
)
from .system_commands import (
    update_process_cache as _update_procs,
)
from .themes import get_nexus_theme
from .utils import format_display_name
from .widgets import IconWorker, NexusInput, RainbowFrame

# ---------------------------------------------------------------------------
# VS Code-style theme picker popup
# ---------------------------------------------------------------------------


class _ThemePickerPopup(QFrame):
    """Floating theme picker — live preview on hover, confirm on click/Enter."""

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(280)

        self._mgr = ThemeManager()
        self._prev_theme = self._mgr.current_theme_name
        self._confirmed = False
        self._themes: list[tuple[str, str]] = []  # (folder, display name)

        self._build_ui()
        self._load_themes()
        self._apply_popup_style()

        # Re-style popup when theme changes (live preview)
        self._mgr.theme_changed.connect(self._apply_popup_style)

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        hdr = QLabel("COLOR THEME")
        hdr.setObjectName("_picker_hdr")
        layout.addWidget(hdr)

        self._list = QListWidget()
        self._list.setObjectName("_picker_list")
        self._list.setFrameShape(QListWidget.Shape.NoFrame)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setFixedHeight(260)
        self._list.itemClicked.connect(self._on_click)
        self._list.currentRowChanged.connect(self._on_hover)
        layout.addWidget(self._list)

        hint = QLabel("↑↓ Preview  •  Enter Confirm  •  Esc Cancel")
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
            item = QListWidgetItem(f"  {'●' if folder == current else '○'}  {name}")
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
                border-radius: 10px;
            }}
            QLabel#_picker_hdr {{
                color: {text2}; font-size: 9px; font-weight: 700;
                letter-spacing: 3px; padding: 2px 6px;
                font-family: 'Outfit','Inter','Segoe UI';
            }}
            QLabel#_picker_hint {{
                color: {text2}; font-size: 9px; padding: 2px 6px;
                font-family: 'Outfit','Inter','Segoe UI';
            }}
            QListWidget#_picker_list {{
                background: {bg2}; border: none; outline: none;
                border-radius: 6px;
                font-family: 'Outfit','Inter','Segoe UI';
                font-size: 12px; color: {text};
            }}
            QListWidget#_picker_list::item {{
                padding: 7px 10px; border-radius: 6px;
            }}
            QListWidget#_picker_list::item:selected {{
                background: {accent_s}; color: {accent};
            }}
            QListWidget#_picker_list::item:hover {{
                background: {accent_s};
            }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 2px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {border}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
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
        elif key == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Revert to original theme if not confirmed."""
        self._mgr.theme_changed.disconnect(self._apply_popup_style)
        if not self._confirmed:
            self._mgr.load_theme(self._prev_theme)
            self._mgr.theme_changed.emit()
        super().closeEvent(event)


class NexusSearch(QWidget):
    """The main Nexus Search launcher UI."""

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus Search")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(960, 700)
        self.resize(960, 700)

        # Window state
        self.dragging = False
        self.drag_pos = None

        # Mode state
        self.modes = {
            "apps": True,
            "bookmarks": True,
            "files": False,
            "scripts": True,
            "processes": False,
            "toggles": True,
            "ssh": True,
            "files_only": False,
            "folders_only": False,
            "target_folders": [],
            "content": False,
            "side_panel_visible": True,
        }
        self.view_mode = "list"
        self.load_settings()

        self.usage_stats = {}
        self.load_usage()

        # Search text history for auto-completion
        self.search_history = []
        self.load_search_history()

        # Data cache
        self.browser_bookmarks = []
        self.ssh_hosts = []
        self.process_cache = []
        self.last_proc_update = 0
        self.installed_apps = []
        self.load_apps_cache()

        self.scan_ssh_hosts()
        self.icon_provider = QFileIconProvider()
        self.icon_cache = {}
        self.search_engine = SearchEngine([X_EXPLORER_DB, DB_PATH])
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(2)
        self.pending_icons = set()

        self.setup_ui()
        self.apply_theme()
        ThemeManager().theme_changed.connect(self.apply_theme)
        self.center_on_screen()

        # Slow app scanning in background
        threading.Thread(target=self.scan_installed_apps_bg, daemon=True).start()
        threading.Thread(target=self.load_browser_bookmarks, daemon=True).start()

        # Debounce timer for search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

        self.last_search_time = 0
        # Clock timer — live updates
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()
        self.current_candidates = []

        # Global input redirect
        if sys.platform == "win32":
            keyboard.on_press(self.on_global_key)
        else:
            #Best effort local focus handling instead of global keyboard hook
            pass

    # ------------------------------------------------------------------
    # App scanning
    # ------------------------------------------------------------------
    def load_apps_cache(self):
        if os.path.exists(APPS_CACHE_FILE):
            try:
                with open(APPS_CACHE_FILE) as f:
                    self.installed_apps = json.load(f)
            except Exception:
                pass

    def scan_installed_apps_bg(self):
        time.sleep(2)
        self.scan_installed_apps()
        try:
            with open(APPS_CACHE_FILE, "w") as f:
                json.dump(self.installed_apps, f)
        except Exception:
            pass

    def scan_installed_apps(self):
        """Scan Windows Start Menu and Desktop for application shortcuts."""
        paths = [
            os.path.join(
                os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
                r"Microsoft\Windows\Start Menu",
            ),
            os.path.join(
                os.environ.get("APPDATA", ""),
                r"Microsoft\Windows\Start Menu",
            ),
            os.path.join(os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        ]
        apps = []
        for p in paths:
            if not os.path.exists(p):
                continue
            for root, _, files in os.walk(p):
                for f in files:
                    if f.lower().endswith((".lnk", ".url")):
                        name = f.rsplit(".", 1)[0]
                        apps.append({"name": name, "path": os.path.join(root, f)})
        self.installed_apps = apps

    # ------------------------------------------------------------------
    # SSH hosts
    # ------------------------------------------------------------------
    def scan_ssh_hosts(self):
        """Parse ~/.ssh/config for SSH sessions."""
        self.ssh_hosts = []
        ssh_config = os.path.expanduser("~/.ssh/config")
        if os.path.exists(ssh_config):
            try:
                with open(ssh_config) as f:
                    for line in f:
                        line = line.strip()
                        if line.lower().startswith("host ") and "*" not in line:
                            host = line.split(" ", 1)[1].strip()
                            if host:
                                self.ssh_hosts.append(host)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Global key redirect
    # ------------------------------------------------------------------
    def on_global_key(self, event):
        """Redirect keys to Nexus when it is visible but not focused."""
        if not self.isVisible():
            return
        if self.isActiveWindow():
            return

        key_name = event.name.lower()
        navigation_keys = {
            "up": -1,
            "down": 1,
            "arrow up": -1,
            "arrow down": 1,
            "page up": -10,
            "page down": 10,
        }

        if key_name in navigation_keys:
            self.navigate_results(navigation_keys[key_name])
            return
        elif key_name in ["enter", "return"]:
            self.launch_selected()
            return
        elif key_name in ("esc", "escape"):
            self.hide()
            return

        if len(key_name) == 1:
            if (
                keyboard.is_pressed("ctrl")
                or keyboard.is_pressed("alt")
                or keyboard.is_pressed("windows")
            ):
                return
            self.search_input.setText(self.search_input.text() + event.name)
            QTimer.singleShot(0, self.summon_and_focus)
            return

    # ------------------------------------------------------------------
    # Focus management
    # ------------------------------------------------------------------
    def summon_and_focus(self):
        """Aggressively grab focus. Uses Windows API on Windows, else PyQt."""
        self.show()
        self.raise_()
        self.activateWindow()

        if sys.platform == "win32":
            hwnd = int(self.winId())
            foreground_thread = ctypes.windll.user32.GetWindowThreadProcessId(
                ctypes.windll.user32.GetForegroundWindow(), None
            )
            current_thread = ctypes.windll.kernel32.GetCurrentThreadId()

            if foreground_thread != current_thread:
                ctypes.windll.user32.AttachThreadInput(
                    foreground_thread, current_thread, True
                )
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.AttachThreadInput(
                    foreground_thread, current_thread, False
                )
            else:
                ctypes.windll.user32.SetForegroundWindow(hwnd)

            ctypes.windll.user32.ShowWindow(hwnd, 5)

        self.search_input.setFocus(Qt.FocusReason.OtherFocusReason)
        self.search_input.activateWindow()

    # ------------------------------------------------------------------
    # Result navigation
    # ------------------------------------------------------------------
    def navigate_results(self, delta):
        if self.view_mode == "tree":
            curr = self.results_tree.currentItem()
            if not curr:
                first = self.results_tree.topLevelItem(0)
                if first:
                    self.results_tree.setCurrentItem(first)
                return
            target = curr
            for _ in range(abs(delta)):
                ptr = (
                    self.results_tree.itemBelow(target)
                    if delta > 0
                    else self.results_tree.itemAbove(target)
                )
                if ptr:
                    target = ptr
                else:
                    break
            self.results_tree.setCurrentItem(target)
        else:
            idx = self.results_list.currentRow()
            count = self.results_list.count()
            if count > 0:
                new_idx = (idx + delta) % count
                self.results_list.setCurrentRow(new_idx)

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------
    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.modes.update(
                            {k: v for k, v in data.items() if k not in ("light_mode",)}
                        )
        except Exception:
            pass

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.modes, f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------
    def load_usage(self):
        try:
            if os.path.exists(USAGE_FILE):
                with open(USAGE_FILE) as f:
                    self.usage_stats = json.load(f)
        except Exception:
            self.usage_stats = {}

    def record_usage(self, key):
        """Increment usage count."""
        count = self.usage_stats.get(key, 0) + 1
        self.usage_stats[key] = count
        try:
            with open(USAGE_FILE, "w") as f:
                json.dump(self.usage_stats, f)
        except Exception:
            pass

    def get_usage_boost(self, key):
        """Score boost based on usage frequency."""
        count = self.usage_stats.get(key, 0)
        return min(count * 50, 600)

    # ------------------------------------------------------------------
    # Search history (raw text)
    # ------------------------------------------------------------------
    def load_search_history(self):
        try:
            if os.path.exists(SEARCH_HISTORY_FILE):
                with open(SEARCH_HISTORY_FILE) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.search_history = data
        except Exception:
            self.search_history = []

    def record_search(self, raw_text):
        """Save a search string to history to enable autocomplete."""
        text = raw_text.strip()
        if not text:
            return
        # Move to front
        if text in self.search_history:
            self.search_history.remove(text)
        self.search_history.insert(0, text)
        self.search_history = self.search_history[:100]  # Keep 100 max
        try:
            with open(SEARCH_HISTORY_FILE, "w") as f:
                json.dump(self.search_history, f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Browser Bookmarks
    # ------------------------------------------------------------------
    def load_browser_bookmarks(self):
        self.browser_bookmarks = []
        paths = []
        paths.extend(
            glob.glob(
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    r"Google\Chrome\User Data\*\Bookmarks",
                )
            )
        )
        paths.extend(
            glob.glob(
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    r"Microsoft\Edge\User Data\*\Bookmarks",
                )
            )
        )
        paths.extend(
            glob.glob(
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    r"BraveSoftware\Brave-Browser\User Data\*\Bookmarks",
                )
            )
        )

        def extract_urls(node):
            if isinstance(node, dict):
                if node.get("type") == "url":
                    self.browser_bookmarks.append(
                        {
                            "name": node.get("name", "Unnamed Bookmark"),
                            "url": node.get("url", ""),
                        }
                    )
                elif "children" in node:
                    for child in node.get("children", []):
                        extract_urls(child)

        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                        roots = data.get("roots", {})
                        for key in roots:
                            extract_urls(roots[key])
                except Exception:
                    pass

        seen = set()
        unique = []
        for b in self.browser_bookmarks:
            if b["url"] not in seen:
                seen.add(b["url"])
                unique.append(b)
        self.browser_bookmarks = unique

    # ------------------------------------------------------------------
    # UI setup  (redesigned: side-panel + rainbow input + action buttons)
    # ------------------------------------------------------------------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)

        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("nexus_bg")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(50)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.bg_frame.setGraphicsEffect(shadow)

        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        bg_layout.setSpacing(0)

        # ── QSplitter: left panel | right content ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("nexus_splitter")
        self.splitter.setHandleWidth(3)
        self.splitter.setChildrenCollapsible(False)

        # ── Left Panel (branding + sources, full height) ──
        self.left_panel = QWidget()
        self.left_panel.setObjectName("left_panel")
        self.left_panel.setMinimumWidth(130)
        self.left_panel.setMaximumWidth(250)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(16, 14, 10, 10)
        left_layout.setSpacing(10)

        # Brand row (inside left panel)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        if os.path.exists(ICON_PATH):
            logo_lbl = QLabel()
            logo_lbl.setObjectName("nexus_logo")
            pix = QIcon(ICON_PATH).pixmap(20, 20)
            logo_lbl.setPixmap(pix)
            brand_row.addWidget(logo_lbl)
        brand_lbl = QLabel("NEXUS")
        brand_lbl.setObjectName("nexus_brand")
        brand_row.addWidget(brand_lbl)
        brand_row.addStretch()

        ver_lbl = QLabel("v2")
        ver_lbl.setObjectName("nexus_version")
        brand_row.addWidget(ver_lbl)
        left_layout.addLayout(brand_row)

        # Sources header
        panel_hdr = QLabel("SOURCES")
        panel_hdr.setObjectName("panel_header")
        left_layout.addWidget(panel_hdr)

        # Mode buttons
        self.mode_btns = {}
        modes_metadata = [
            ("apps", "Apps", "package.svg"),
            ("bookmarks", "Bookmarks", "star.svg"),
            ("files", "Files", "folder.svg"),
            ("scripts", "Scripts", "code.svg"),
            ("ssh", "SSH", "server.svg"),
            ("processes", "Processes", "zap.svg"),
            ("toggles", "System", "settings.svg"),
        ]
        for key, label, icon_name in modes_metadata:
            btn = QPushButton(f"  {label}")
            btn.setIcon(self._create_svg_icon(icon_name, color="#78849e"))
            btn.setCheckable(True)
            btn.setChecked(self.modes[key])
            btn.setObjectName("mode_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self.toggle_mode(k, checked))
            left_layout.addWidget(btn)
            self.mode_btns[key] = btn

        left_layout.addStretch()

        # File filter sub-buttons
        self.filter_bar = QFrame()
        self.filter_bar.setObjectName("filter_bar")
        self.filter_bar.setVisible(self.modes.get("files", False))
        fb_layout = QVBoxLayout(self.filter_bar)
        fb_layout.setContentsMargins(0, 4, 0, 0)
        fb_layout.setSpacing(3)

        self.btn_f_only = QPushButton("Just Files")
        self.btn_f_only.setCheckable(True)
        self.btn_f_only.setChecked(self.modes.get("files_only", False))
        self.btn_f_only.setObjectName("mode_btn")
        self.btn_f_only.clicked.connect(lambda c: self.toggle_sub_mode("files_only", c))

        self.btn_d_only = QPushButton("Just Folders")
        self.btn_d_only.setCheckable(True)
        self.btn_d_only.setChecked(self.modes.get("folders_only", False))
        self.btn_d_only.setObjectName("mode_btn")
        self.btn_d_only.clicked.connect(
            lambda c: self.toggle_sub_mode("folders_only", c)
        )

        self.btn_pick_folders = QPushButton("Pick Folder…")
        self.btn_pick_folders.setObjectName("mode_btn")
        self.btn_pick_folders.clicked.connect(self.show_folder_picker)

        self.btn_reset_path = QPushButton("Reset Path")
        self.btn_reset_path.setObjectName("mode_btn")
        self.btn_reset_path.setToolTip("Clear all folder search filters")
        self.btn_reset_path.clicked.connect(self.clear_folder_filters)
        # Highlight if filter is active
        if self.modes.get("target_folders"):
            self.btn_reset_path.setStyleSheet("color: #ef4444; font-weight: bold;")

        self.btn_view_toggle = QPushButton("Tree View")
        self.btn_view_toggle.setCheckable(True)
        self.btn_view_toggle.setObjectName("mode_btn")
        self.btn_view_toggle.clicked.connect(self.toggle_view_mode)

        fb_layout.addWidget(self.btn_f_only)
        fb_layout.addWidget(self.btn_d_only)
        fb_layout.addWidget(self.btn_view_toggle)
        fb_layout.addWidget(self.btn_pick_folders)
        fb_layout.addWidget(self.btn_reset_path)
        left_layout.addWidget(self.filter_bar)

        left_layout.addStretch()

        # Clock in bottom left panel
        self.clock_lbl = QLabel()
        self.clock_lbl.setObjectName("nexus_clock")
        self.clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.clock_lbl)

        self.splitter.addWidget(self.left_panel)

        # ── Right Panel (input + results + footer) ──
        right_panel = QWidget()
        right_panel.setObjectName("right_panel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 14, 16, 10)
        right_layout.setSpacing(10)

        # Toggle button (in right panel top-left, visible when panel hidden)
        top_bar = QHBoxLayout()
        self.btn_side_toggle = QPushButton("≡")
        self.btn_side_toggle.setObjectName("panel_toggle")
        self.btn_side_toggle.setFixedSize(28, 24)
        self.btn_side_toggle.setToolTip("Toggle Sources Panel")
        self.btn_side_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_side_toggle.clicked.connect(self.toggle_side_panel)
        top_bar.addWidget(self.btn_side_toggle)
        top_bar.addStretch()

        # Theme picker button (VS Code-style)
        _mgr = ThemeManager()
        self._theme_btn = QPushButton(f"◑ {_mgr.theme_data.get('name', _mgr.current_theme_name)}")
        self._theme_btn.setObjectName("theme_btn")
        self._theme_btn.setFixedHeight(24)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setToolTip("Color Theme (Ctrl+K Ctrl+T)")
        self._theme_btn.clicked.connect(self._open_theme_picker)
        top_bar.addWidget(self._theme_btn)

        # Settings folder button
        self._settings_btn = QPushButton("📂")
        self._settings_btn.setObjectName("theme_btn") # reuse style
        self._settings_btn.setFixedSize(28, 24)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setToolTip("Open Settings Folder")
        self._settings_btn.clicked.connect(self._open_settings_folder)
        top_bar.addWidget(self._settings_btn)

        right_layout.addLayout(top_bar)

        # Rainbow-wrapped search input
        self.rainbow_frame = RainbowFrame()
        self.search_input = NexusInput(self)
        self.search_input.setObjectName("nexus_search")
        self.search_input.setPlaceholderText(
            "Search apps, files, scripts, workspaces …"
        )
        self.search_input.textChanged.connect(lambda: self.search_timer.start(30))
        self.rainbow_frame._content_layout.addWidget(self.search_input)
        right_layout.addWidget(self.rainbow_frame)

        # Results area
        self.results_stack = QStackedWidget()
        self.results_stack.setObjectName("results_stack")

        self.results_list = QListWidget()
        self.results_list.setObjectName("nexus_list")
        self.results_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.results_list.itemDoubleClicked.connect(self.launch_selected)
        self.results_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_list.customContextMenuRequested.connect(self.show_context_menu)

        self.results_tree = QTreeWidget()
        self.results_tree.setObjectName("nexus_tree")
        self.results_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.results_tree.viewport().setStyleSheet("background: transparent;")
        self.results_tree.setHeaderHidden(True)
        self.results_tree.setIndentation(20)
        self.results_tree.itemDoubleClicked.connect(self.launch_selected)
        self.results_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_tree.customContextMenuRequested.connect(
            self.show_tree_context_menu
        )

        self.results_stack.addWidget(self.results_list)
        self.results_stack.addWidget(self.results_tree)
        right_layout.addWidget(self.results_stack, stretch=1)

        self.results_list.currentRowChanged.connect(self.on_item_hover)
        self.results_list.verticalScrollBar().valueChanged.connect(
            self.lazy_load_visible_icons
        )

        # Footer
        footer_layout = QHBoxLayout()
        self.status_lbl = QLabel("Nexus Engine Ready …")
        self.status_lbl.setObjectName("status_text")
        self.status_lbl.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        footer_layout.addWidget(self.status_lbl, stretch=1)

        hint_lbl = QLabel("Enter ↵  Launch  •  Esc  Hide")
        hint_lbl.setObjectName("hint_text")
        footer_layout.addWidget(hint_lbl)

        right_layout.addLayout(footer_layout)

        self.splitter.addWidget(right_panel)

        # Splitter proportions
        self.splitter.setStretchFactor(0, 0)  # left panel fixed
        self.splitter.setStretchFactor(1, 1)  # right panel expands
        self.splitter.setSizes([160, 760])

        bg_layout.addWidget(self.splitter)
        main_layout.addWidget(self.bg_frame)

        # Initial side panel visibility from settings
        is_visible = self.modes.get("side_panel_visible", True)
        self.left_panel.setVisible(is_visible)

    # ------------------------------------------------------------------
    # Mode toggles
    # ------------------------------------------------------------------
    def toggle_mode(self, mode, checked):
        self.modes[mode] = checked
        if mode == "files":
            self.filter_bar.setVisible(checked)
        if mode == "processes" and checked:
            _update_procs(self, force=True)
        self.save_settings()
        self.perform_search()

    def toggle_view_mode(self, checked):
        self.view_mode = "tree" if checked else "list"
        self.results_stack.setCurrentIndex(1 if checked else 0)
        self.btn_view_toggle.setText("List View" if checked else "Tree View")
        self.perform_search()

    def toggle_side_panel(self):
        is_visible = self.left_panel.isVisible()
        self.left_panel.setVisible(not is_visible)
        self.modes["side_panel_visible"] = not is_visible
        self.save_settings()

    def toggle_sub_mode(self, mode, checked):
        if mode == "files_only" and checked:
            self.modes["folders_only"] = False
            self.btn_d_only.setChecked(False)
        elif mode == "folders_only" and checked:
            self.modes["files_only"] = False
            self.btn_f_only.setChecked(False)
        self.modes[mode] = checked
        self.save_settings()
        self.update_reset_path_style()
        self.perform_search()

    def clear_folder_filters(self):
        """Reset path-specific folder filters."""
        self.modes["target_folders"] = []
        self.save_settings()
        self.update_reset_path_style()
        self.status_lbl.setText("Folder filters cleared")
        self.perform_search()

    def update_reset_path_style(self):
        """Update Reset Path button style based on filter state."""
        if hasattr(self, "btn_reset_path"):
            if self.modes.get("target_folders"):
                self.btn_reset_path.setStyleSheet("color: #ef4444; font-weight: bold;")
            else:
                self.btn_reset_path.setStyleSheet("")

    def show_folder_picker(self):
        managed = []
        if os.path.exists(X_EXPLORER_DB):
            try:
                with sqlite3.connect(X_EXPLORER_DB) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM settings WHERE key='folders'")
                    res = cursor.fetchone()
                    if res:
                        try:
                            folders_data = json.loads(res[0])
                            managed = [f["path"] for f in folders_data]
                        except json.JSONDecodeError:
                            managed = [
                                f.rsplit(":", 1)[0]
                                for f in res[0].split("|")
                                if ":" in f
                            ]
            except Exception:
                pass

        if not managed:
            self.status_lbl.setText("No managed folders found in X-Explorer cache.")
            return

        self.status_lbl.setText("Select Search Folders (ESC to return)")
        self.results_list.clear()

        item = QListWidgetItem("Search EVERYTHING (Clear Filters)")
        item.setData(Qt.ItemDataRole.UserRole, {"type": "filter_clear"})
        self.results_list.addItem(item)

        for path in managed:
            is_active = path in self.modes.get("target_folders", [])
            state = "check.svg" if is_active else "folder.svg"
            item = QListWidgetItem(f"{state}{path}")
            item.setData(
                Qt.ItemDataRole.UserRole, {"type": "filter_toggle", "path": path}
            )
            self.results_list.addItem(item)

    # ------------------------------------------------------------------
    # Event overrides
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        """Auto-hide when clicking outside (Windows only)."""
        if sys.platform == "win32":
            QTimer.singleShot(150, self.check_focus_and_hide)
        super().focusOutEvent(event)

    def check_focus_and_hide(self):
        if not self.isActiveWindow() and self.isVisible():
            self.hide()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Context menus
    # ------------------------------------------------------------------
    def show_context_menu(self, pos):
        item = self.results_list.itemAt(pos)
        if not item:
            return

        selected = self.results_list.selectedItems()
        if item not in selected:
            selected = [item]

        data_list = [i.data(Qt.ItemDataRole.UserRole) for i in selected]
        self._show_common_menu(pos, data_list, self.results_list)

    def show_tree_context_menu(self, pos):
        item = self.results_tree.itemAt(pos)
        if not item:
            return

        selected = self.results_tree.selectedItems()
        if item not in selected:
            selected = [item]

        data_list = []
        for i in selected:
            data = i.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                # Intermediate folder node — reconstruct path from tree hierarchy
                parts = []
                node = i
                while node:
                    parts.insert(0, node.text(0))
                    node = node.parent()
                folder_path = os.sep.join(parts)
                if os.path.isdir(folder_path):
                    data = {"type": "file", "path": folder_path}
            if data:
                data_list.append(data)

        self._show_common_menu(pos, data_list, self.results_tree)

    def _show_common_menu(self, pos, data_list, parent_widget):
        if not data_list:
            return
        menu = QMenu(self)
        _mgr = ThemeManager()
        _c = _mgr.theme_data.get("colors", {})
        _bg = _c.get("bg_elevated", "#1e293b")
        _txt = _c.get("text_primary", "#f8fafc")
        _brd = _c.get("border", "#334155")
        _acc = _c.get("accent", "#3b82f6")
        menu.setStyleSheet(
            f"QMenu {{ background-color: {_bg}; color: {_txt}; border: 1px solid {_brd}; "
            f"border-radius: 8px; }} QMenu::item {{ padding: 6px 20px; }} "
            f"QMenu::item:selected {{ background-color: {_acc}; color: {_c.get('text_on_accent', 'white')}; }}"
        )

        paths = [
            d.get("path") for d in data_list if isinstance(d, dict) and d.get("path")
        ]

        if paths:
            copy_path = menu.addAction("Copy Path(s)")
            copy_name = menu.addAction("Copy File Name(s)")
            open_loc = menu.addAction("Open File Location")
            search_here = None
            if len(paths) == 1:
                search_here = menu.addAction("🎯 Search ONLY in this Folder")

            menu.addSeparator()
            file_ops_action = menu.addAction("Copy / Move / Delete...")

            archive_action = None
            extract_action = None
            if len(paths) == 1 and is_archive(paths[0]):
                extract_action = menu.addAction("Extract Archive...")
            else:
                archive_action = menu.addAction("Compress to Archive...")

            action = menu.exec(parent_widget.mapToGlobal(pos))
            if not action:
                return

            if action != search_here:
                self.hide()

            if action == copy_path:
                norm_paths = [os.path.normpath(p) for p in paths]
                QApplication.clipboard().setText("\n".join(norm_paths))
                self.status_lbl.setText(f"Copied {len(norm_paths)} path(s)")
            elif action == copy_name:
                names = [os.path.basename(p) for p in paths]
                QApplication.clipboard().setText("\n".join(names))
                self.status_lbl.setText("Copied file name(s) to clipboard")
            elif action == open_loc:
                norm_path = os.path.normpath(paths[0])
                if os.path.exists(norm_path):
                    if os.path.isdir(norm_path):
                        os.startfile(norm_path)
                    else:
                        subprocess.Popen(f'explorer /select,"{norm_path}"')
                else:
                    self.status_lbl.setText("Path not found on disk")
            elif search_here and action == search_here:
                path = paths[0]
                dir_path = path if os.path.isdir(path) else os.path.dirname(path)
                self.modes["target_folders"] = [dir_path]
                self.modes["files"] = True
                self.search_input.setText("")
                self.search_input.setFocus()
                self.status_lbl.setText(
                    f"Locked Search to: {os.path.basename(dir_path)}"
                )
                self.save_settings()
            elif action == file_ops_action:
                self.file_ops_win = FileOpsWindow()
                self.file_ops_win.source_paths = list(paths)
                self.file_ops_win._refresh_list()
                self.file_ops_win.show()
            elif (
                archive_action
                and action == archive_action
                or extract_action
                and action == extract_action
            ):
                self.archiver_win = ArchiverWindow()
                self.archiver_win.source_paths = list(paths)
                self.archiver_win._refresh_list()
                self.archiver_win.show()

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------
    def update_clock(self):
        """Update the live clock label."""
        self.clock_lbl.setText(QDateTime.currentDateTime().toString("HH:mm:ss"))

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------
    def center_on_screen(self):
        cursor_pos = QCursor.pos()
        screen = None
        for s in QGuiApplication.screens():
            if s.geometry().contains(cursor_pos):
                screen = s
                break
        if not screen:
            screen = QGuiApplication.primaryScreen()

        screen_geo = screen.geometry()
        x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
        y = screen_geo.y() + int(screen_geo.height() * 0.2)
        self.move(x, y)

    def hide(self):
        for hk in ["esc", "up", "down", "enter"]:
            with contextlib.suppress(Exception):
                keyboard.remove_hotkey(hk)
        super().hide()

    def summon(self):
        self.center_on_screen()
        self.search_input.clear()
        self.perform_search()

        self.setWindowOpacity(0)
        self.show()
        self.raise_()
        self.show()
        self.raise_()
        self.activateWindow()

        self.summon_and_focus()
        QTimer.singleShot(10, self.summon_and_focus)
        QTimer.singleShot(100, self.summon_and_focus)
        QTimer.singleShot(300, self.summon_and_focus)

        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(250)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

        # Trigger rainbow glow on the search input
        self.rainbow_frame.trigger_animation()

    def start_img_to_text(self) -> None:
        """Snip a region on screen and OCR it into clipboard."""
        start_snip_to_text(nexus=self)

    # ------------------------------------------------------------------
    # Search engine
    # ------------------------------------------------------------------
    def perform_search(self):
        raw_search = self.search_input.text().strip()
        search = raw_search.lower()
        self.results_list.clear()
        self.results_tree.clear()
        self.pending_icons.clear()
        candidates = []

        def matches_all_terms(text, terms):
            if not terms:
                return True
            tl = text.lower()
            return all(t in tl for t in terms)

        # 0. CHRONOS QUICK-LOG
        if search.startswith("+") and len(search) > 1:
            log_text = search[1:].strip()
            candidates.append(
                {
                    "score": 10000,
                    "title": f"CHRONOS: Log '{log_text}'",
                    "path": "Record this achievement instantly to Chronos Hub",
                    "icon": "clock.svg",
                    "color": "#fbbf24",
                    "data": {"type": "chronos_log", "content": log_text},
                }
            )
            self.results_list.clear()
            self.results_tree.clear()
            self.populate_list_results(candidates)
            return

        # 0.1. EXACT PATH DETECTION — open files/folders from paths
        if os.path.exists(raw_search) and (
            os.path.isabs(raw_search)
            or (len(raw_search) > 2 and raw_search[1:3] == ":\\")
        ):
            is_dir = os.path.isdir(raw_search)
            candidates.append(
                {
                    "score": 5000,
                    "title": f"Open {'Folder' if is_dir else 'File'}: {os.path.basename(raw_search) or raw_search}",
                    "path": raw_search,
                    "icon": "folder.svg" if is_dir else "file.svg",
                    "file_path": raw_search,
                    "data": {"type": "file", "path": raw_search},
                }
            )

        # 0.2. URL DETECTION
        url_pattern = re.compile(
            r"^(https?://)?"
            r"(([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}|"
            r"localhost|"
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
            r"(:\d+)?"
            r"(/.*)?$"
        )
        if (
            url_pattern.match(raw_search)
            and ("." in raw_search or "localhost" in raw_search.lower())
            and not os.path.exists(raw_search)
        ):
            url = raw_search
            if not url.lower().startswith("http"):
                url = "https://" + url
            candidates.append(
                {
                    "score": 4500,
                    "title": f"Open Web URL: {raw_search}",
                    "path": f"Browse to {url}",
                    "icon": "globe.svg",
                    "color": "#3b82f6",
                    "data": {"type": "url", "url": url},
                }
            )

        # Prefix logic
        prefixes = {
            ":b": "bookmarks",
            ":f": "files",
            ":s": "scripts",
            ":p": "processes",
            ":t": "toggles",
            ":ssh": "ssh",
            ":a": "apps",
            ":c": "content",
        }
        active_modes = self.modes.copy()
        search_term = search

        for pref, mode_key in prefixes.items():
            if search.startswith(pref + " ") or search == pref:
                for k in active_modes:
                    if k in prefixes.values():
                        active_modes[k] = False
                active_modes[mode_key] = True
                search_term = search[len(pref) :].strip()
                break

        terms = [t for t in search_term.split() if t]

        # Footer hint
        if active_modes.get("processes"):
            self.status_lbl.setText(
                "Executioner Mode • Select and Press Enter to Finish It"
            )
            self.status_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
        else:
            self.status_lbl.setText("Nexus Engine Ready...")
            self.status_lbl.setStyleSheet("color: #6b7280;")

        # 0. SSH Hosts
        if active_modes.get("ssh"):
            for host in self.ssh_hosts:
                if matches_all_terms(host, terms):
                    candidates.append(
                        {
                            "score": 980,
                            "title": f"SSH: {host}",
                            "path": f"Remote Node • ssh {host}",
                            "icon": "server.svg",
                            "data": {"type": "ssh", "host": host},
                        }
                    )

        # 1. Apps
        if active_modes.get("apps"):
            for app in self.installed_apps:
                if matches_all_terms(app["name"], terms):
                    boost = self.get_usage_boost(app["path"])
                    candidates.append(
                        {
                            "score": 1000 + boost,
                            "title": app["name"],
                            "path": f"App • {app['path']}",
                            "file_path": app["path"],
                            "icon": "package.svg",
                            "data": {"type": "app", "path": app["path"]},
                        }
                    )

        # 2. System Commands & Toggles
        if active_modes.get("toggles") or search.startswith(">"):
            score_base = 1100 if search.startswith(">") or not search else 500
            t_terms = [t.strip(">") for t in terms]

            mgmt_cmds = [
                (
                    "xexplorer - File Manager",
                    "Modern explorer with blazing-fast search",
                    "xexplorer",
                    "folder.svg",
                    "#3b82f6",
                ),
                (
                    "Re-index Files (X-Explorer)",
                    "Background re-index of search cache",
                    "reindex_files",
                    "refresh.svg",
                    "#60a5fa",
                ),
                (
                    "Regex Helper",
                    "Offline Pattern Tester",
                    "regex_helper",
                    "search.svg",
                    "#f472b6",
                ),
                (
                    "Base64 Encoder/Decoder",
                    "Encode and decode text strings",
                    "base64_tool",
                    "hash.svg",
                    "#4f46e5",
                ),
                (
                    "Color Picker",
                    "Hex & RGB preview + color tool",
                    "color_picker",
                    "palette.svg",
                    "#8b5cf6",
                ),
                (
                    "File Ops",
                    "Fast copy • move • delete",
                    "file_ops",
                    "folder.svg",
                    "#22c55e",
                ),
                (
                    "Chronos Hub",
                    "Achievement & Mission Tracker",
                    "chronos_hub",
                    "clock.svg",
                    "#fbbf24",
                ),
                (
                    "Archiver",
                    "Zip • tar • 7z compress & extract",
                    "archiver",
                    "package.svg",
                    "#a78bfa",
                ),
                (
                    "Snip → Text (OCR)",
                    "Select an area on screen and copy text to clipboard",
                    "img_to_text",
                    "image.svg",
                    "#22c55e",
                ),
            ]
            for title, path, cmd, icon, color in mgmt_cmds:
                if not terms or matches_all_terms(title, t_terms):
                    candidates.append(
                        {
                            "score": score_base,
                            "title": title,
                            "path": f"System • {path}",
                            "icon": icon,
                            "color": color,
                            "data": {"type": "cmd", "cmd": cmd},
                        }
                    )

            power_commands = [
                (
                    "Toggle Nexus Theme (App Only)",
                    "Theme",
                    "toggle_nexus_theme",
                    "moon.svg",
                    ["dark", "light", "nexus", "app"],
                ),
                (
                    "Toggle Windows Theme (System)",
                    "Theme",
                    "toggle_dark_mode",
                    "moon.svg",
                    ["dark", "light", "theme", "night", "system", "windows"],
                ),
                (
                    "Toggle Hidden Files",
                    "Explorer",
                    "toggle_hidden_files",
                    "eye.svg",
                    ["hidden", "files", "view", "explorer"],
                ),
                (
                    "Toggle Desktop Icons",
                    "Desktop",
                    "toggle_desktop_icons",
                    "menu.svg",
                    ["icons", "desktop", "shortcuts"],
                ),
                (
                    "Toggle System Mute",
                    "Audio",
                    "toggle_mute",
                    "eye.svg",
                    ["mute", "audio", "volume", "sound"],
                ),
                (
                    "Show / Hide Desktop",
                    "Windows",
                    "toggle_desktop",
                    "file-axis-3d.svg",
                    ["desktop", "reveal", "hide"],
                ),
                (
                    "Restart Windows Explorer",
                    "System",
                    "restart_explorer",
                    "refresh.svg",
                    ["restart", "explorer", "refresh", "taskbar"],
                ),
                (
                    "Flush DNS Cache",
                    "Network",
                    "flush_dns",
                    "refresh.svg",
                    ["dns", "flush", "network", "reset"],
                ),
                (
                    "Lock Workstation",
                    "Security",
                    "cmd_lock",
                    "arrow-right.svg",
                    ["lock", "security", "sign out"],
                ),
                (
                    "Put PC to Sleep",
                    "Power",
                    "cmd_sleep",
                    "arrow-right.svg",
                    ["sleep", "standby", "power"],
                ),
                (
                    "Restart Computer",
                    "Power",
                    "cmd_restart",
                    "refresh.svg",
                    ["restart", "reboot", "power"],
                ),
                (
                    "Shutdown System",
                    "Power",
                    "cmd_shutdown",
                    "power.svg",
                    ["shutdown", "power off", "exit"],
                ),
                (
                    "Windows Settings",
                    "ms-settings",
                    "ms-settings:default",
                    "arrow-right.svg",
                    ["settings", "config", "windows"],
                ),
                (
                    "Display Settings",
                    "ms-settings",
                    "ms-settings:display",
                    "arrow-right.svg",
                    ["display", "monitor", "resolution", "brightness"],
                ),
                (
                    "Wi-Fi Settings",
                    "ms-settings",
                    "ms-settings:network-wifi",
                    "arrow-right.svg",
                    ["wifi", "internet", "wireless"],
                ),
            ]
            for title, path, cmd, icon, keywords in power_commands:
                if (
                    not terms
                    or matches_all_terms(title, t_terms)
                    or any(matches_all_terms(kw, t_terms) for kw in keywords)
                ):
                    score = score_base - 10
                    if search_term and search_term in title.lower():
                        score += 150
                    candidates.append(
                        {
                            "score": score,
                            "title": title,
                            "path": f"System › {path}",
                            "icon": icon,
                            "color": "#94a3b8",
                            "data": {"type": "cmd", "cmd": cmd},
                        }
                    )

        # 3. Bookmarks
        if active_modes.get("bookmarks"):
            for b in self.browser_bookmarks:
                if (
                    not terms
                    or matches_all_terms(b["name"], terms)
                    or matches_all_terms(b["url"], terms)
                ):
                    candidates.append(
                        {
                            "score": 600,
                            "title": b["name"],
                            "path": b["url"],
                            "icon": "star.svg",
                            "color": "#fcd34d",
                            "data": {"type": "url", "url": b["url"]},
                        }
                    )

        # 4. Local Scripts
        if active_modes.get("scripts"):
            # Include project root, core packages, and user scripts
            script_paths = [
                PROJECT_ROOT,
                os.path.join(PROJECT_ROOT, "src", "xexplorer"),
                os.path.join(PROJECT_ROOT, "src", "regex_helper"),
                os.path.join(PROJECT_ROOT, "src", "file_ops"),
                os.path.join(PROJECT_ROOT, "src", "archiver"),
                os.path.join(PROJECT_ROOT, "src", "color_picker"),
                os.path.join(PROJECT_ROOT, "src", "base64_tool"),
                os.path.join(PROJECT_ROOT, "src", "chronos"),
                os.path.join(APPDATA, "scripts"),
            ]
            for spath in script_paths:
                if not os.path.exists(spath):
                    continue
                for f in os.listdir(spath):
                    if f.endswith(".py") and f not in [
                        "nexus_launcher.py",
                        "nexus_search.py",
                        "__init__.py",
                        "__main__.py",
                    ]:
                        display_name = f[:-3].replace("_", " ").title()
                        if matches_all_terms(display_name, terms) or matches_all_terms(
                            f, terms
                        ):
                            score = 800
                            if search_term and f.lower().startswith(search_term):
                                score += 500
                            f_path = os.path.join(spath, f)
                            score += self.get_usage_boost(f"script_{f_path}")
                            candidates.append(
                                {
                                    "score": score,
                                    "title": display_name,
                                    "path": f"Python Script • {f}",
                                    "file_path": f_path,
                                    "icon": "code.svg",
                                    "data": {"type": "script", "path": f_path},
                                }
                            )

        # 6. File Search (Centralized Engine)
        if active_modes.get("files"):
            files_only = active_modes.get("files_only", False)
            folders_only = active_modes.get("folders_only", False)
            target_folders = active_modes.get("target_folders", [])

            results = self.search_engine.search_files(
                query_terms=terms,
                target_folders=target_folders,
                files_only=files_only,
                folders_only=folders_only,
                limit=100,
            )

            for f_path, is_dir, f_name in results:
                score = 200 + (50 if is_dir else 0)
                if search_term and f_name.lower() == search_term:
                    score += 500
                score += self.get_usage_boost(f"file_{f_path}")

                # UNC / network paths get a globe icon
                icon = (
                    "globe.svg"
                    if self._is_unc_path(f_path)
                    else "folder.svg"
                    if is_dir
                    else "file.svg"
                )

                candidates.append(
                    {
                        "score": score,
                        "title": format_display_name(f_name),
                        "path": f_path,
                        "file_path": f_path,
                        "icon": icon,
                        "data": {"type": "file", "path": f_path},
                    }
                )

        # 6.5. Content Search
        if active_modes.get("content") and terms:
            target_folders = active_modes.get("target_folders", [])
            results = self.search_engine.search_content(
                query_terms=terms, target_folders=target_folders, limit=50
            )
            for f_path, _is_dir, f_name in results:
                candidates.append(
                    {
                        "score": 150,
                        "title": f"{f_name}",
                        "path": f"Found in content • {f_path}",
                        "file_path": f_path,
                        "icon": "file.svg",
                        "data": {"type": "file", "path": f_path},
                    }
                )

        # 7. Processes
        is_explicit_process = search.startswith(":p")
        if active_modes.get("processes") and (terms or is_explicit_process):
            _update_procs(self)
            # Group by name
            grouped = {}
            for p in self.process_cache:
                name = p["name"]
                if matches_all_terms(name, terms):
                    if name not in grouped:
                        grouped[name] = {
                            "count": 0,
                            "pids": [],
                            "mem_sum": 0,
                            "path": p["path"],
                            "desc": p["desc"],
                        }
                    grouped[name]["count"] += 1
                    grouped[name]["pids"].append(p["pid"])
                    grouped[name]["mem_sum"] += p["mem_bytes"]

            for name, info in grouped.items():
                mem_mb = info["mem_sum"] // 1024 // 1024
                # Description suffix
                desc_suff = f" • {info['desc']}" if info["desc"] else ""

                # Group result for multi-instance
                if info["count"] > 1:
                    candidates.append(
                        {
                            "score": 750
                            + (100 if name.lower().startswith(search_term) else 0),
                            "title": f"{name} ({info['count']} instances)",
                            "path": f"Total: {mem_mb} MB{desc_suff}",
                            "file_path": info["path"],
                            "icon": "power.svg",
                            "color": "#f87171",
                            "data": {"type": "process_kill_all", "name": name},
                        }
                    )

                # Individual result (only if 1 or if specifically requested)
                # For clarity we show the first one if count > 1 as sample, or just show all if search is narrow
                limit_individuals = 1 if info["count"] > 3 else info["count"]
                for i in range(limit_individuals):
                    pid = info["pids"][i]
                    # Find individual mem for this PID if possible, else use average
                    # For simplicity we just show average if grouped, or actual if single
                    m_val = mem_mb if info["count"] == 1 else "?"
                    candidates.append(
                        {
                            "score": 700
                            + (100 if name.lower().startswith(search_term) else 0),
                            "title": name
                            if info["count"] == 1
                            else f"{name} (PID: {pid})",
                            "path": f"PID: {pid} • {m_val} MB{desc_suff}",
                            "file_path": info["path"],
                            "icon": "power.svg",
                            "color": "#ef4444",
                            "data": {
                                "type": "process",
                                "pid": pid,
                                "name": name,
                            },
                        }
                    )

        # Web Search Fallback (Only if explicit or if nothing found)
        if search:
            web_query = search
            engine_url = "https://www.google.com/search?q="
            is_explicit = False

            if search.startswith("g ") and len(search) > 2:
                web_query = search[2:].strip()
                is_explicit = True
            elif search.startswith("b ") and len(search) > 2:
                engine_url = "https://www.bing.com/search?q="
                web_query = search[2:].strip()
                is_explicit = True
            elif search.startswith("yt ") and len(search) > 3:
                engine_url = "https://www.youtube.com/results?search_query="
                web_query = search[3:].strip()
                is_explicit = True

            if is_explicit or not candidates:
                encoded_query = urllib.parse.quote(web_query)
                candidates.append(
                    {
                        "score": 6000 if is_explicit else 300,
                        "title": f"Web Search: {web_query}",
                        "path": f"Search online • {web_query}",
                        "icon": "globe.svg",
                        "color": "#3b82f6",
                        "data": {"type": "url", "url": engine_url + encoded_query},
                    }
                )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        if self.view_mode == "tree":
            self.populate_tree_results(candidates)
        else:
            self.populate_list_results(candidates)

    # ------------------------------------------------------------------
    # Result population
    # ------------------------------------------------------------------
    def _create_svg_icon(self, svg_name, color="#9ca3af"):
        from PyQt6.QtCore import QByteArray
        from PyQt6.QtGui import QIcon, QPixmap

        svg_path = os.path.join(PROJECT_ROOT, "assets", "svgs", svg_name)
        if not os.path.exists(svg_path):
            return QIcon()
        try:
            with open(svg_path, encoding="utf-8") as f:
                data = f.read().replace("currentColor", color)
            pix = QPixmap()
            pix.loadFromData(QByteArray(data.encode("utf-8")), "SVG")
            return QIcon(pix)
        except Exception:
            return QIcon()

    def _is_unc_path(self, path: str) -> bool:
        """Return True if *path* is a UNC / network path."""
        return path.startswith("\\\\") or path.startswith("//")

    def _action_copy_path(self, path: str):
        norm = os.path.normpath(path)
        QApplication.clipboard().setText(norm)
        short = norm if len(norm) < 50 else "…" + norm[-45:]
        self.status_lbl.setText(f"Copied: {short}")

    def _action_copy_dir(self, path: str):
        d = path if os.path.isdir(path) else os.path.dirname(path)
        norm = os.path.normpath(d)
        QApplication.clipboard().setText(norm)
        short = norm if len(norm) < 50 else "…" + norm[-45:]
        self.status_lbl.setText(f"Copied: {short}")

    def _action_open_folder(self, path: str):
        norm = os.path.normpath(path)
        if os.path.exists(norm):
            if os.path.isdir(norm):
                os.startfile(norm)
            else:
                subprocess.Popen(f'explorer /select,"{norm}"')
        else:
            self.status_lbl.setText("Path not found on disk")

    def populate_list_results(self, candidates):
        self.current_candidates = candidates[:50]
        self.results_list.setUpdatesEnabled(False)

        for idx, c in enumerate(self.current_candidates):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, c["data"])
            item.setData(Qt.ItemDataRole.UserRole + 1, c)
            self.results_list.addItem(item)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(12, 0, 8, 0)
            row_layout.setSpacing(14)

            # -- Icon (UNC-aware) --
            icon_label = QLabel()
            icon_label.setObjectName(f"icon_{idx}")
            icon_label.setFixedSize(38, 38)
            icon_label.setScaledContents(True)

            icon_name = c.get("icon", "file.svg")
            file_path = c.get("file_path") or c["data"].get("path", "")
            if file_path and self._is_unc_path(file_path):
                icon_name = "globe.svg"

            # Render SVG with color
            color_hex = c.get("color", "#9ca3af")
            svg_path = os.path.join(PROJECT_ROOT, "assets", "svgs", icon_name)
            if not os.path.exists(svg_path):
                svg_path = os.path.join(PROJECT_ROOT, "assets", "svgs", "file.svg")

            try:
                from PyQt6.QtCore import QByteArray
                from PyQt6.QtGui import QPixmap

                with open(svg_path, encoding="utf-8") as fs:
                    svg_data = fs.read()
                svg_data = svg_data.replace("currentColor", color_hex)
                pix = QPixmap()
                pix.loadFromData(QByteArray(svg_data.encode("utf-8")), "SVG")
                icon_label.setPixmap(pix)
            except Exception:
                pass

            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            row_layout.addWidget(icon_label)

            # -- Text column --
            text_container = QVBoxLayout()
            text_container.setContentsMargins(0, 0, 0, 0)
            text_container.setSpacing(1)

            title_lbl = QLabel(c["title"])
            title_lbl.setObjectName("item_title")
            if "color" in c:
                title_lbl.setStyleSheet(f"color: {c['color']};")

            display_path = c.get("path", "")
            # Show UNC prefix hint
            if file_path and self._is_unc_path(file_path):
                display_path = f"{display_path}"
            path_lbl = QLabel(format_display_name(display_path, max_len=72))
            path_lbl.setObjectName("item_path")

            text_container.addWidget(title_lbl)
            text_container.addWidget(path_lbl)
            row_layout.addLayout(text_container, stretch=1)

            # -- Alt Shortcut Badge --
            if idx < 9:
                hk_lbl = QLabel(f"{idx + 1}")
                hk_lbl.setObjectName("shortcut_badge")
                hk_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row_layout.addWidget(hk_lbl)

            # -- Inline action buttons --
            d = c["data"]
            dtype = d.get("type")

            if dtype in ("file", "app", "script", None) and d.get("path"):
                p_val = d["path"]
                btn_copy = QPushButton()
                btn_copy.setIcon(self._create_svg_icon("copy.svg"))
                btn_copy.setObjectName("action_btn")
                btn_copy.setToolTip("Copy path")
                btn_copy.setFixedSize(32, 32)
                btn_copy.clicked.connect(lambda _, p=p_val: self._action_copy_path(p))
                row_layout.addWidget(btn_copy)

                btn_dir = QPushButton()
                btn_dir.setIcon(self._create_svg_icon("folder.svg"))
                btn_dir.setObjectName("action_btn")
                btn_dir.setToolTip("Open containing folder")
                btn_dir.setFixedSize(32, 32)
                btn_dir.clicked.connect(lambda _, p=p_val: self._action_open_folder(p))
                row_layout.addWidget(btn_dir)

            elif dtype == "process":
                p_id = d["pid"]
                p_name = d["name"]
                p_path = c.get("file_path")

                if p_path and os.path.exists(p_path):
                    btn_dir = QPushButton()
                    btn_dir.setIcon(self._create_svg_icon("folder.svg"))
                    btn_dir.setObjectName("action_btn")
                    btn_dir.setToolTip("Open process location")
                    btn_dir.setFixedSize(32, 32)
                    btn_dir.clicked.connect(
                        lambda _, p=p_path: self._action_open_folder(p)
                    )
                    row_layout.addWidget(btn_dir)

                btn_info = QPushButton()
                btn_info.setIcon(self._create_svg_icon("info.svg"))
                btn_info.setObjectName("action_btn")
                btn_info.setToolTip(f"Search web for {p_name}")
                btn_info.setFixedSize(32, 32)
                btn_info.clicked.connect(
                    lambda _, n=p_name: webbrowser.open(
                        f"https://www.google.com/search?q={n}+process+info"
                    )
                )
                row_layout.addWidget(btn_info)

                btn_kill = QPushButton()
                btn_kill.setIcon(self._create_svg_icon("power.svg", color="#f87171"))
                btn_kill.setObjectName("action_btn_danger")
                btn_kill.setToolTip(f"Kill process {p_id}")
                btn_kill.setFixedSize(32, 32)
                btn_kill.setStyleSheet(
                    "background: #450a0a; border: 1px solid #7f1d1d; border-radius: 4px;"
                )
                btn_kill.clicked.connect(
                    lambda _, pid=p_id, n=p_name: self.kill_process(pid, n)
                )
                row_layout.addWidget(btn_kill)

            elif dtype == "process_kill_all":
                p_name = d["name"]
                btn_kill_all = QPushButton("Kill All")
                btn_kill_all.setIcon(
                    self._create_svg_icon("power.svg", color="#ffffff")
                )
                btn_kill_all.setObjectName("action_btn_danger")
                btn_kill_all.setToolTip(f"Kill all instances of {p_name}")
                btn_kill_all.setFixedSize(80, 32)
                btn_kill_all.setStyleSheet(
                    "background: #ef4444; color: white; border-radius: 4px; font-weight: bold; font-size: 10px;"
                )
                btn_kill_all.clicked.connect(
                    lambda _, n=p_name: _kill_all_procs(self, n)
                )
                row_layout.addWidget(btn_kill_all)

            item.setSizeHint(QSize(row_widget.sizeHint().width(), 62))
            self.results_list.setItemWidget(item, row_widget)

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)

        self.results_list.setUpdatesEnabled(True)
        QTimer.singleShot(0, self.lazy_load_visible_icons)

    def populate_tree_results(self, candidates):
        self.results_tree.setUpdatesEnabled(False)
        tree_data = {}
        for c in candidates[:150]:
            path = c.get("path", "")
            if os.path.isabs(path):
                parts = path.split(os.sep)
                current = tree_data
                for i, part in enumerate(parts):
                    if not part and i == 0:
                        continue
                    if part not in current:
                        current[part] = {"_data": None, "_children": {}}
                    if i == len(parts) - 1:
                        current[part]["_data"] = c
                    current = current[part]["_children"]
            else:
                cat = "System & Core"
                if cat not in tree_data:
                    tree_data[cat] = {"_data": None, "_children": {}}
                tree_data[cat]["_children"][c["title"]] = {
                    "_data": c,
                    "_children": {},
                }

        def add_items_to_tree(parent_item, data_dict):
            for name, content in sorted(data_dict.items()):
                item = QTreeWidgetItem(
                    parent_item if parent_item is not None else self.results_tree
                )
                item.setText(0, name)
                if content["_data"]:
                    item.setData(0, Qt.ItemDataRole.UserRole, content["_data"]["data"])
                    file_path = content["_data"].get("file_path")
                    if file_path:
                        ext = os.path.splitext(file_path)[1].lower()
                        cache_key = (
                            file_path if ext in [".exe", ".lnk", ".url"] else ext
                        )
                        if cache_key in self.icon_cache:
                            item.setIcon(0, QIcon(self.icon_cache[cache_key]))
                        else:
                            icon_str = content["_data"].get("icon", "🔹")
                            item.setText(0, f"{icon_str} {name}")
                            if cache_key not in self.pending_icons:
                                self.pending_icons.add(cache_key)
                                worker = IconWorker(file_path, cache_key, self)
                                self.thread_pool.start(worker)
                    else:
                        icon = content["_data"].get("icon", "🔹")
                        item.setText(0, f"{icon} {name}")
                else:
                    item.setIcon(
                        0,
                        self.icon_provider.icon(QFileIconProvider.IconType.Folder),
                    )
                    item.setText(0, name)
                    item.setForeground(0, QColor("#60a5fa"))

                if content["_children"]:
                    add_items_to_tree(item, content["_children"])
                    item.setExpanded(True)

        add_items_to_tree(None, tree_data)
        self.results_tree.setUpdatesEnabled(True)

    # ------------------------------------------------------------------
    # Icon lazy loading
    # ------------------------------------------------------------------
    def on_item_hover(self, row):
        pass  # Reserved for future hover metadata

    def lazy_load_visible_icons(self):
        """Load icons only for items visible in the viewport."""
        if not hasattr(self, "current_candidates"):
            return

        viewport = self.results_list.viewport()
        first_visible = self.results_list.indexAt(viewport.rect().topLeft()).row()
        last_visible = self.results_list.indexAt(viewport.rect().bottomLeft()).row()

        if first_visible < 0:
            first_visible = 0
        if last_visible < 0:
            last_visible = self.results_list.count() - 1

        start = max(0, first_visible - 5)
        end = min(self.results_list.count(), last_visible + 6)

        for idx in range(start, end):
            item = self.results_list.item(idx)
            if not item:
                continue
            c = item.data(Qt.ItemDataRole.UserRole + 1)
            if not c:
                continue
            file_path = c.get("file_path")
            if not file_path:
                continue

            row_widget = self.results_list.itemWidget(item)
            if not row_widget:
                continue
            icon_label = row_widget.findChild(QLabel, f"icon_{idx}")
            if not icon_label:
                continue
            if icon_label.property("native_loaded"):
                continue

            ext = os.path.splitext(file_path)[1].lower()
            is_dir = os.path.isdir(file_path) if os.path.exists(file_path) else False
            cache_key = (
                "__dir__"
                if is_dir
                else (file_path if ext in [".exe", ".lnk", ".url"] else ext)
            )

            if cache_key in self.icon_cache:
                icon_label.setPixmap(self.icon_cache[cache_key])
                icon_label.setText("")
                icon_label.setStyleSheet("")
                icon_label.setProperty("native_loaded", True)
            elif cache_key not in self.pending_icons:
                self.pending_icons.add(cache_key)
                worker = IconWorker(file_path, cache_key, self)
                worker.setAutoDelete(True)
                self.thread_pool.start(worker)

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------
    def launch_selected(self):
        try:
            if self.view_mode == "tree":
                item = self.results_tree.currentItem()
            else:
                item = self.results_list.currentItem()

            if not item:
                return

            data = (
                item.data(0, Qt.ItemDataRole.UserRole)
                if self.view_mode == "tree"
                else item.data(Qt.ItemDataRole.UserRole)
            )
            if not data:
                return

            should_hide = True
            if data.get("type") in ["filter_toggle", "filter_clear"]:
                should_hide = False

            if should_hide:
                # Save the successful search string
                self.record_search(self.search_input.text())
                self.hide()

            if data.get("type") == "filter_toggle":
                path = data["path"]
                if path in self.modes.get("target_folders", []):
                    self.modes["target_folders"].remove(path)
                else:
                    self.modes["target_folders"].append(path)
                self.save_settings()
                self.show_folder_picker()
                return
            elif data.get("type") == "filter_clear":
                self.modes["target_folders"] = []
                self.save_settings()
                self.show_folder_picker()
                return
            elif data.get("type") == "app":
                if not os.path.exists(data["path"]):
                    raise FileNotFoundError(f"App not found: {data['path']}")
                os.startfile(data["path"])
            # Workspaces removed
            elif data["type"] == "cmd":
                if data["cmd"] == "xexplorer":
                    _launch_xexplorer(self)
                elif data["cmd"] == "reindex_files":
                    _trigger_reindex(self)
                elif data["cmd"] == "regex_helper":
                    _launch_regex(self)
                elif data["cmd"] == "file_ops":
                    _launch_file_ops(self)
                elif data["cmd"] == "archiver":
                    _launch_archiver(self)
                elif data["cmd"] == "color_picker":
                    _launch_color_picker(self)
                elif data["cmd"] == "base64_tool":
                    _launch_base64_tool(self)
                elif data["cmd"] == "chronos_hub":
                    _launch_chronos(self)
                elif data["cmd"] == "img_to_text":
                    self.start_img_to_text()
                elif (
                    data["cmd"].startswith("toggle_")
                    or data["cmd"].startswith("cmd_")
                    or data["cmd"].startswith("ms-settings:")
                    or data["cmd"]
                    in ["flush_dns", "restart_explorer", "toggle_desktop"]
                ):
                    _exec_toggle(self, data["cmd"])
            elif data["type"] == "script":
                self.record_usage(f"script_{data['path']}")
                f_path = data["path"]
                if not os.path.exists(f_path):
                    raise FileNotFoundError(f"Script not found: {f_path}")
                # If it is inside our src package, run it as a module
                if "src" in f_path:
                    rel = os.path.relpath(f_path, PROJECT_ROOT)
                    mod_path = rel.replace(os.sep, ".").rsplit(".", 1)[0]
                    subprocess.Popen([sys.executable, "-m", mod_path])
                else:
                    subprocess.Popen([sys.executable, f_path])
            elif data["type"] == "file":
                self.record_usage(f"file_{data['path']}")
                if not os.path.exists(data["path"]):
                    raise FileNotFoundError(f"File not found: {data['path']}")
                os.startfile(data["path"])
            # Macros removed
            elif data["type"] == "process":
                _kill_proc(self, data["pid"], data["name"])
            elif data["type"] == "process_kill_all":
                _kill_all_procs(self, data["name"])
            elif data["type"] == "ssh":
                self.status_lbl.setText(f"Connecting to {data['host']}...")
                subprocess.Popen(f"start cmd /k ssh {data['host']}", shell=True)
            elif data["type"] == "chronos_log":
                _log_to_chronos(self, data["content"])
            elif data["type"] == "url":
                webbrowser.open(data["url"])
                self.status_lbl.setText(f"Opened URL: {data['url']}")
                self.status_lbl.setStyleSheet("color: #3b82f6; font-weight: bold;")
        except Exception as e:
            self.show()
            self.raise_()
            self.activateWindow()
            self.status_lbl.setText(f"Error: {str(e)}")
            self.status_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")

    # ------------------------------------------------------------------
    # System command delegates
    # ------------------------------------------------------------------
    def execute_system_toggle(self, cmd):
        _exec_toggle(self, cmd)

    def kill_process(self, pid, name):
        _kill_proc(self, pid, name)

    def trigger_reindex(self):
        _trigger_reindex(self)

    def update_process_cache(self, force=False):
        _update_procs(self, force)

    # macro removed

    def _log_to_chronos(self, text):
        _log_to_chronos(self, text)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def apply_theme(self):
        mgr = ThemeManager()
        self.setStyleSheet(get_nexus_theme(mgr))
        # Update theme button label with current theme name
        if hasattr(self, "_theme_btn"):
            self._theme_btn.setText(f"◑ {mgr.theme_data.get('name', mgr.current_theme_name)}")

    def _open_theme_picker(self):
        """Open the VS Code-style floating theme picker."""
        picker = _ThemePickerPopup(self)
        # Position it below the theme button
        btn_pos = self._theme_btn.mapToGlobal(self._theme_btn.rect().bottomLeft())
        picker.move(btn_pos.x(), btn_pos.y() + 4)
        picker.show()
        picker.raise_()

    def _open_settings_folder(self):
        """Open the folder where Nexus settings are stored."""
        settings_dir = os.path.dirname(SETTINGS_FILE)
        if os.path.exists(settings_dir):
            QDesktopServices.openUrl(QUrl.fromLocalFile(settings_dir))
        else:
            self.status_lbl.setText("Settings directory not found")
