"""UI-building mixin — setup_ui, mode toggles, folder picker, clock."""

import json
import os
import sqlite3

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QWidget,
)

from src.common.config import ICON_PATH, X_EXPLORER_DB
from src.common.theme import ThemeManager

from .system_commands import update_process_cache as _update_procs
from .widgets import NexusInput, RainbowFrame


class _UIMixin:
    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def setup_ui(self):
        from PyQt6.QtWidgets import QVBoxLayout

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

        # Brand row
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
            ("ssh", "SSH", "server.svg"),
            ("processes", "Processes", "zap.svg"),
            ("toggles", "System", "settings.svg"),
        ]
        mgr = ThemeManager()
        text_sec = mgr.theme_data.get("colors", {}).get("text_secondary", "#78849e")
        for key, label, icon_name in modes_metadata:
            btn = QPushButton(f"  {label}")
            btn.setIcon(self._create_svg_icon(icon_name, color=text_sec))
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

        # Toggle button
        top_bar = QHBoxLayout()
        self.btn_side_toggle = QPushButton("≡")
        self.btn_side_toggle.setObjectName("panel_toggle")
        self.btn_side_toggle.setFixedSize(28, 24)
        self.btn_side_toggle.setToolTip("Toggle Sources Panel")
        self.btn_side_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_side_toggle.clicked.connect(self.toggle_side_panel)
        top_bar.addWidget(self.btn_side_toggle)
        top_bar.addStretch()

        # Theme picker button
        _mgr = ThemeManager()
        self._theme_btn = QPushButton(
            f"◑ {_mgr.theme_data.get('name', _mgr.current_theme_name)}"
        )
        self._theme_btn.setObjectName("theme_btn")
        self._theme_btn.setFixedHeight(24)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setToolTip("Color Theme (Ctrl+K Ctrl+T)")
        self._theme_btn.clicked.connect(self._open_theme_picker)
        top_bar.addWidget(self._theme_btn)

        # Settings folder button
        self._settings_btn = QPushButton("📂")
        self._settings_btn.setObjectName("theme_btn")
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
        self.search_input.setPlaceholderText("Search apps, files, workspaces …")
        self.search_input.textChanged.connect(self.perform_search_instant)
        self.search_input.textChanged.connect(lambda: self.search_timer.start(200))
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

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([160, 760])

        bg_layout.addWidget(self.splitter)
        main_layout.addWidget(self.bg_frame)

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
    # Clock
    # ------------------------------------------------------------------
    def update_clock(self):
        """Update the live clock label."""
        self.clock_lbl.setText(QDateTime.currentDateTime().toString("HH:mm:ss"))
