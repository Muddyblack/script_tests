import sys
import os
import sqlite3
import time
import json
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QLabel,
    QListWidget,
    QInputDialog,
    QMessageBox,
    QFrame,
    QFileDialog,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QStackedWidget,
    QListWidgetItem,
    QButtonGroup,
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize
from PyQt6.QtGui import QIcon

from search_engine import SearchEngine

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

# --- CONFIGURATION & PERSISTENCE ---
DB_PATH = os.path.join(os.getenv("APPDATA", "."), "x_explorer_cache.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Table for indexed files
    cursor.execute("""CREATE TABLE IF NOT EXISTS files (
                        path TEXT PRIMARY KEY,
                        name TEXT,
                        parent TEXT,
                        is_dir INTEGER,
                        last_seen INTEGER)""")
    # Table for user settings (Custom folders & Ignore lists)
    cursor.execute("""CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT)""")
    # Table for folder-specific stats
    cursor.execute("""CREATE TABLE IF NOT EXISTS folder_stats (
                        path TEXT PRIMARY KEY,
                        last_indexed TEXT)""")
    conn.commit()
    conn.close()


# --- BACKGROUND INDEXER ---
class IndexerWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(int)

    def __init__(self, roots, ignore_list):
        super().__init__()
        self.roots = roots
        self.ignore_list = [i.lower() for i in ignore_list]
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=OFF")  # Extreme performance mode

        total_indexed = 0
        batch_entries = []
        BATCH_SIZE = 5000  # Massive speedup by reducing transaction overhead

        for root_path in self.roots:
            if not self._is_running:
                break
            if not os.path.exists(root_path):
                continue

            for root, dirs, files in os.walk(root_path):
                if not self._is_running:
                    break

                # Filter directories
                new_dirs = []
                for d in dirs:
                    full_path = os.path.abspath(os.path.join(root, d)).lower()
                    if (
                        d.lower() not in self.ignore_list
                        and full_path not in self.ignore_list
                    ):
                        new_dirs.append(d)
                dirs[:] = new_dirs

                # Add directories to batch
                now = int(time.time())
                for d in dirs:
                    full_path = os.path.join(root, d)
                    batch_entries.append((full_path, d, root, 1, now))

                # Filter and add files to batch
                for f in files:
                    full_path = os.path.abspath(os.path.join(root, f))
                    if (
                        f.lower() not in self.ignore_list
                        and full_path.lower() not in self.ignore_list
                    ):
                        _, ext = os.path.splitext(f)
                        if ext.lower() not in self.ignore_list:
                            batch_entries.append((full_path, f, root, 0, now))

                # Periodic Bulk Insert
                if len(batch_entries) >= BATCH_SIZE:
                    cursor.executemany(
                        "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?)",
                        batch_entries,
                    )
                    total_indexed += len(batch_entries)
                    self.progress.emit(total_indexed, f"Deep in: {root[:30]}...")
                    batch_entries = []
                    conn.commit()

        # Final remaining items
        if batch_entries:
            cursor.executemany(
                "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?)", batch_entries
            )
            total_indexed += len(batch_entries)
            conn.commit()

        conn.close()
        self.finished.emit(total_indexed)


# --- LIVE FILE WATCHER ---
class LiveCacheUpdater(FileSystemEventHandler):
    def __init__(self, ignore_list):
        self.ignore_list = [i.lower() for i in ignore_list]
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._cursor = self._conn.cursor()

    def _should_ignore(self, path):
        path_lower = path.lower()
        name_lower = os.path.basename(path).lower()
        for ig in self.ignore_list:
            if ig in name_lower or ig in path_lower:
                return True
        return False

    def on_created(self, event):
        if self._should_ignore(event.src_path):
            return
        is_dir = 1 if event.is_directory else 0
        name = os.path.basename(event.src_path)
        parent = os.path.dirname(event.src_path)
        now = int(time.time())
        try:
            self._cursor.execute(
                "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?)",
                (event.src_path, name, parent, is_dir, now),
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # Database might be locked, skip this minor update

    def on_deleted(self, event):
        try:
            self._cursor.execute("DELETE FROM files WHERE path=?", (event.src_path,))
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

    def on_moved(self, event):
        self.on_deleted(event)

        # Craft a fake creation event for the destination
        class FakeEvent:
            def __init__(self, path, is_dir):
                self.src_path = path
                self.is_directory = is_dir

        self.on_created(FakeEvent(event.dest_path, event.is_directory))


# --- MAIN UI ---
class XExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.setWindowTitle("X-Explorer Pro | Extreme Fast Windows Indexer")
        self.resize(1100, 700)
        self.dark_mode = True  # Default
        self.view_mode = "flat"  # flat or tree
        self.filter_type = "all"  # all, files, folders
        self.setup_ui()
        self.load_settings()
        self.apply_modern_theme()
        self.setWindowIcon(QIcon("assets/xexplorer.png"))
        self.update_stats()

        # Watchdog Observer Reference
        self.observer = None
        if WATCHDOG_AVAILABLE:
            self.start_live_watchers()

        self.search_engine = SearchEngine(DB_PATH)

        # Search Debounce Timer
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

        QTimer.singleShot(100, self.check_args)

    def check_args(self):
        if "--index" in sys.argv or "--daemon" in sys.argv:
            self.hide()
            self.start_indexing()
            if "--daemon" not in sys.argv:
                self.worker.finished.connect(lambda: QApplication.quit())
            else:
                self.daemon_timer = QTimer()
                self.daemon_timer.timeout.connect(self.start_indexing)
                self.daemon_timer.start(3600000)  # Re-index every 1 hr

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 20, 15, 20)
        sidebar_layout.setSpacing(15)

        sidebar_layout.addWidget(QLabel("<b>MANAGED FOLDERS</b>"))
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(
            self.show_folder_context_menu
        )
        self.folder_list.itemChanged.connect(self.save_settings)
        self.folder_list.itemChanged.connect(self.perform_search)
        self.folder_list.itemSelectionChanged.connect(self.perform_search)
        sidebar_layout.addWidget(self.folder_list)

        btn_add_folder = QPushButton("+ Add Folder")
        btn_add_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_folder.clicked.connect(self.add_managed_folder)

        btn_scan_drives = QPushButton("📡 Scan Drives")
        btn_scan_drives.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_scan_drives.clicked.connect(self.scan_drives)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_add_folder)
        btn_layout.addWidget(btn_scan_drives)
        sidebar_layout.addLayout(btn_layout)

        sidebar_layout.addWidget(QLabel("<b>IGNORE LIST</b>"))
        self.ignore_list_widget = QListWidget()
        self.ignore_list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.ignore_list_widget.customContextMenuRequested.connect(
            self.show_ignore_context_menu
        )
        self.ignore_list_widget.itemChanged.connect(self.save_settings)
        sidebar_layout.addWidget(self.ignore_list_widget)

        btn_add_ignore = QPushButton("+ Add Ignore Rule")
        btn_add_ignore.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_ignore.clicked.connect(self.add_ignore_rule)
        sidebar_layout.addWidget(btn_add_ignore)

        self.btn_index = QPushButton("RE-INDEX ALL")
        self.btn_index.setObjectName("index_btn")
        self.btn_index.clicked.connect(self.start_indexing)
        sidebar_layout.addWidget(self.btn_index)

        self.btn_stop = QPushButton("🛑 STOP INDEXING")
        self.btn_stop.setObjectName("clear_btn")  # Re-use red style
        self.btn_stop.setVisible(False)
        self.btn_stop.clicked.connect(self.stop_indexing)
        sidebar_layout.addWidget(self.btn_stop)

        self.btn_clear = QPushButton("CLEAR CACHE")
        self.btn_clear.setObjectName("clear_btn")
        self.btn_clear.clicked.connect(self.clear_index)
        sidebar_layout.addWidget(self.btn_clear)

        sidebar_layout.addStretch()

        self.btn_theme = QPushButton("☀️ Light Mode")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.btn_theme)

        # Main Area
        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # Search Bar Area
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search millions of files instantly...")
        self.search_input.textChanged.connect(self.instant_search)
        search_layout.addWidget(self.search_input)

        # View Toggle
        self.btn_view_toggle = QPushButton("🌲 Tree")
        self.btn_view_toggle.setFixedWidth(80)
        self.btn_view_toggle.setCheckable(True)
        self.btn_view_toggle.clicked.connect(self.toggle_view_mode)
        search_layout.addWidget(self.btn_view_toggle)
        content_layout.addLayout(search_layout)

        # Filters Bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        self.filter_group = QButtonGroup(self)
        self.btn_all = QPushButton("All")
        self.btn_all.setCheckable(True)
        self.btn_all.setChecked(True)
        self.btn_files = QPushButton("Files")
        self.btn_files.setCheckable(True)
        self.btn_folders = QPushButton("Folders")
        self.btn_folders.setCheckable(True)
        self.btn_content = QPushButton("Content")
        self.btn_content.setCheckable(True)

        for btn, ftype in [
            (self.btn_all, "all"),
            (self.btn_files, "files"),
            (self.btn_folders, "folders"),
            (self.btn_content, "content"),
        ]:
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName(f"filter_{ftype}")
            btn.clicked.connect(lambda checked, t=ftype: self.change_filter(t))
            self.filter_group.addButton(btn)
            filter_layout.addWidget(btn)

        filter_layout.addStretch()
        content_layout.addLayout(filter_layout)

        # Results Container (Stacked Widget for List vs Tree)
        self.results_stack = QStackedWidget()

        # List View
        self.results_list = QListWidget()
        self.results_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_list.customContextMenuRequested.connect(self.show_context_menu)
        self.results_list.itemDoubleClicked.connect(self.open_file)

        # Tree View
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Name", "Path"])
        self.results_tree.setColumnWidth(0, 300)
        self.results_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_tree.customContextMenuRequested.connect(
            self.show_tree_context_menu
        )
        self.results_tree.itemDoubleClicked.connect(self.open_tree_item)

        self.results_stack.addWidget(self.results_list)
        self.results_stack.addWidget(self.results_tree)
        content_layout.addWidget(self.results_stack)

        # Status & Progress Area
        status_container = QFrame()
        status_container.setObjectName("status_container")
        status_layout = QVBoxLayout(status_container)
        status_layout.setContentsMargins(0, 5, 0, 0)

        self.status_label = QLabel("Index Ready")
        self.status_label.setStyleSheet(
            "color: #64748b; font-size: 13px; font-weight: 500;"
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        content_layout.addWidget(status_container)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(content_wrapper)

    def apply_modern_theme(self):
        if self.dark_mode:
            self.btn_theme.setText("☀️ Light Mode")
            # --- DARK MODE ---
            self.setStyleSheet("""
                QMainWindow { background-color: #0b0e14; }
                QWidget { background-color: #0b0e14; color: #e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 12px; }
                
                QFrame#sidebar { 
                    background-color: #121620; 
                    border-right: 1px solid #1e293b; 
                }
                
                QLabel { color: #94a3b8; font-weight: bold; font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px; }
                
                QLineEdit { 
                    background-color: #1a1f2e; 
                    border: 1px solid #334155; 
                    padding: 12px; 
                    border-radius: 8px; 
                    color: #ffffff;
                    font-size: 13px;
                }
                QLineEdit:focus { border: 1px solid #3b82f6; background-color: #0f172a; }
                
                QPushButton { 
                    background-color: #1e293b; 
                    border: 1px solid #334155; 
                    padding: 8px 12px; 
                    border-radius: 6px; 
                    font-weight: 600; 
                    color: #f8fafc;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #334155; border: 1px solid #475569; }
                QPushButton:pressed { background-color: #0f172a; }
                
                QPushButton#index_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6); 
                    color: white; 
                    border: none;
                    font-size: 12px;
                }
                QPushButton#index_btn:hover { background: #3b82f6; }
                
                QPushButton#clear_btn { 
                    background-color: rgba(239, 68, 68, 0.1); 
                    color: #f87171; 
                    border: 1px solid rgba(239, 68, 68, 0.2); 
                }
                QPushButton#clear_btn:hover { background-color: rgba(239, 68, 68, 0.2); }

                QListWidget { 
                    background-color: transparent; 
                    border: none; 
                    outline: none; 
                }
                QListWidget::item { 
                    background-color: #1a1f2e;
                    padding: 4px 8px; 
                    border-radius: 5px; 
                    margin-bottom: 3px; 
                    border: 1px solid transparent;
                }
                QListWidget::item:hover { background-color: #242b3d; border: 1px solid #334155; }
                QListWidget::item:selected { background-color: #1e293b; color: #3b82f6; border: 1px solid #3b82f6; }

                QTreeWidget { background-color: transparent; border: none; outline: none; }
                QTreeWidget::item { padding: 4px; border-radius: 4px; color: #e2e8f0; }
                QTreeWidget::item:selected { background-color: #1e293b; color: #3b82f6; }
                QHeaderView::section { background-color: #1a1f2e; color: #94a3b8; border: none; padding: 4px; font-weight: bold; }

                /* Filter Buttons */
                QPushButton[objectName^="filter_"] { background-color: transparent; border: none; padding: 4px 12px; color: #94a3b8; }
                QPushButton[objectName^="filter_"]:checked { color: #3b82f6; border-bottom: 2px solid #3b82f6; font-weight: bold; }
                QPushButton[objectName^="filter_"]:hover { color: #ffffff; }

                /* Premium Checkbox Styling */
                QListWidget::indicator {
                    width: 14px;
                    height: 14px;
                    border-radius: 3px;
                    border: 1.5px solid #334155;
                    background-color: #0f172a;
                }
                QListWidget::indicator:checked {
                    background-color: #3b82f6;
                    border: 1.5px solid #3b82f6;
                }
                QListWidget::indicator:unchecked:hover {
                    border: 2px solid #3b82f6;
                    background-color: #1a1f2e;
                }
                QListWidget::indicator:checked:hover {
                    background-color: #2563eb;
                }

                QScrollBar:vertical { 
                    border: none; background: transparent; 
                    width: 4px; margin: 0px;
                }
                QScrollBar::handle:vertical { 
                    background: #334155; border-radius: 2px; min-height: 40px; 
                }
                QScrollBar::handle:vertical:hover { background: #475569; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            """)
        else:
            self.btn_theme.setText("🌙 Dark Mode")
            # --- PREMIUM LIGHT MODE ---
            self.setStyleSheet("""
                QMainWindow { background-color: #f8fafc; }
                QWidget { background-color: #f8fafc; color: #1e293b; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; }
                
                QFrame#sidebar { 
                    background-color: #ffffff; 
                    border-right: 1px solid #e2e8f0; 
                }
                
                QLabel { color: #64748b; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
                
                QLineEdit { 
                    background-color: #ffffff; 
                    border: 1px solid #e2e8f0; 
                    padding: 14px; 
                    border-radius: 10px; 
                    color: #1e293b;
                    font-size: 14px;
                }
                QLineEdit:focus { border: 1px solid #3b82f6; background-color: #f1f5f9; }
                
                QPushButton { 
                    background-color: #f1f5f9; 
                    border: 1px solid #e2e8f0; 
                    padding: 10px 15px; 
                    border-radius: 8px; 
                    font-weight: 600; 
                    color: #475569;
                }
                QPushButton:hover { background-color: #e2e8f0; border: 1px solid #cbd5e1; }
                QPushButton:pressed { background-color: #cbd5e1; }
                
                QPushButton#index_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6); 
                    color: white; 
                    border: none;
                }
                QPushButton#index_btn:hover { background: #1d4ed8; }
                
                QPushButton#clear_btn { 
                    background-color: #fef2f2; 
                    color: #ef4444; 
                    border: 1px solid #fee2e2; 
                }
                QPushButton#clear_btn:hover { background-color: #fee2e2; }

                QListWidget { 
                    background-color: transparent; 
                    border: none; 
                    outline: none; 
                }
                QListWidget::item { 
                    background-color: #ffffff;
                    padding: 6px 10px; 
                    border-radius: 6px; 
                    margin-bottom: 4px; 
                    border: 1px solid #f1f5f9;
                }
                QListWidget::item:hover { background-color: #f1f5f9; border: 1px solid #e2e8f0; }
                QListWidget::item:selected { background-color: #eff6ff; color: #2563eb; border: 1px solid #3b82f6; }

                /* Premium Checkbox Styling */
                QListWidget::indicator {
                    width: 16px;
                    height: 16px;
                    border-radius: 4px;
                    border: 2px solid #e2e8f0;
                    background-color: #ffffff;
                }
                QListWidget::indicator:checked {
                    background-color: #3b82f6;
                    border: 2px solid #3b82f6;
                }
                QListWidget::indicator:unchecked:hover {
                    border: 2px solid #3b82f6;
                    background-color: #f8fafc;
                }
                QListWidget::indicator:checked:hover {
                    background-color: #2563eb;
                }

                QScrollBar:vertical { 
                    border: none; background: rgba(0,0,0,0.03); 
                    width: 4px; border-radius: 2px;
                }
                QScrollBar::handle:vertical { 
                    background: #e2e8f0; border-radius: 2px; min-height: 30px; 
                }
                QScrollBar::handle:vertical:hover { background: #cbd5e1; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

                QMenu { background-color: #ffffff; border: 1px solid #e2e8f0; color: #1e293b; padding: 5px; border-radius: 8px; }
                QMenu::item { padding: 8px 25px; border-radius: 4px; }
                QMenu::item:selected { background-color: #3b82f6; color: white; }
            """)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_modern_theme()
        self.save_settings()

    # --- LOGIC ---
    def load_settings(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT path, last_indexed FROM folder_stats")
        stats = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT value FROM settings WHERE key='folders'")
        res = cursor.fetchone()
        if res:
            try:
                folders_data = json.loads(res[0])
                for f in folders_data:
                    path = f.get("path")
                    label = f.get("label", path)
                    state = f.get("state", "1")

                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, path)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.CheckState.Checked
                        if state == "1"
                        else Qt.CheckState.Unchecked
                    )

                    if path in stats:
                        item.setToolTip(f"Path: {path}\nLast indexed: {stats[path]}")
                    else:
                        item.setToolTip(f"Path: {path}")

                    self.folder_list.addItem(item)
            except (json.JSONDecodeError, TypeError):
                # Fallback to old pipe format
                folders_raw = res[0].split("|")
                for f_raw in folders_raw:
                    if ":" in f_raw:
                        path, state = f_raw.rsplit(":", 1)
                        item = QListWidgetItem(path)
                        item.setData(Qt.ItemDataRole.UserRole, path)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(
                            Qt.CheckState.Checked
                            if state == "1"
                            else Qt.CheckState.Unchecked
                        )
                        if path in stats:
                            item.setToolTip(f"Last indexed: {stats[path]}")
                        self.folder_list.addItem(item)
                    elif f_raw:
                        item = QListWidgetItem(f_raw)
                        item.setData(Qt.ItemDataRole.UserRole, f_raw)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Checked)
                        self.folder_list.addItem(item)

        # --- MANAGE IGNORE LIST & DEFAULTS ---
        # Get Windows System Paths for precise ignoring
        win_dir = os.environ.get("SystemRoot", "C:\\Windows")
        prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")

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
            prog_files_x86,
            "C:\\MSOCache",
            "C:\\$Recycle.Bin",
        ]

        cursor.execute("SELECT value FROM settings WHERE key='ignore'")
        res = cursor.fetchone()

        # Load existing
        current_ignores = {}
        if res:
            for i_raw in res[0].split("|"):
                if ":" in i_raw:
                    rule, state = i_raw.rsplit(":", 1)
                    current_ignores[rule] = state
                elif i_raw:
                    current_ignores[i_raw] = "1"

        # Merge Defaults if not present
        for d in defaults:
            if d not in current_ignores:
                current_ignores[d] = "1"

        # Sort and Add to Widget
        for rule in sorted(current_ignores.keys(), key=str.lower):
            item = QListWidgetItem(rule)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if current_ignores[rule] == "1"
                else Qt.CheckState.Unchecked
            )
            self.ignore_list_widget.addItem(item)

        # Save merged list back to DB once if we added defaults
        if not res or len(current_ignores) > (len(res[0].split("|")) if res else 0):
            self.save_settings()

        cursor.execute("SELECT value FROM settings WHERE key='theme'")
        res = cursor.fetchone()
        if res:
            self.dark_mode = res[0] == "dark"

        conn.close()

    def save_settings(self, *args):
        folders = []
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            state = "1" if item.checkState() == Qt.CheckState.Checked else "0"
            path = item.data(Qt.ItemDataRole.UserRole)
            label = item.text()
            folders.append({"path": path, "state": state, "label": label})

        ignores = []
        for i in range(self.ignore_list_widget.count()):
            item = self.ignore_list_widget.item(i)
            state = "1" if item.checkState() == Qt.CheckState.Checked else "0"
            ignores.append(f"{item.text()}:{state}")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings VALUES (?, ?)",
            ("folders", json.dumps(folders)),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO settings VALUES (?, ?)",
            ("ignore", "|".join(ignores)),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO settings VALUES (?, ?)",
            ("theme", "dark" if self.dark_mode else "light"),
        )
        conn.commit()
        conn.close()

    def add_managed_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Folder to Index")
        if path:
            item = QListWidgetItem(path)  # Use path as initial label
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(f"Path: {path}")
            self.folder_list.addItem(item)
            self.save_settings()

    def add_ignore_rule(self):
        rule, ok = QInputDialog.getText(
            self,
            "Ignore Rule",
            "Enter folder name or extension to ignore (e.g. .git or node_modules):",
        )
        if ok and rule:
            item = QListWidgetItem(rule)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.ignore_list_widget.addItem(item)
            self.save_settings()

    def scan_drives(self):
        import string
        from ctypes import windll

        bitmask = windll.kernel32.GetLogicalDrives()
        drives = []
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:\\")
            bitmask >>= 1

        # Add found drives if not already in list
        existing = [
            self.folder_list.item(i).text() for i in range(self.folder_list.count())
        ]
        added_any = False
        for drive in drives:
            if drive not in existing:
                item = QListWidgetItem(drive)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.folder_list.addItem(item)
                added_any = True

        if added_any:
            self.save_settings()
            QMessageBox.information(
                self, "Drives Added", f"Found and added: {', '.join(drives)}"
            )

    def start_indexing(self, targets=None):
        roots = []
        if targets:
            roots = targets
        else:
            for i in range(self.folder_list.count()):
                item = self.folder_list.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    path = item.data(Qt.ItemDataRole.UserRole)
                    roots.append(path if path else item.text())

        # Track roots being indexed for stats
        self._current_roots = roots

        ignores = []
        for i in range(self.ignore_list_widget.count()):
            item = self.ignore_list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ignores.append(item.text())

        if not roots:
            QMessageBox.warning(
                self, "No Folders", "Add at least one folder to index first."
            )
            return

        self.btn_index.setVisible(False)
        self.btn_stop.setVisible(True)
        self.progress_bar.setVisible(True)
        self.start_time = time.time()
        self.worker = IndexerWorker(roots, ignores)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.indexing_done)
        self.worker.start()

    def stop_indexing(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
            self.status_label.setText("Stopping indexer...")
            self.btn_stop.setEnabled(False)

    def update_progress(self, count, msg):
        self.status_label.setText(f"Indexed {count:,} items... {msg[:40]}")

    def indexing_done(self, count):
        self.btn_index.setVisible(True)
        self.btn_index.setEnabled(True)
        self.btn_stop.setVisible(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setVisible(False)

        # Save last indexed time
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for root in getattr(self, "_current_roots", []):
            cursor.execute(
                "INSERT OR REPLACE INTO folder_stats VALUES (?, ?)", (root, now_str)
            )

        cursor.execute(
            "INSERT OR REPLACE INTO settings VALUES (?, ?)", ("last_indexed", now_str)
        )
        conn.commit()
        conn.close()

        # Refresh tooltips
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if item.text() in getattr(self, "_current_roots", []):
                item.setToolTip(f"Last indexed: {now_str}")

        conn = sqlite3.connect(DB_PATH)  # Re-open connection for count
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM files")
        total_count = cursor.fetchone()[0]
        conn.close()

        self.update_stats()
        duration = time.time() - self.start_time

        # Don't show dialogue if running in background
        if "--daemon" not in sys.argv and "--index" not in sys.argv:
            QMessageBox.information(
                self,
                "Indexing Complete",
                f"🚀 <b>Indexing finished!</b>\n\n"
                f"Items processed: {count:,}\n"
                f"Duration: {duration:.1f}s\n"
                f"Total index size: {total_count:,} items\n\n"
                f"Last Run: {now_str}",
            )

    def clear_index(self):
        reply = QMessageBox.question(
            self,
            "Clear Index",
            "Are you sure you want to wipe the entire index cache?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files")
            conn.commit()
            conn.close()
            self.results_list.clear()
            self.update_stats()

    def update_stats(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Count files
            cursor.execute("SELECT COUNT(*) FROM files")
            count = cursor.fetchone()[0]

            # Get last indexed time
            cursor.execute("SELECT value FROM settings WHERE key='last_indexed'")
            res = cursor.fetchone()
            last_indexed = res[0] if res else "Never"

            if WATCHDOG_AVAILABLE and self.observer and self.observer.is_alive():
                last_indexed += " (Live Sync Active)"

            conn.close()
            self.status_label.setText(
                f"Index: {count:,} items | Last Run: {last_indexed}"
            )
        except Exception:
            self.status_label.setText("Index Ready")

    def keyPressEvent(self, event):
        if (
            event.key() == Qt.Key.Key_F
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.search_input.setFocus()
            self.search_input.selectAll()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if self.results_list.hasFocus():
                item = self.results_list.currentItem()
                if item:
                    self.open_file(item)
        super().keyPressEvent(event)

    def instant_search(self):
        # Debounce the search
        self.search_timer.start(150)

    def change_filter(self, ftype):
        self.filter_type = ftype
        self.perform_search()

    def toggle_view_mode(self, checked):
        self.view_mode = "tree" if checked else "flat"
        self.btn_view_toggle.setText("📄 Flat" if checked else "🌲 Tree")
        self.results_stack.setCurrentIndex(1 if checked else 0)
        self.perform_search()

    def perform_search(self):
        query = self.search_input.text().strip()
        if len(query) < 2:
            self.results_list.clear()
            self.results_tree.clear()
            self.status_label.setText("Enter at least 2 characters...")
            return

        start_time = time.time()
        terms = [t for t in query.split() if t]

        if not terms:
            return

        # Check for managed folder filtering
        selected_items = self.folder_list.selectedItems()
        filter_paths = []

        if selected_items:
            for item in selected_items:
                path = item.data(Qt.ItemDataRole.UserRole)
                filter_paths.append(path if path else item.text())
        else:
            for i in range(self.folder_list.count()):
                item = self.folder_list.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    path = item.data(Qt.ItemDataRole.UserRole)
                    filter_paths.append(path if path else item.text())

        if not filter_paths and self.folder_list.count() > 0:
            # If folders exist but NONE are checked/selected, return no results
            self.results_list.clear()
            self.results_tree.clear()
            self.status_label.setText("No folders selected/checked.")
            return

        files_only = self.filter_type == "files"
        folders_only = self.filter_type == "folders"

        if self.filter_type == "content":
            results = self.search_engine.search_content(
                query_terms=terms, target_folders=filter_paths
            )
        else:
            # results come as (path, is_dir, name)
            results = self.search_engine.search_files(
                query_terms=terms,
                target_folders=filter_paths,
                files_only=files_only,
                folders_only=folders_only,
            )
            # Standardize back to (path, is_dir) for populator functions
            results = [(r[0], r[1]) for r in results]

        if self.view_mode == "flat":
            self.populate_flat_results(results)
        else:
            # Standardize content search tuples back to (path, is_dir) for tree
            if self.filter_type == "content":
                results = [(r[0], r[1]) for r in results]
            self.populate_tree_results(results)

        elapsed = (time.time() - start_time) * 1000
        self.status_label.setText(f"Found {len(results)} items in {elapsed:.1f}ms")

    def format_display_name(self, name, max_len=80):
        if not name:
            return ""
        if len(name) <= max_len:
            return name
        half = (max_len - 3) // 2
        return f"{name[:half]}...{name[-half:]}"

    def populate_flat_results(self, results):
        self.results_list.setUpdatesEnabled(False)
        self.results_list.clear()
        for path, is_dir in results[:100]:  # Cap at 100 rendering for extreme speed
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(f"{'Folder' if is_dir else 'File'}: {path}")
            self.results_list.addItem(item)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(15, 0, 15, 0)
            row_layout.setSpacing(18)

            icon_label = QLabel()
            icon_label.setFixedSize(42, 42)
            icon_label.setText("📁" if is_dir else "📄")
            icon_label.setStyleSheet(
                "font-size: 28px; color: #60a5fa;"
                if is_dir
                else "font-size: 28px; color: #9ca3af;"
            )
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            row_layout.addWidget(icon_label)

            text_container = QVBoxLayout()
            text_container.setContentsMargins(0, 0, 0, 0)
            text_container.setSpacing(2)

            title = os.path.basename(path)
            title_lbl = QLabel(f"<b>{title}</b>")
            title_lbl.setStyleSheet("font-size: 14px;")

            path_lbl = QLabel(self.format_display_name(path, max_len=100))
            if not self.dark_mode:
                path_lbl.setStyleSheet("color: #6b7280; font-size: 12px;")
            else:
                path_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")

            text_container.addWidget(title_lbl)
            text_container.addWidget(path_lbl)
            row_layout.addLayout(text_container, stretch=1)

            item.setSizeHint(QSize(row_widget.sizeHint().width(), 70))
            self.results_list.setItemWidget(item, row_widget)

        self.results_list.setUpdatesEnabled(True)

    def populate_tree_results(self, results):
        self.results_tree.setUpdatesEnabled(False)
        self.results_tree.clear()
        root_nodes = {}

        for path, is_dir in results[:300]:  # Trees handle volume better
            parts = path.replace("\\", "/").split("/")
            current_parent = self.results_tree.invisibleRootItem()

            path_so_far = ""
            for i, part in enumerate(parts):
                path_so_far += part + ("/" if i < len(parts) - 1 else "")

                if path_so_far in root_nodes:
                    current_parent = root_nodes[path_so_far]
                else:
                    icon = "📁 " if (i < len(parts) - 1 or is_dir) else "📄 "
                    new_item = QTreeWidgetItem(
                        current_parent, [icon + part, path_so_far.replace("/", "\\")]
                    )
                    root_nodes[path_so_far] = new_item
                    current_parent = new_item
        self.results_tree.setUpdatesEnabled(True)

    def show_tree_context_menu(self, pos):
        item = self.results_tree.itemAt(pos)
        if not item:
            return
        self._show_common_menu(pos, item.text(1), self.results_tree)

    def open_tree_item(self, item):
        path = item.text(1)
        if os.path.exists(path):
            os.startfile(path)

    def _show_common_menu(self, pos, path, parent_widget):
        menu = QMenu(self)
        open_action = menu.addAction("🚀 Run / Open")
        explore_action = menu.addAction("📁 Show in Explorer")
        copy_action = menu.addAction("🔗 Copy Full Path")

        action = menu.exec(parent_widget.mapToGlobal(pos))

        if action == open_action:
            if os.path.exists(path):
                os.startfile(path)
        elif action == explore_action:
            if os.path.exists(path):
                dir_path = path if os.path.isdir(path) else os.path.dirname(path)
                os.startfile(dir_path)
        elif action == copy_action:
            QApplication.clipboard().setText(path)

    def show_folder_context_menu(self, pos):
        item = self.folder_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        index_action = menu.addAction("🚀 Index ONLY this folder")
        rename_action = menu.addAction("✏️ Rename Label")
        remove_action = menu.addAction("❌ Stop Managing Folder")
        action = menu.exec(self.folder_list.mapToGlobal(pos))

        if action == index_action:
            path = item.data(Qt.ItemDataRole.UserRole)
            self.start_indexing(targets=[path])
        elif action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, "Rename Label", "Label:", text=item.text()
            )
            if ok and new_name:
                item.setText(new_name)
                self.save_settings()
        elif action == remove_action:
            self.folder_list.takeItem(self.folder_list.row(item))
            self.save_settings()

    def show_ignore_context_menu(self, pos):
        item = self.ignore_list_widget.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        remove_action = menu.addAction("❌ Remove Ignore Rule")
        action = menu.exec(self.ignore_list_widget.mapToGlobal(pos))
        if action == remove_action:
            self.ignore_list_widget.takeItem(self.ignore_list_widget.row(item))
            self.save_settings()

    def show_context_menu(self, pos):
        item = self.results_list.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        open_action = menu.addAction("🚀 Run / Open")
        explore_action = menu.addAction("📁 Show in Explorer")
        copy_action = menu.addAction("🔗 Copy Full Path")

        action = menu.exec(self.results_list.mapToGlobal(pos))

        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        if action == open_action:
            self.open_file(item)
        elif action == explore_action:
            if os.path.exists(path):
                # Ensure we point to the parent dir if it's a file
                dir_path = path if os.path.isdir(path) else os.path.dirname(path)
                os.startfile(dir_path)
        elif action == copy_action:
            QApplication.clipboard().setText(path)

    def open_file(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        if os.path.exists(path):
            os.startfile(path)
        else:
            QMessageBox.critical(
                self,
                "Error",
                "File or folder no longer exists or network is unreachable.",
            )

    def start_live_watchers(self):
        """Initializes watchdog to actively monitor managed folders."""
        if self.observer:
            self.observer.stop()
            self.observer.join()

        active_folders = []
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.exists(path):
                    active_folders.append(path)

        if not active_folders:
            return

        ignores = []
        for i in range(self.ignore_list_widget.count()):
            item = self.ignore_list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ignores.append(item.text())

        self.observer = Observer()
        handler = LiveCacheUpdater(ignores)

        for folder in active_folders:
            try:
                self.observer.schedule(handler, folder, recursive=True)
            except Exception:
                # Some system folders might reject recursive hooks
                pass

        self.observer.start()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = XExplorer()
    if (
        "--no-ui" not in sys.argv
        and "--daemon" not in sys.argv
        and "--index" not in sys.argv
    ):
        window.show()
    sys.exit(app.exec())
