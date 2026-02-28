"""
X-Explorer — Windows-11-style file explorer with blazing-fast search.
Drop-in replacement for the original x_explorer.py.
"""

import contextlib
import ctypes
import json
import os
import sqlite3
import sys
import time

from PyQt6.QtCore import QFileInfo, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QIcon,
    QPalette,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.archiver.archiver import ArchiverWindow, is_archive
from src.common.config import ASSETS_DIR
from src.common.config import X_EXPLORER_DB as DB_PATH
from src.common.search_engine import SearchEngine
from src.common.theme import ThemeManager
from src.file_ops.file_ops import FileOpsWindow
from src.xexplorer.database import init_db
from src.xexplorer.delegates import DetailsDelegate
from src.xexplorer.icons import Icons
from src.xexplorer.indexer import IndexerWorker
from src.xexplorer.theme import Theme
from src.xexplorer.watcher import LiveCacheUpdater
from src.xexplorer.widgets import (
    ChipBtn,
    DriveWidget,
    EmptyStateWidget,
    IgnoreItemWidget,
    NavBtn,
    RibbonBtn,
    SearchBar,
    SidebarList,
)

try:
    from watchdog.events import FileSystemEventHandler  # noqa: F401
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class XExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.T = Theme(dark=True)
        self.view_mode = "details"
        self.filter_type = "all"
        self._icon_cache: dict[str, QIcon] = {}

        self.setWindowTitle("X-Explorer")
        self.resize(1300, 800)
        self.setMinimumSize(900, 580)
        self.icon_provider = QFileIconProvider()
        self._last_indexing_dur = None

        self._build_all()
        self.load_settings()
        self._apply_theme()
        ThemeManager().theme_changed.connect(self._on_theme_changed)

        icon_path = os.path.join(ASSETS_DIR, "xexplorer.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.observer = None
        if WATCHDOG_AVAILABLE:
            self.start_live_watchers()

        self.search_engine = SearchEngine(DB_PATH)

        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

        QTimer.singleShot(100, self.check_args)
        QTimer.singleShot(200, self.update_stats)

    # ──────────────────────────────────────────────────────────────────────────
    #  BUILD
    # ──────────────────────────────────────────────────────────────────────────

    def _build_all(self):
        self._build_titlebar_area()
        self._build_central()
        self._build_statusbar()

    def _build_titlebar_area(self):
        # Single unified toolbar row
        self._ribbon = QToolBar("Ribbon")
        self._ribbon.setMovable(False)
        self._ribbon.setFloatable(False)
        self._ribbon.setObjectName("ribbon_bar")
        self._ribbon.setFixedHeight(54)

        ribbon_widget = QWidget()
        rbl = QHBoxLayout(ribbon_widget)
        rbl.setContentsMargins(10, 4, 10, 4)
        rbl.setSpacing(4)

        T = self.T

        # App logo + title
        logo_lbl = QLabel()
        logo_lbl.setObjectName("app_logo_lbl")
        logo_lbl.setFixedSize(30, 30)
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lbl.setStyleSheet(
            f"background: {T['accent']}; border-radius: 6px; color: {T['text_on_accent']};"
            f" font-size: 15px; font-weight: 700;"
        )
        logo_lbl.setText("X")
        rbl.addWidget(logo_lbl)

        title_lbl = QLabel("X-Explorer")
        title_lbl.setObjectName("app_title_lbl")
        title_lbl.setStyleSheet(
            f"color: {T['text_primary']}; font-size: 14px; font-weight: 600; padding: 0 6px;"
        )
        rbl.addWidget(title_lbl)

        # Nav buttons
        self._nav_back = NavBtn(Icons.arrow_left(T["text_secondary"]), T, "Back")
        self._nav_fwd = NavBtn(Icons.arrow_right(T["text_secondary"]), T, "Forward")
        self._nav_up = NavBtn(Icons.arrow_up(T["text_secondary"]), T, "Up")
        self._nav_refresh = NavBtn(Icons.refresh(T["text_secondary"]), T, "Refresh")
        self._nav_refresh.clicked.connect(self.update_stats)

        for btn in [self._nav_back, self._nav_fwd, self._nav_up, self._nav_refresh]:
            rbl.addWidget(btn)

        rbl.addSpacing(6)

        # Search bar (center, expanding)
        self._search_bar = SearchBar(T)
        self._search_bar.textChanged.connect(self._on_search_changed)
        rbl.addWidget(self._search_bar, stretch=1)

        rbl.addSpacing(6)

        # View mode buttons
        self._rb_detail = RibbonBtn(
            Icons.view_details(T["text_secondary"], 20), "Details", T
        )
        self._rb_icons = RibbonBtn(
            Icons.view_icons(T["text_secondary"], 20), "Icons", T
        )
        self._rb_tree = RibbonBtn(Icons.view_tree(T["text_secondary"], 20), "Tree", T)
        self._rb_detail.clicked.connect(lambda: self.set_view("details"))
        self._rb_icons.clicked.connect(lambda: self.set_view("icons"))
        self._rb_tree.clicked.connect(lambda: self.set_view("tree"))
        for w in [self._rb_detail, self._rb_icons, self._rb_tree]:
            rbl.addWidget(w)

        def vsep():
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            f.setFixedWidth(1)
            f.setFixedHeight(30)
            f.setObjectName("ribbon_sep")
            return f

        rbl.addWidget(vsep())

        # Action buttons
        self._rb_index = QPushButton("⚡  Index")
        self._rb_index.setObjectName("action_btn_primary")
        self._rb_index.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._rb_index.clicked.connect(self.start_indexing)

        self._rb_stop = QPushButton("■  Stop")
        self._rb_stop.setObjectName("action_btn_secondary")
        self._rb_stop.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._rb_stop.clicked.connect(self.stop_indexing)
        self._rb_stop.setVisible(False)

        self._rb_clear = QPushButton("○  Clear DB")
        self._rb_clear.setObjectName("action_btn_secondary")
        self._rb_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._rb_clear.clicked.connect(self.clear_index)

        self._btn_add_folder = QPushButton("+ Add Folder")
        self._btn_add_folder.setObjectName("action_btn_accent")
        self._btn_add_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_add_folder.clicked.connect(self.add_managed_folder)

        for w in [
            self._rb_index,
            self._rb_stop,
            self._rb_clear,
            self._btn_add_folder,
        ]:
            rbl.addWidget(w)

        self._ribbon.addWidget(ribbon_widget)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._ribbon)

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        vl = QVBoxLayout(central)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        vl.addWidget(self._build_filter_row())

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.addWidget(self._build_sidebar())
        self._splitter.addWidget(self._build_results_panel())
        self._splitter.setSizes([220, 1100])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        vl.addWidget(self._splitter, stretch=1)

    def _build_filter_row(self):
        self._filter_row = QWidget()
        self._filter_row.setObjectName("filter_row")
        self._filter_row.setFixedHeight(40)
        hl = QHBoxLayout(self._filter_row)
        hl.setContentsMargins(12, 5, 12, 5)
        hl.setSpacing(4)

        T = self.T
        self._chip_group = QButtonGroup(self)
        self._chips = {}

        for label, ftype in [
            ("All", "all"),
            ("Files", "files"),
            ("Folders", "folders"),
            ("Content Search", "content"),
        ]:
            btn = ChipBtn(label, T)
            if ftype == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda _, t=ftype: self.change_filter(t))
            self._chip_group.addButton(btn)
            self._chips[ftype] = btn
            hl.addWidget(btn)

        # Visual separator
        sep_lbl = QLabel("|")
        sep_lbl.setObjectName("filter_sep_lbl")
        hl.addWidget(sep_lbl)

        # Recent chip
        btn_recent = ChipBtn("Recent", T)
        btn_recent.clicked.connect(lambda: self.change_filter("recent"))
        self._chip_group.addButton(btn_recent)
        self._chips["recent"] = btn_recent
        hl.addWidget(btn_recent)

        hl.addStretch()

        # Sort by label + combo
        sort_lbl = QLabel("Sort by")
        sort_lbl.setObjectName("sort_by_lbl")
        hl.addWidget(sort_lbl)

        self._sort_combo = QComboBox()
        self._sort_combo.setObjectName("sort_combo")
        self._sort_combo.addItems(["Name", "Type", "Size", "Modified"])
        self._sort_combo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        hl.addWidget(self._sort_combo)

        return self._filter_row

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar_frame")
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(300)
        vl = QVBoxLayout(sidebar)
        vl.setContentsMargins(0, 8, 0, 8)
        vl.setSpacing(0)

        T = self.T

        def section(text):
            lbl = QLabel(text)
            lbl.setObjectName("section_lbl")
            lbl.setContentsMargins(12, 8, 0, 4)
            return lbl

        vl.addWidget(section("DRIVES"))
        self.folder_list = SidebarList(T)
        self.folder_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self.show_folder_ctx)
        self.folder_list.itemSelectionChanged.connect(self.perform_search)
        vl.addWidget(self.folder_list, stretch=2)

        self._btn_add_drive = QPushButton("+ Add folder")
        self._btn_add_drive.setObjectName("sidebar_action")
        self._btn_add_drive.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_add_drive.clicked.connect(self.add_managed_folder)
        vl.addWidget(self._btn_add_drive)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        vl.addWidget(sep)

        vl.addWidget(section("IGNORE LIST"))
        self.ignore_list = SidebarList(T)
        self.ignore_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ignore_list.customContextMenuRequested.connect(self.show_ignore_ctx)
        vl.addWidget(self.ignore_list, stretch=3)

        self._btn_add_ignore = QPushButton("+ Add rule")
        self._btn_add_ignore.setObjectName("sidebar_action")
        self._btn_add_ignore.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_add_ignore.clicked.connect(self.add_ignore_rule)
        vl.addWidget(self._btn_add_ignore)

        return sidebar

    def _build_results_panel(self):
        container = QWidget()
        container.setObjectName("results_panel")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        T = self.T

        # ── Details view ────────────────────────────────────────────────────
        self._details = QTreeWidget()
        self._details.setObjectName("details_view")
        self._details.setRootIsDecorated(False)
        self._details.setUniformRowHeights(True)
        self._details.setAlternatingRowColors(True)
        self._details.setHeaderLabels(["Name", "Type", "Size", "Modified"])
        self._details.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._details.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._details.setSortingEnabled(True)
        self._details.setItemDelegate(DetailsDelegate(T))
        self._details.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self._details.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._details.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._details.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._details.setColumnWidth(0, 340)
        self._details.setColumnWidth(1, 90)
        self._details.setColumnWidth(2, 90)
        self._details.customContextMenuRequested.connect(lambda p: self._ctx_details(p))
        self._details.itemDoubleClicked.connect(
            lambda item: self._open_path(item.data(0, Qt.ItemDataRole.UserRole))
        )

        # ── Icons view ───────────────────────────────────────────────────────
        self._icons_view = QListWidget()
        self._icons_view.setObjectName("icons_view")
        self._icons_view.setViewMode(QListWidget.ViewMode.IconMode)
        self._icons_view.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._icons_view.setSpacing(6)
        self._icons_view.setGridSize(QSize(100, 86))
        self._icons_view.setIconSize(QSize(40, 40))
        self._icons_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._icons_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._icons_view.customContextMenuRequested.connect(
            lambda p: self._ctx_icons(p)
        )
        self._icons_view.itemDoubleClicked.connect(
            lambda item: self._open_path(item.data(Qt.ItemDataRole.UserRole))
        )

        # ── Tree view ────────────────────────────────────────────────────────
        self._tree_view = QTreeWidget()
        self._tree_view.setObjectName("tree_view")
        self._tree_view.setHeaderLabels(["Name", "Full Path"])
        self._tree_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree_view.customContextMenuRequested.connect(
            lambda p: self._ctx_tree(p, self._tree_view)
        )
        self._tree_view.itemDoubleClicked.connect(
            lambda item: self._open_path(item.data(0, Qt.ItemDataRole.UserRole))
        )
        self._tree_view.setColumnWidth(0, 300)

        # ── Empty state ──────────────────────────────────────────────────────
        self._empty_state = EmptyStateWidget(T)
        self._empty_state.run_indexer.connect(self.start_indexing)
        self._empty_state.clear_db.connect(self.clear_index)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._details)  # 0
        self._stack.addWidget(self._icons_view)  # 1
        self._stack.addWidget(self._tree_view)  # 2
        self._stack.addWidget(self._empty_state)  # 3

        vl.addWidget(self._stack)
        return container

    def _build_statusbar(self):
        sb = QStatusBar()
        sb.setObjectName("main_sb")
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setObjectName("status_lbl")

        self._progress = QProgressBar()
        self._progress.setFixedSize(160, 6)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)

        self._live_dot = QLabel()
        self._live_dot.setPixmap(Icons.live_dot(8))
        self._live_dot.setVisible(WATCHDOG_AVAILABLE)

        self._live_lbl = QLabel("Live Sync")
        self._live_lbl.setObjectName("live_lbl")
        self._live_lbl.setVisible(WATCHDOG_AVAILABLE)

        sb.addWidget(self._status_lbl, 1)
        sb.addPermanentWidget(self._progress)
        sb.addPermanentWidget(self._live_dot)
        sb.addPermanentWidget(self._live_lbl)

    # ──────────────────────────────────────────────────────────────────────────
    #  THEMING
    # ──────────────────────────────────────────────────────────────────────────

    def _on_theme_changed(self):
        self._icon_cache.clear()
        self._apply_theme()

    def _apply_theme(self):
        T = self.T

        # Nav buttons
        self._nav_back.setPixmap(Icons.arrow_left(T["text_secondary"]))
        self._nav_fwd.setPixmap(Icons.arrow_right(T["text_secondary"]))
        self._nav_up.setPixmap(Icons.arrow_up(T["text_secondary"]))
        self._nav_refresh.setPixmap(Icons.refresh(T["text_secondary"]))

        # View mode RibbonBtns
        self._rb_detail.setPixmap(Icons.view_details(T["text_secondary"], 20))
        self._rb_icons.setPixmap(Icons.view_icons(T["text_secondary"], 20))
        self._rb_tree.setPixmap(Icons.view_tree(T["text_secondary"], 20))
        for w in [self._rb_detail, self._rb_icons, self._rb_tree]:
            w._theme = T
            w.update()

        # Sidebar lists
        self.folder_list._theme = T
        self.folder_list.update_style()
        self.ignore_list._theme = T
        self.ignore_list.update_style()

        # Update DriveWidgets in folder_list
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            w = self.folder_list.itemWidget(item)
            if isinstance(w, DriveWidget):
                w.update_theme(T)

        # Update IgnoreItemWidgets in ignore_list
        for i in range(self.ignore_list.count()):
            item = self.ignore_list.item(i)
            w = self.ignore_list.itemWidget(item)
            if isinstance(w, IgnoreItemWidget):
                w.update_theme(T)

        # Chips
        for btn in self._chips.values():
            btn._theme = T
            btn.update_style()

        # Delegate
        self._details.itemDelegate()._theme = T  # type: ignore

        # Search bar
        self._search_bar._theme = T
        self._search_bar.apply_input_style()
        self._search_bar.update_theme()

        # Empty state
        self._empty_state.update_theme(T)

        acc = T["accent"]
        qss = f"""
        /* ── App base ── */
        QMainWindow, QWidget {{
            background: {T["bg_base"]};
            color: {T["text_primary"]};
            font-family: 'Segoe UI', system-ui, sans-serif;
            font-size: 13px;
        }}

        /* ── Ribbon ── */
        QToolBar#ribbon_bar {{
            background: {T["bg_elevated"]};
            border-bottom: 1px solid {T["border"]};
            padding: 0;
            spacing: 0;
        }}
        QFrame#ribbon_sep {{
            background: {T["border"]};
        }}

        /* ── Action buttons in ribbon ── */
        QPushButton#action_btn_primary {{
            background: {T["accent"]};
            border: none;
            border-radius: 6px;
            padding: 5px 14px;
            color: {T["text_on_accent"]};
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton#action_btn_primary:hover {{
            background: {T["accent_hover"]};
        }}
        QPushButton#action_btn_secondary {{
            background: {T["bg_control"]};
            border: 1px solid {T["border_light"]};
            border-radius: 6px;
            padding: 5px 14px;
            color: {T["text_secondary"]};
            font-size: 12px;
        }}
        QPushButton#action_btn_secondary:hover {{
            background: {T["bg_control_hov"]};
            color: {T["text_primary"]};
        }}
        QPushButton#action_btn_accent {{
            background: transparent;
            border: 1px solid {T["accent"]};
            border-radius: 6px;
            padding: 5px 14px;
            color: {T["accent"]};
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#action_btn_accent:hover {{
            background: {T["accent_subtle"]};
        }}
        QPushButton#action_btn_icon {{
            background: {T["bg_control"]};
            border: 1px solid {T["border"]};
            border-radius: 6px;
        }}
        QPushButton#action_btn_icon:hover {{
            background: {T["bg_control_hov"]};
        }}
        QLabel#app_title_lbl {{
            color: {T["text_primary"]};
        }}

        /* ── Filter row ── */
        QWidget#filter_row {{
            background: {T["bg_base"]};
            border-bottom: 1px solid {T["border"]};
        }}
        QLabel#filter_sep_lbl {{
            color: {T["border_light"]};
            font-size: 14px;
            padding: 0 2px;
        }}
        QLabel#sort_by_lbl {{
            color: {T["text_secondary"]};
            font-size: 12px;
        }}
        QComboBox#sort_combo {{
            background: {T["bg_control"]};
            border: 1px solid {T["border"]};
            border-radius: 5px;
            padding: 3px 8px;
            color: {T["text_primary"]};
            font-size: 12px;
            min-width: 90px;
        }}
        QComboBox#sort_combo::drop-down {{
            border: none;
            width: 18px;
        }}
        QComboBox QAbstractItemView {{
            background: {T["bg_elevated"]};
            border: 1px solid {T["border_light"]};
            color: {T["text_primary"]};
            selection-background-color: {T["accent"]};
            selection-color: {T["text_on_accent"]};
        }}

        /* ── Sidebar ── */
        QFrame#sidebar_frame {{
            background: {T["sidebar_bg"]};
            border-right: 1px solid {T["border"]};
        }}
        QLabel#section_lbl {{
            color: {T["text_secondary"]};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.8px;
        }}
        QFrame#sidebar_sep {{
            color: {T["border"]};
            margin: 4px 10px;
        }}
        QPushButton#sidebar_action {{
            background: transparent;
            border: none;
            text-align: left;
            padding: 4px 12px;
            color: {acc};
            font-size: 12px;
        }}
        QPushButton#sidebar_action:hover {{
            color: {T["accent_hover"]};
        }}

        /* ── Details view ── */
        QTreeWidget#details_view {{
            background: {T["bg_elevated"]};
            alternate-background-color: {T["row_alt"]};
            border: none;
            outline: none;
            show-decoration-selected: 1;
        }}
        QTreeWidget#details_view::item {{ border: none; }}
        QHeaderView::section {{
            background: {T["bg_overlay"]};
            color: {T["text_secondary"]};
            border: none;
            border-bottom: 1px solid {T["border"]};
            border-right: 1px solid {T["border"]};
            padding: 5px 8px;
            font-size: 12px;
            font-weight: 600;
        }}
        QHeaderView::section:hover {{
            background: {T["bg_control_hov"]};
        }}

        /* ── Icons view ── */
        QListWidget#icons_view {{
            background: {T["bg_elevated"]};
            border: none;
            outline: none;
        }}
        QListWidget#icons_view::item {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 5px;
            color: {T["text_primary"]};
            padding: 4px;
        }}
        QListWidget#icons_view::item:hover {{
            background: {T["bg_control_hov"]};
            border-color: {T["border"]};
        }}
        QListWidget#icons_view::item:selected {{
            background: {T["sel_bg"]};
            border-color: {acc};
            color: {T["text_primary"]};
        }}

        /* ── Tree view ── */
        QTreeWidget#tree_view {{
            background: {T["bg_elevated"]};
            border: none;
            outline: none;
        }}
        QTreeWidget#tree_view::item {{
            padding: 3px 4px;
            color: {T["text_primary"]};
        }}
        QTreeWidget#tree_view::item:hover  {{ background: {T["bg_control_hov"]}; }}
        QTreeWidget#tree_view::item:selected {{ background: {T["sel_bg"]}; color: {T["text_primary"]}; }}

        /* ── Results panel ── */
        QWidget#results_panel {{ background: {T["bg_elevated"]}; }}

        /* ── Status bar ── */
        QStatusBar#main_sb {{
            background: {T["bg_elevated"]};
            border-top: 1px solid {T["border"]};
            min-height: 24px;
        }}
        QLabel#status_lbl {{
            color: {T["text_secondary"]};
            font-size: 12px;
            padding: 0 8px;
        }}
        QLabel#live_lbl {{
            color: {T["success"]};
            font-size: 11px;
            padding: 0 6px;
        }}

        /* ── Progress bar (global) ── */
        QProgressBar {{
            background: {T["border"]};
            border: none;
            border-radius: 3px;
        }}
        QProgressBar::chunk {{
            background: {acc};
            border-radius: 3px;
        }}

        /* ── Splitter ── */
        QSplitter::handle {{ background: {T["border"]}; }}

        /* ── Menus ── */
        QMenu {{
            background: {T["bg_elevated"]};
            border: 1px solid {T["border_light"]};
            border-radius: 8px;
            padding: 5px;
            color: {T["text_primary"]};
        }}
        QMenu::item {{ padding: 6px 20px 6px 12px; border-radius: 4px; font-size: 13px; }}
        QMenu::item:selected {{ background: {acc}; color: {T["text_on_accent"]}; }}
        QMenu::separator {{ height: 1px; background: {T["border"]}; margin: 4px 0; }}

        /* ── Scrollbars ── */
        QScrollBar:vertical {{
            background: transparent; width: 6px; border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {T["border_light"]}; border-radius: 3px; min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {T["text_secondary"]}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent; height: 6px; border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {T["border_light"]}; border-radius: 3px; min-width: 24px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        /* ── Dialogs ── */
        QMessageBox {{ background: {T["bg_elevated"]}; }}
        QDialog {{ background: {T["bg_elevated"]}; }}
        """
        self.setStyleSheet(qss)

        # ── Windows Title Bar & Palette Sync ──
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                # DWMWA_USE_IMMERSIVE_DARK_MODE constants
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19

                value = ctypes.c_int(1 if T.dark else 0)
                # Try setting both for maximum compatibility across Windows 10/11 versions
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    DWMWA_USE_IMMERSIVE_DARK_MODE,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
            except Exception:
                pass

        app_inst = QApplication.instance()
        if app_inst:
            pal = app_inst.palette()
            bg = QColor(T["bg_elevated"])
            fg = QColor(T["text_primary"])
            base = QColor(T["bg_base"])

            pal.setColor(QPalette.ColorRole.Window, bg)
            pal.setColor(QPalette.ColorRole.WindowText, fg)
            pal.setColor(QPalette.ColorRole.Base, base)
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor(T["row_alt"]))
            pal.setColor(QPalette.ColorRole.Text, fg)
            pal.setColor(QPalette.ColorRole.Button, bg)
            pal.setColor(QPalette.ColorRole.ButtonText, fg)
            pal.setColor(QPalette.ColorRole.Highlight, QColor(T["accent"]))
            pal.setColor(
                QPalette.ColorRole.HighlightedText, QColor(T["text_on_accent"])
            )
            app_inst.setPalette(pal)

    # ──────────────────────────────────────────────────────────────────────────
    #  ICON HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _folder_icon(self, size=20) -> QIcon:
        key = f"folder_{size}"
        if key not in self._icon_cache:
            # Fallback to nexus provider
            icon = self.icon_provider.icon(QFileIconProvider.IconType.Folder)
            self._icon_cache[key] = icon
        return self._icon_cache[key]

    def _file_icon(self, name: str, size=20) -> QIcon:
        _, ext = os.path.splitext(name)
        key = f"file_{ext}_{size}"
        if key not in self._icon_cache:
            # Create a temp file to get the real system icon

            # We can use the actual path if it exists, otherwise use the provider with extension
            # For now, let's try the simple extension-based provider if possible,
            # or just use the generic icon. Nexus uses QFileInfo.
            icon = self.icon_provider.icon(QFileIconProvider.IconType.File)
            self._icon_cache[key] = icon
        return self._icon_cache[key]

    def _ext_type(self, path, is_dir):
        if is_dir:
            return "Folder"
        _, ext = os.path.splitext(path)
        return (ext.upper().lstrip(".") + " File") if ext else "File"

    # ──────────────────────────────────────────────────────────────────────────
    #  SETTINGS
    # ──────────────────────────────────────────────────────────────────────────

    def _add_drive_item(self, path: str, label: str):
        """Add a drive/folder item with custom DriveWidget to folder_list."""
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        w = DriveWidget(path, label, self.T)
        item.setSizeHint(w.sizeHint())
        self.folder_list.addItem(item)
        self.folder_list.setItemWidget(item, w)

    def _add_ignore_item(self, rule: str, checked: bool = True):
        """Add an ignore rule with toggle switch to ignore_list."""
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, rule)
        item.setData(Qt.ItemDataRole.UserRole + 1, "1" if checked else "0")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        w = IgnoreItemWidget(rule, checked, self.T)
        w.stateChanged.connect(
            lambda st, i=item: (
                i.setData(Qt.ItemDataRole.UserRole + 1, "1" if st else "0"),
                self.save_settings(),
            )
        )
        # Ensure enough vertical space to prevent clumping/overlapping
        item.setSizeHint(QSize(100, 32))
        self.ignore_list.addItem(item)
        self.ignore_list.setItemWidget(item, w)

    def load_settings(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("SELECT path, last_indexed FROM folder_stats")
        {r[0]: r[1] for r in c.fetchall()}

        c.execute("SELECT value FROM settings WHERE key='folders'")
        res = c.fetchone()
        if res:
            try:
                for f in json.loads(res[0]):
                    path = f.get("path", "")
                    label = f.get("label", path)
                    self._add_drive_item(path, label)
            except (json.JSONDecodeError, TypeError):
                pass

        # Ignore list defaults
        win_dir = os.environ.get("SYSTEMROOT", "C:\\Windows")
        prog_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
        prog_x86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
        defaults = [
            "node_modules",
            "venv",
            ".venv",
            "env",
            "__pycache__",
            ".git",
            ".svn",
            ".idea",
            ".vscode",
            "dist",
            "build",
            "AppData",
            "Local Settings",
            "System Volume Information",
            "$RECYCLE.BIN",
            ".exe",
            ".dll",
            ".sys",
            ".tmp",
            ".pyc",
            win_dir,
            prog_files,
            prog_x86,
            "C:\\MSOCache",
            "C:\\$Recycle.Bin",
        ]

        c.execute("SELECT value FROM settings WHERE key='ignore'")
        res = c.fetchone()
        current = {}
        if res:
            for raw in res[0].split("|"):
                if ":" in raw:
                    rule, st = raw.rsplit(":", 1)
                    current[rule] = st
                elif raw:
                    current[raw] = "1"
        for d in defaults:
            if d not in current:
                current[d] = "1"

        for rule in sorted(current.keys(), key=str.lower):
            self._add_ignore_item(rule, current[rule] == "1")

        self.save_settings()
        conn.close()

    def save_settings(self, *_):
        folders = []
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            w = self.folder_list.itemWidget(item)
            if hasattr(w, "_name_lbl"):
                label = w._name_lbl.text()
            elif hasattr(w, "text") and callable(w.text):
                label = w.text()
            else:
                label = path or ""
            folders.append({"path": path, "state": "1", "label": label})

        ignores = []
        for i in range(self.ignore_list.count()):
            item = self.ignore_list.item(i)
            rule = item.data(Qt.ItemDataRole.UserRole)
            st = item.data(Qt.ItemDataRole.UserRole + 1) or "1"
            ignores.append(f"{rule}:{st}")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO settings VALUES(?,?)",
            ("folders", json.dumps(folders)),
        )
        c.execute(
            "INSERT OR REPLACE INTO settings VALUES(?,?)", ("ignore", "|".join(ignores))
        )

        conn.commit()
        conn.close()

    # ──────────────────────────────────────────────────────────────────────────
    #  FOLDER MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def add_managed_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Folder to Index")
        if path:
            self._add_drive_item(path, path)
            self.save_settings()

    def add_ignore_rule(self):
        rule, ok = QInputDialog.getText(
            self, "Add Ignore Rule", "Folder name, file name, or extension to ignore:"
        )
        if ok and rule:
            self._add_ignore_item(rule, True)
            self.save_settings()

    def scan_drives(self):
        try:
            import string
            from ctypes import windll

            bitmask = windll.kernel32.GetLogicalDrives()
            drives = [
                f"{letter}:\\"
                for letter in string.ascii_uppercase
                if bitmask & (1 << ord(letter) - 65)
            ]
        except Exception:
            drives = ["/"]  # Linux fallback

        existing = [
            self.folder_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.folder_list.count())
        ]
        added = []
        for d in drives:
            if d not in existing:
                letter = d[0].upper() if d else "?"
                # Friendly label e.g. "System C:\" or "Data D:\"
                label = f"{letter}:\\"
                self._add_drive_item(d, label)
                added.append(d)
        if added:
            self.save_settings()
            QMessageBox.information(self, "Drives Found", f"Added: {', '.join(added)}")

    # ──────────────────────────────────────────────────────────────────────────
    #  INDEXING
    # ──────────────────────────────────────────────────────────────────────────

    def _get_checked_roots(self):
        """Return all drive/folder paths (all are active in new design)."""
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for i in range(self.folder_list.count())
            if (item := self.folder_list.item(i))
            and item.data(Qt.ItemDataRole.UserRole)
        ]

    def _get_checked_ignores(self):
        """Return ignore rules whose toggle is ON."""
        result = []
        for i in range(self.ignore_list.count()):
            item = self.ignore_list.item(i)
            if not item:
                continue
            st = item.data(Qt.ItemDataRole.UserRole + 1) or "1"
            if st == "1":
                rule = item.data(Qt.ItemDataRole.UserRole)
                if rule:
                    result.append(rule)
        return result

    def start_indexing(self, targets=None):
        roots = targets or self._get_checked_roots()
        ignores = self._get_checked_ignores()
        if not roots:
            QMessageBox.warning(
                self, "No Folders", "Add at least one folder to index first."
            )
            return
        self._current_roots = roots
        self._rb_index.setVisible(False)
        self._rb_stop.setVisible(True)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._start_time = time.time()
        self.worker = IndexerWorker(roots, ignores)
        self.worker.progress.connect(self._on_index_progress)
        self.worker.finished.connect(self._on_index_done)
        self.worker.start()

    def stop_indexing(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
            self._status_lbl.setText("Stopping…")
            self._rb_stop.setEnabled(False)

    def _on_index_progress(self, count, msg):
        self._status_lbl.setText(f"Indexing… {count:,} items — {msg[:60]}")

    def _on_index_done(self, count):
        self._rb_index.setVisible(True)
        self._rb_stop.setVisible(False)
        self._rb_stop.setEnabled(True)
        self._progress.setVisible(False)

        self._last_indexing_dur = time.time() - self._start_time

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for root in getattr(self, "_current_roots", []):
            c.execute(
                "INSERT OR REPLACE INTO folder_stats VALUES(?,?)", (root, now_str)
            )
        c.execute(
            "INSERT OR REPLACE INTO settings VALUES(?,?)", ("last_indexed", now_str)
        )
        conn.commit()
        c.execute("SELECT COUNT(*) FROM files")
        total = c.fetchone()[0]
        conn.close()

        self.update_stats()
        dur = time.time() - self._start_time
        if "--daemon" not in sys.argv and "--index" not in sys.argv:
            QMessageBox.information(
                self,
                "Indexing Complete",
                f"Done!\n\nProcessed:  {count:,} items\n"
                f"Duration:   {dur:.1f}s\n"
                f"Index size: {total:,} items\n"
                f"Completed:  {now_str}",
            )

    def clear_index(self):
        if (
            QMessageBox.question(
                self,
                "Clear Index",
                "Wipe the entire index cache?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM files")
            conn.commit()
            conn.close()
            for w in [self._details, self._icons_view, self._tree_view]:
                w.clear()
            self.update_stats()

    def update_stats(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM files")
            count = c.fetchone()[0]
            c.execute("SELECT value FROM settings WHERE key='last_indexed'")
            res = c.fetchone()
            last = res[0] if res else "Never"
            conn.close()
            dur_str = (
                f"  ·  Indexed in {self._last_indexing_dur:.1f}s"
                if self._last_indexing_dur
                else ""
            )
            self._status_lbl.setText(
                f"{count:,} items indexed  ·  Last run: {last}{dur_str}"
            )
        except Exception:
            self._status_lbl.setText("Ready")

    # ──────────────────────────────────────────────────────────────────────────
    #  SEARCH
    # ──────────────────────────────────────────────────────────────────────────

    def _on_search_changed(self, text):
        self.search_timer.start(120)

    def change_filter(self, ftype):
        self.filter_type = ftype
        self.perform_search()

    def set_view(self, mode):
        self.view_mode = mode
        self._stack.setCurrentIndex({"details": 0, "icons": 1, "tree": 2}[mode])
        self.perform_search()

    def _show_empty_state(self):
        self._stack.setCurrentIndex(3)

    def perform_search(self):
        query = self._search_bar.input.text().strip()

        if len(query) < 2:
            for w in [self._details, self._icons_view, self._tree_view]:
                w.clear()
            self._status_lbl.setText("Type at least 2 characters…   0 items")
            # Show empty state only if nothing indexed
            try:
                import sqlite3 as _sq

                c2 = _sq.connect(DB_PATH).execute("SELECT COUNT(*) FROM files")
                cnt = c2.fetchone()[0]
                if cnt == 0:
                    self._show_empty_state()
                else:
                    self._stack.setCurrentIndex(
                        {"details": 0, "icons": 1, "tree": 2}[self.view_mode]
                    )
            except Exception:
                pass
            return

        terms = query.split()
        sel = self.folder_list.selectedItems()
        filter_paths = (
            [i.data(Qt.ItemDataRole.UserRole) for i in sel]
            if sel
            else self._get_checked_roots()
        )

        if not filter_paths and self.folder_list.count():
            for w in [self._details, self._icons_view, self._tree_view]:
                w.clear()
            self._status_lbl.setText("No folders configured.")
            return

        t0 = time.perf_counter()

        if self.filter_type == "content":
            results = [
                (r[0], r[1])
                for r in self.search_engine.search_content(
                    query_terms=terms, target_folders=filter_paths
                )
            ]
        else:
            raw = self.search_engine.search_files(
                query_terms=terms,
                target_folders=filter_paths,
                files_only=(self.filter_type == "files"),
                folders_only=(self.filter_type == "folders"),
            )
            results = [(r[0], r[1]) for r in raw]

        elapsed = (time.perf_counter() - t0) * 1000

        if self.view_mode == "details":
            self._fill_details(results)
        elif self.view_mode == "icons":
            self._fill_icons(results)
        else:
            self._fill_tree(results)

        self._stack.setCurrentIndex(
            {"details": 0, "icons": 1, "tree": 2}[self.view_mode]
        )
        n = len(results)
        self._status_lbl.setText(f"⚡  {n:,} results  in  {elapsed:.1f} ms")

    # ──────────────────────────────────────────────────────────────────────────
    #  POPULATORS
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_size(path: str, is_dir: bool) -> str:
        if is_dir:
            return ""
        try:
            b = os.path.getsize(path)
            for unit in ("B", "KB", "MB", "GB"):
                if b < 1024:
                    return f"{b:.0f} {unit}"
                b /= 1024
            return f"{b:.1f} TB"
        except OSError:
            return ""

    @staticmethod
    def _fmt_mtime(path: str) -> str:
        try:
            t = os.path.getmtime(path)
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
        except OSError:
            return ""

    def _fill_details(self, results):
        tree = self._details
        tree.setUpdatesEnabled(False)
        tree.setSortingEnabled(False)
        tree.clear()
        for path, is_dir in results[:3000]:
            name = os.path.basename(path) or path
            ttype = self._ext_type(path, is_dir)
            size_str = self._fmt_size(path, is_dir)
            mod_str = self._fmt_mtime(path)
            item = QTreeWidgetItem([name, ttype, size_str, mod_str])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            if os.path.exists(path):
                icon = self.icon_provider.icon(QFileInfo(path))
            else:
                icon = self._folder_icon(20) if is_dir else self._file_icon(name, 20)
            item.setIcon(0, icon)
            item.setToolTip(0, path)
            tree.addTopLevelItem(item)
        tree.setSortingEnabled(True)
        tree.setUpdatesEnabled(True)

    def _fill_icons(self, results):
        lw = self._icons_view
        lw.setUpdatesEnabled(False)
        lw.clear()
        for path, is_dir in results[:800]:
            name = os.path.basename(path) or path
            short = name if len(name) <= 14 else name[:12] + "…"
            if os.path.exists(path):
                icon = self.icon_provider.icon(QFileInfo(path))
            else:
                icon = self._folder_icon(40) if is_dir else self._file_icon(name, 40)
            item = QListWidgetItem(icon, short)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
            )
            lw.addItem(item)
        lw.setUpdatesEnabled(True)

    def _fill_tree(self, results):
        tree = self._tree_view
        tree.setUpdatesEnabled(False)
        tree.clear()
        nodes: dict[str, QTreeWidgetItem] = {}
        for path, is_dir in results[:1500]:
            parts = path.replace("\\", "/").split("/")
            parent = tree.invisibleRootItem()
            so_far = ""
            for i, part in enumerate(parts):
                sep = "/" if i < len(parts) - 1 else ""
                so_far += part + sep
                full = so_far.replace("/", "\\")
                if so_far in nodes:
                    parent = nodes[so_far]
                else:
                    folder = (i < len(parts) - 1) or is_dir
                    icon = (
                        self._folder_icon(16) if folder else self._file_icon(part, 16)
                    )
                    new = QTreeWidgetItem(parent, [part, full])
                    new.setData(0, Qt.ItemDataRole.UserRole, full)
                    new.setIcon(0, icon)
                    nodes[so_far] = new
                    parent = new
        tree.setUpdatesEnabled(True)

    # ──────────────────────────────────────────────────────────────────────────
    #  CONTEXT MENUS
    # ──────────────────────────────────────────────────────────────────────────

    def _ctx_details(self, pos):
        sel = self._details.selectedItems()
        if not sel:
            return
        paths = [
            i.data(0, Qt.ItemDataRole.UserRole)
            for i in sel
            if i.data(0, Qt.ItemDataRole.UserRole)
        ]
        self._common_menu(pos, paths, self._details)

    def _ctx_icons(self, pos):
        sel = self._icons_view.selectedItems()
        if not sel:
            return
        paths = [
            i.data(Qt.ItemDataRole.UserRole)
            for i in sel
            if i.data(Qt.ItemDataRole.UserRole)
        ]
        self._common_menu(pos, paths, self._icons_view)

    def _ctx_tree(self, pos, widget):
        sel = widget.selectedItems()
        if not sel:
            return
        paths = [
            i.data(0, Qt.ItemDataRole.UserRole)
            for i in sel
            if i.data(0, Qt.ItemDataRole.UserRole)
        ]
        self._common_menu(pos, paths, widget)

    def _common_menu(self, pos, paths, parent_widget):
        if not paths:
            return
        path = paths[0]
        menu = QMenu(self)
        open_a = menu.addAction("Open")
        explore_a = menu.addAction("Show in Explorer")
        copy_a = menu.addAction("Copy Path")
        menu.addSeparator()
        ops_a = menu.addAction("Copy / Move / Delete…")
        arch_a = extr_a = None
        if len(paths) == 1 and is_archive(path):
            extr_a = menu.addAction("Extract Archive…")
        else:
            arch_a = menu.addAction("Compress to Archive…")

        action = menu.exec(parent_widget.mapToGlobal(pos))
        if action == open_a:
            for p in paths:
                self._open_path(p)
        elif action == explore_a:
            d = path if os.path.isdir(path) else os.path.dirname(path)
            if os.path.exists(d):
                os.startfile(d)
        elif action == copy_a:
            QApplication.clipboard().setText("\n".join(paths))
        elif action == ops_a:
            self.file_ops_win = FileOpsWindow()
            self.file_ops_win.source_paths = list(paths)
            self.file_ops_win._refresh_list()
            self.file_ops_win.show()
        elif (arch_a and action == arch_a) or (extr_a and action == extr_a):
            self.archiver_win = ArchiverWindow()
            self.archiver_win.source_paths = list(paths)
            self.archiver_win._refresh_list()
            self.archiver_win.show()

    def show_folder_ctx(self, pos):
        item = self.folder_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        idx_a = menu.addAction("Index This Folder Only")
        rem_a = menu.addAction("Remove")
        action = menu.exec(self.folder_list.mapToGlobal(pos))
        if action == idx_a:
            self.start_indexing(targets=[item.data(Qt.ItemDataRole.UserRole)])
        elif action == rem_a:
            self.folder_list.takeItem(self.folder_list.row(item))
            self.save_settings()

    def show_ignore_ctx(self, pos):
        item = self.ignore_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        rem_a = menu.addAction("Remove Rule")
        if menu.exec(self.ignore_list.mapToGlobal(pos)) == rem_a:
            self.ignore_list.takeItem(self.ignore_list.row(item))
            self.save_settings()

    def _open_path(self, path):
        if not path:
            return
        if os.path.exists(path):
            os.startfile(path)
        else:
            QMessageBox.critical(
                self, "Not Found", "File or folder no longer exists or is unreachable."
            )

    # ──────────────────────────────────────────────────────────────────────────
    #  KEYBOARD SHORTCUTS
    # ──────────────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if (
            event.key() in (Qt.Key.Key_F, Qt.Key.Key_K)
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self._search_bar.input.setFocus()
            self._search_bar.input.selectAll()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._details.hasFocus():
                items = self._details.selectedItems()
                if items:
                    self._open_path(items[0].data(0, Qt.ItemDataRole.UserRole))
        super().keyPressEvent(event)

    # ──────────────────────────────────────────────────────────────────────────
    #  LIVE WATCHER
    # ──────────────────────────────────────────────────────────────────────────

    def start_live_watchers(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
        active = [
            item.data(Qt.ItemDataRole.UserRole)
            for i in range(self.folder_list.count())
            if (item := self.folder_list.item(i))
            and item.data(Qt.ItemDataRole.UserRole)
            and os.path.exists(item.data(Qt.ItemDataRole.UserRole))
        ]
        if not active:
            return
        self.observer = Observer()
        handler = LiveCacheUpdater(self._get_checked_ignores())
        for f in active:
            with contextlib.suppress(Exception):
                self.observer.schedule(handler, f, recursive=True)
        self.observer.start()

    # ──────────────────────────────────────────────────────────────────────────
    #  DAEMON / CLI
    # ──────────────────────────────────────────────────────────────────────────

    def check_args(self):
        if "--index" in sys.argv or "--daemon" in sys.argv:
            self.hide()
            self.start_indexing()
            if "--daemon" not in sys.argv:
                self.worker.finished.connect(lambda: QApplication.quit())
            else:
                self.daemon_timer = QTimer()
                self.daemon_timer.timeout.connect(self.start_indexing)
                self.daemon_timer.start(3600000)


#  ENTRY POINT


def main():
    # High-DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.xexplorer")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = XExplorer()
    if (
        "--no-ui" not in sys.argv
        and "--daemon" not in sys.argv
        and "--index" not in sys.argv
    ):
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
