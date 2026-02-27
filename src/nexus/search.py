"""Nexus Search — main UI widget with all search, navigation, and launch logic."""

import contextlib
import ctypes
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser

import keyboard
from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
)
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QIcon
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

from src.common.config import (
    APPDATA,
    APPS_CACHE_FILE,
    DB_PATH,
    GHOST_TYPIST_DB,
    ICON_PATH,
    PROJECT_ROOT,
    SEARCH_HISTORY_FILE,
    SETTINGS_FILE,
    USAGE_FILE,
    X_EXPLORER_DB,
)

# Import SearchEngine
from src.common.search_engine import SearchEngine

from .system_commands import (
    execute_system_toggle as _exec_toggle,
)
from .system_commands import (
    kill_process as _kill_proc,
)
from .system_commands import (
    launch_regex_helper as _launch_regex,
)
from .system_commands import (
    log_to_chronos as _log_to_chronos,
)
from .system_commands import (
    run_macro as _run_macro,
)
from .system_commands import (
    trigger_reindex as _trigger_reindex,
)
from .system_commands import (
    update_process_cache as _update_procs,
)
from .themes import get_dark_theme, get_light_theme
from .utils import format_display_name, run_workspace
from .widgets import IconWorker, NexusInput, RainbowFrame


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
            "workspaces": True,
            "files": False,
            "macros": False,
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
        self.is_light_mode = False
        self.load_settings()

        self.usage_stats = {}
        self.load_usage()

        # Search text history for auto-completion
        self.search_history = []
        self.load_search_history()

        # Data cache
        self.workspaces = []
        self.ssh_hosts = []
        self.process_cache = []
        self.last_proc_update = 0
        self.installed_apps = []
        self.load_apps_cache()

        self.scan_ssh_hosts()
        self.load_workspaces()
        self.icon_provider = QFileIconProvider()
        self.icon_cache = {}
        self.search_engine = SearchEngine([X_EXPLORER_DB, DB_PATH])
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(2)
        self.pending_icons = set()

        self.setup_ui()
        self.apply_theme()
        self.center_on_screen()

        # Slow app scanning in background
        threading.Thread(target=self.scan_installed_apps_bg, daemon=True).start()

        # Debounce timer for search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

        self.last_search_time = 0
        self.current_candidates = []

        # Global input redirect
        keyboard.on_press(self.on_global_key)

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
        """Aggressively grab focus on Windows."""
        self.show()
        self.raise_()
        self.activateWindow()

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
                            {k: v for k, v in data.items() if k != "light_mode"}
                        )
                        self.is_light_mode = data.get("light_mode", False)
        except Exception:
            pass

    def save_settings(self):
        try:
            settings = self.modes.copy()
            settings["light_mode"] = self.is_light_mode
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f)
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
    # Workspace loading
    # ------------------------------------------------------------------
    def load_workspaces(self):
        try:
            if os.path.exists(DB_PATH):
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, name FROM workspaces")
                    self.workspaces = [
                        {"id": r[0], "name": r[1]} for r in cursor.fetchall()
                    ]
        except Exception:
            self.workspaces = []

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
            ("apps", "Apps"),
            ("workspaces", "Workspaces"),
            ("files", "Files"),
            ("macros", "Macros"),
            ("scripts", "Scripts"),
            ("ssh", "SSH"),
            ("processes", "Processes"),
            ("toggles", "System"),
        ]
        for key, label in modes_metadata:
            btn = QPushButton(label)
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

        self.btn_view_toggle = QPushButton("Tree View")
        self.btn_view_toggle.setCheckable(True)
        self.btn_view_toggle.setObjectName("mode_btn")
        self.btn_view_toggle.clicked.connect(self.toggle_view_mode)

        fb_layout.addWidget(self.btn_f_only)
        fb_layout.addWidget(self.btn_d_only)
        fb_layout.addWidget(self.btn_view_toggle)
        fb_layout.addWidget(self.btn_pick_folders)
        left_layout.addWidget(self.filter_bar)

        self.splitter.addWidget(self.left_panel)

        # ── Right Panel (input + results + footer) ──
        right_panel = QWidget()
        right_panel.setObjectName("right_panel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 14, 16, 10)
        right_layout.setSpacing(10)

        # Toggle button (in right panel top-left, visible when panel hidden)
        top_bar = QHBoxLayout()
        self.btn_side_toggle = QPushButton("☰")
        self.btn_side_toggle.setObjectName("panel_toggle")
        self.btn_side_toggle.setFixedSize(28, 24)
        self.btn_side_toggle.setToolTip("Toggle Sources Panel")
        self.btn_side_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_side_toggle.clicked.connect(self.toggle_side_panel)
        top_bar.addWidget(self.btn_side_toggle)
        top_bar.addStretch()
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
        self.results_list.itemDoubleClicked.connect(self.launch_selected)
        self.results_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_list.customContextMenuRequested.connect(self.show_context_menu)

        self.results_tree = QTreeWidget()
        self.results_tree.setObjectName("nexus_tree")
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
        self.perform_search()

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

        item = QListWidgetItem("✅ Search EVERYTHING (Clear Filters)")
        item.setData(Qt.ItemDataRole.UserRole, {"type": "filter_clear"})
        self.results_list.addItem(item)

        for path in managed:
            is_active = path in self.modes.get("target_folders", [])
            state = "⭐ " if is_active else "📁 "
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
        """Auto-hide when clicking outside."""
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
        data = item.data(Qt.ItemDataRole.UserRole)
        self._show_common_menu(pos, data, self.results_list)

    def show_tree_context_menu(self, pos):
        item = self.results_tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            # Intermediate folder node — reconstruct path from tree hierarchy
            parts = []
            node = item
            while node:
                parts.insert(0, node.text(0))
                node = node.parent()
            folder_path = os.sep.join(parts)
            if os.path.isdir(folder_path):
                data = {"type": "file", "path": folder_path}
        self._show_common_menu(pos, data, self.results_tree)

    def _show_common_menu(self, pos, data, parent_widget):
        if not data:
            return
        menu = QMenu(self)
        if self.is_light_mode:
            menu.setStyleSheet(
                "QMenu { background-color: #ffffff; color: #111827; border: 1px solid #d1d5db; "
                "border-radius: 8px; } QMenu::item { padding: 6px 20px; } "
                "QMenu::item:selected { background-color: #3b82f6; color: white; }"
            )
        else:
            menu.setStyleSheet(
                "QMenu { background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; "
                "border-radius: 8px; } QMenu::item { padding: 6px 20px; } "
                "QMenu::item:selected { background-color: #3b82f6; color: white; }"
            )

        path = data.get("path")
        if path:
            copy_path = menu.addAction("🔗 Copy Path")
            copy_name = menu.addAction("📄 Copy File Name")
            open_loc = menu.addAction("📁 Open File Location")
            search_here = menu.addAction("🎯 Search ONLY in this Folder")

            action = menu.exec(parent_widget.mapToGlobal(pos))
            if not action:
                return

            # Most actions hide the UI
            if action != search_here:
                self.hide()

            if action == copy_path:
                norm_path = os.path.normpath(path)
                QApplication.clipboard().setText(norm_path)
                short = norm_path if len(norm_path) < 50 else "…" + norm_path[-45:]
                self.status_lbl.setText(f"✓ Copied path: {short}")
            elif action == copy_name:
                QApplication.clipboard().setText(os.path.basename(path))
                self.status_lbl.setText("✓ Copied file name to clipboard")
            elif action == open_loc:
                norm_path = os.path.normpath(path)
                if os.path.exists(norm_path):
                    if os.path.isdir(norm_path):
                        os.startfile(norm_path)
                    else:
                        # Professional "Open and Select" on Windows
                        subprocess.Popen(f'explorer /select,"{norm_path}"')
                else:
                    self.status_lbl.setText("Path not found on disk")
            elif action == search_here:
                dir_path = path if os.path.isdir(path) else os.path.dirname(path)
                self.modes["target_folders"] = [dir_path]
                self.modes["files"] = True
                self.search_input.setText("")
                self.search_input.setFocus()
                self.status_lbl.setText(
                    f"Locked Search to: {os.path.basename(dir_path)}"
                )
                self.save_settings()

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
        self.load_workspaces()
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
                    "icon": "🏆",
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
                    "icon": "📁" if is_dir else "📄",
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
                    "icon": "🌐",
                    "color": "#3b82f6",
                    "data": {"type": "url", "url": url},
                }
            )

        # Prefix logic
        prefixes = {
            ":w": "workspaces",
            ":f": "files",
            ":m": "macros",
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
                "💥 Executioner Mode • Select and Press Enter to Finish It"
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
                            "icon": "🌐",
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
                            "icon": "📦",
                            "data": {"type": "app", "path": app["path"]},
                        }
                    )

        # 2. System Commands & Toggles
        if active_modes.get("toggles") or search.startswith(">"):
            score_base = 1100 if search.startswith(">") or not search else 500
            t_terms = [t.strip(">") for t in terms]

            mgmt_cmds = [
                (
                    "Re-index Files (X-Explorer)",
                    "Refresh file search cache",
                    "reindex_files",
                    "▸",
                    "#60a5fa",
                ),
                (
                    "Regex Helper",
                    "Offline Pattern Tester",
                    "regex_helper",
                    "🔬",
                    "#f472b6",
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
                    "Toggle Dark / Light Mode",
                    "Theme",
                    "toggle_dark_mode",
                    "◐",
                    ["dark", "light", "theme", "night"],
                ),
                (
                    "Toggle Hidden Files",
                    "Explorer",
                    "toggle_hidden_files",
                    "◉",
                    ["hidden", "files", "view", "explorer"],
                ),
                (
                    "Toggle Desktop Icons",
                    "Desktop",
                    "toggle_desktop_icons",
                    "▦",
                    ["icons", "desktop", "shortcuts"],
                ),
                (
                    "Toggle System Mute",
                    "Audio",
                    "toggle_mute",
                    "◉",
                    ["mute", "audio", "volume", "sound"],
                ),
                (
                    "Show / Hide Desktop",
                    "Windows",
                    "toggle_desktop",
                    "▣",
                    ["desktop", "reveal", "hide"],
                ),
                (
                    "Restart Windows Explorer",
                    "System",
                    "restart_explorer",
                    "↻",
                    ["restart", "explorer", "refresh", "taskbar"],
                ),
                (
                    "Flush DNS Cache",
                    "Network",
                    "flush_dns",
                    "↻",
                    ["dns", "flush", "network", "reset"],
                ),
                (
                    "Lock Workstation",
                    "Security",
                    "cmd_lock",
                    "▸",
                    ["lock", "security", "sign out"],
                ),
                (
                    "Put PC to Sleep",
                    "Power",
                    "cmd_sleep",
                    "▸",
                    ["sleep", "standby", "power"],
                ),
                (
                    "Restart Computer",
                    "Power",
                    "cmd_restart",
                    "↻",
                    ["restart", "reboot", "power"],
                ),
                (
                    "Shutdown System",
                    "Power",
                    "cmd_shutdown",
                    "■",
                    ["shutdown", "power off", "exit"],
                ),
                (
                    "Windows Settings",
                    "ms-settings",
                    "ms-settings:default",
                    "▸",
                    ["settings", "config", "windows"],
                ),
                (
                    "Display Settings",
                    "ms-settings",
                    "ms-settings:display",
                    "▸",
                    ["display", "monitor", "resolution", "brightness"],
                ),
                (
                    "Wi-Fi Settings",
                    "ms-settings",
                    "ms-settings:network-wifi",
                    "▸",
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

        # 3. Workspaces
        if active_modes.get("workspaces"):
            for ws in self.workspaces:
                if matches_all_terms(ws["name"], terms):
                    score = 1000
                    if search_term and ws["name"].lower() == search_term:
                        score += 500
                    score += self.get_usage_boost(f"ws_{ws['id']}")
                    candidates.append(
                        {
                            "score": score,
                            "title": ws["name"],
                            "path": "Local Workspace",
                            "icon": "🚀",
                            "data": {"type": "workspace", "id": ws["id"]},
                        }
                    )

        # 4. Local Scripts
        if active_modes.get("scripts"):
            # Include project root, core packages, and user scripts
            script_paths = [
                PROJECT_ROOT,
                os.path.join(PROJECT_ROOT, "src", "xexplorer"),
                os.path.join(PROJECT_ROOT, "src", "regex_helper"),
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
                                    "icon": "🐍",
                                    "data": {"type": "script", "path": f_path},
                                }
                            )

        # 5. Ghost Macros
        if active_modes.get("macros") and os.path.exists(GHOST_TYPIST_DB):
            try:
                with sqlite3.connect(GHOST_TYPIST_DB) as conn:
                    cursor = conn.cursor()
                    sql = "SELECT id, name, hotkey FROM macros"
                    if terms:
                        sql += " WHERE " + " AND ".join(["name LIKE ?" for _ in terms])
                        cursor.execute(sql, [f"%{t}%" for t in terms])
                    else:
                        cursor.execute(sql + " LIMIT 10")
                    for mid, name, hotkey in cursor.fetchall():
                        score = 900
                        if search_term and name.lower() == search_term:
                            score += 500
                        score += self.get_usage_boost(f"macro_{mid}")
                        candidates.append(
                            {
                                "score": score,
                                "title": name,
                                "path": f"Ghost Macro • {hotkey if hotkey else ''}",
                                "icon": "⌨️",
                                "data": {"type": "macro", "id": mid, "name": name},
                            }
                        )
            except Exception:
                pass

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
                icon = "🌐" if self._is_unc_path(f_path) else "📁" if is_dir else "📄"

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
                        "title": f"📄 {f_name}",
                        "path": f"Found in content • {f_path}",
                        "file_path": f_path,
                        "icon": "📄",
                        "data": {"type": "file", "path": f_path},
                    }
                )

        # 7. Processes
        if active_modes.get("processes") and terms:
            _update_procs(self)
            for p in self.process_cache:
                if matches_all_terms(p["name"], terms):
                    candidates.append(
                        {
                            "score": 700
                            + (200 if p["name"].lower().startswith(search_term) else 0),
                            "title": p["name"],
                            "path": f"PID: {p['pid']} • {p['mem']} • 💀 KILL",
                            "icon": "💥",
                            "color": "#ef4444",
                            "data": {
                                "type": "process",
                                "pid": p["pid"],
                                "name": p["name"],
                            },
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
    def _is_unc_path(self, path: str) -> bool:
        """Return True if *path* is a UNC / network path."""
        return path.startswith("\\\\") or path.startswith("//")

    def _action_copy_path(self, path: str):
        norm = os.path.normpath(path)
        QApplication.clipboard().setText(norm)
        short = norm if len(norm) < 50 else "…" + norm[-45:]
        self.status_lbl.setText(f"✓ Copied: {short}")

    def _action_copy_dir(self, path: str):
        d = path if os.path.isdir(path) else os.path.dirname(path)
        norm = os.path.normpath(d)
        QApplication.clipboard().setText(norm)
        short = norm if len(norm) < 50 else "…" + norm[-45:]
        self.status_lbl.setText(f"✓ Copied: {short}")

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

            icon_text = c.get("icon", "🔹")
            file_path = c.get("file_path") or c["data"].get("path", "")
            if file_path and self._is_unc_path(file_path):
                icon_text = "🌐"  # network directory
            icon_label.setText(icon_text)
            icon_label.setStyleSheet("font-size: 20px; color: #9ca3af;")
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
                display_path = f"🌐 {display_path}"
            path_lbl = QLabel(format_display_name(display_path, max_len=72))
            path_lbl.setObjectName("item_path")

            text_container.addWidget(title_lbl)
            text_container.addWidget(path_lbl)
            row_layout.addLayout(text_container, stretch=1)

            # -- Inline action buttons (only for items with a path) --
            path_val = c["data"].get("path", "")
            if path_val and c["data"].get("type") in ("file", "app", "script", None):
                btn_copy = QPushButton("📋")
                btn_copy.setObjectName("action_btn")
                btn_copy.setToolTip("Copy path")
                btn_copy.setFixedSize(30, 26)
                btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_copy.clicked.connect(
                    lambda _, p=path_val: self._action_copy_path(p)
                )
                row_layout.addWidget(btn_copy)

                btn_dir = QPushButton("📂")
                btn_dir.setObjectName("action_btn")
                btn_dir.setToolTip("Open containing folder")
                btn_dir.setFixedSize(30, 26)
                btn_dir.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_dir.clicked.connect(
                    lambda _, p=path_val: self._action_open_folder(p)
                )
                row_layout.addWidget(btn_dir)

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
            if icon_label.pixmap() and not icon_label.pixmap().isNull():
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
            elif cache_key not in self.pending_icons:
                self.pending_icons.add(cache_key)
                worker = IconWorker(file_path, cache_key, self)
                worker.setAutoDelete(True)
                self.thread_pool.start(worker)

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------
    def launch_selected(self):
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
            os.startfile(data["path"])
        elif data.get("type") == "workspace":
            self.record_usage(f"ws_{data['id']}")
            run_workspace(data["id"])
        elif data["type"] == "cmd":
            if data["cmd"] == "reindex_files":
                _trigger_reindex(self)
            elif data["cmd"] == "regex_helper":
                _launch_regex(self)
            elif (
                data["cmd"].startswith("toggle_")
                or data["cmd"].startswith("cmd_")
                or data["cmd"].startswith("ms-settings:")
                or data["cmd"] in ["flush_dns", "restart_explorer", "toggle_desktop"]
            ):
                _exec_toggle(self, data["cmd"])
        elif data["type"] == "script":
            self.record_usage(f"script_{data['path']}")
            f_path = data["path"]
            # If it is inside our src package, run it as a module
            if "src" in f_path:
                rel = os.path.relpath(f_path, PROJECT_ROOT)
                mod_path = rel.replace(os.sep, ".").rsplit(".", 1)[0]
                subprocess.Popen([sys.executable, "-m", mod_path])
            else:
                subprocess.Popen([sys.executable, f_path])
        elif data["type"] == "file":
            self.record_usage(f"file_{data['path']}")
            os.startfile(data["path"])
        elif data["type"] == "macro":
            self.record_usage(f"macro_{data['id']}")
            _run_macro(self, data["id"])
        elif data["type"] == "process":
            _kill_proc(self, data["pid"], data["name"])
        elif data["type"] == "ssh":
            self.status_lbl.setText(f"🔗 Connecting to {data['host']}...")
            subprocess.Popen(f"start cmd /k ssh {data['host']}", shell=True)
        elif data["type"] == "chronos_log":
            _log_to_chronos(self, data["content"])
        elif data["type"] == "url":
            webbrowser.open(data["url"])
            self.status_lbl.setText(f"🌐 Opened URL: {data['url']}")
            self.status_lbl.setStyleSheet("color: #3b82f6; font-weight: bold;")

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

    def _run_macro(self, macro_id):
        _run_macro(self, macro_id)

    def _log_to_chronos(self, text):
        _log_to_chronos(self, text)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def apply_theme(self):
        if self.is_light_mode:
            self.setStyleSheet(get_light_theme())
        else:
            self.setStyleSheet(get_dark_theme())
