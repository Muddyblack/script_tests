import sys
import os
import sqlite3
import subprocess
import webbrowser
import keyboard
import ctypes
from ctypes import wintypes

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QComboBox,
    QFrame,
    QMessageBox,
    QAbstractItemView,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QSystemTrayIcon,
    QMenu,
    QStyle,
    QInputDialog,
    QDialog,
)
from PyQt6.QtCore import (
    Qt,
    QObject,
    pyqtSignal,
    QTimer,
    QEventLoop,
)
from PyQt6.QtGui import QIcon

# --- CONFIGURATION & DATABASE ---
DB_PATH = os.path.join(os.getenv("APPDATA", "."), "context_switcher.db")
X_EXPLORER_DB = os.path.join(os.getenv("APPDATA", "."), "x_explorer_cache.db")
GHOST_TYPIST_DB = os.path.join(os.getenv("APPDATA", "."), "ghost_typist.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER,
                type TEXT,
                target TEXT,
                FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


# --- WINDOWS NATIVE API HELPERS (For Window Tracking & Manipulation) ---
def get_hwnd_executable(hwnd):
    """Securely resolves a Window Handle to its underlying Executable Path."""
    if sys.platform != "win32":
        return ""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    hProcess = kernel32.OpenProcess(0x1000, False, pid.value)
    if hProcess:
        exe_path = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(
            hProcess, 0, exe_path, ctypes.byref(size)
        ):
            kernel32.CloseHandle(hProcess)
            return exe_path.value
        kernel32.CloseHandle(hProcess)
    return ""


def get_visible_windows():
    """Fetches all visible windows, their coordinates, and executables for Context Weaver."""
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    windows = []

    def callback(hwnd, extra):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)

            # Filter out standard invisible OS overlays
            ignore_list = [
                "Program Manager",
                "Settings",
                "Microsoft Text Input Application",
                "Context Switcher | Workspace Manager",
                "Context Weaver Auto-Capture",
            ]
            if title.value in ignore_list:
                return True

            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            if w > 0 and h > 0:
                exe_path = get_hwnd_executable(hwnd)
                if exe_path:
                    windows.append(
                        (hwnd, title.value, rect.left, rect.top, w, h, exe_path)
                    )
        return True

    cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(cb_type(callback), 0)
    return windows


def move_matching_windows(title_substring, x, y, w, h):
    """Finds windows matching the substring and resizes/moves them. Returns True if found."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    moved_any = False

    def callback(hwnd, extra):
        nonlocal moved_any
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)

            if title_substring.lower() in title.value.lower():
                user32.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True)
                moved_any = True
        return True

    cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(cb_type(callback), 0)
    return moved_any


def close_tracked_window(window_info, force=False):
    """Smarter teardown that specifically targets apps based on their exe type and title"""
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32

    target_title = window_info.get("title", "").lower()
    w_type = window_info.get("type", "app")

    if not target_title:
        return

    def callback(hwnd, extra):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            t_lower = title.value.lower()

            if target_title in t_lower:
                exe_path = get_hwnd_executable(hwnd).lower()

                is_match = False
                # Ensure we only close the specific window type we launched
                if w_type == "folder" and "explorer.exe" in exe_path:
                    is_match = True
                elif w_type == "vscode" and "code.exe" in exe_path:
                    is_match = True
                elif w_type == "app":
                    is_match = True

                if is_match:
                    # NEVER force kill Windows Explorer (it crashes the desktop shell)
                    if force and "explorer.exe" not in exe_path:
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        try:
                            # CREATE_NO_WINDOW prevents black console flashes
                            subprocess.run(
                                f"taskkill /F /T /PID {pid.value}",
                                shell=True,
                                capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                        except Exception:
                            pass
                    else:
                        # WM_CLOSE = 0x0010 (Sends graceful close request)
                        user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return True

    cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(cb_type(callback), 0)


# --- CONTEXT WEAVER DIALOG ---
class ContextWeaverDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Context Weaver Auto-Capture")
        self.resize(700, 550)
        self.manager = parent
        self.captured_workspace_id = None

        if parent:
            self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout(self)

        lbl = QLabel(
            "<b>Context Weaver</b><br>Select the open windows you want to save. We will capture their exact screen coordinates and executables."
        )
        layout.addWidget(lbl)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter a Name for this new Workspace...")
        layout.addWidget(self.name_input)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Save & Create Workspace")
        btn_ok.setObjectName("success_btn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self.capture)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        self.populate_windows()

    def populate_windows(self):
        windows = get_visible_windows()
        for hwnd, title, x, y, w, h, exe in windows:
            display_title = title if len(title) < 55 else title[:52] + "..."
            app_name = os.path.basename(exe)

            item = QListWidgetItem(f"🪟 {display_title}  ({app_name})")
            # Store exact string format for DB: EXE | Title | Bounds
            item.setData(Qt.ItemDataRole.UserRole, f"{exe} | {title} | {x},{y},{w},{h}")

            # Make Checkable
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

    def capture(self):
        ws_name = self.name_input.text().strip()
        if not ws_name:
            QMessageBox.warning(self, "Error", "Please enter a workspace name.")
            return

        selected_actions = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_actions.append(item.data(Qt.ItemDataRole.UserRole))

        if not selected_actions:
            QMessageBox.warning(self, "Error", "Please select at least one window.")
            return

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO workspaces (name) VALUES (?)", (ws_name,))
                ws_id = cursor.lastrowid

                for target in selected_actions:
                    cursor.execute(
                        "INSERT INTO actions (workspace_id, type, target) VALUES (?, ?, ?)",
                        (ws_id, "Captured App", target),
                    )
                conn.commit()
                self.captured_workspace_id = ws_id
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Error", "A workspace with that name already exists."
            )


# --- MANUAL WINDOW CAPTURE DIALOG ---
class WindowCaptureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture Window Layout")
        self.resize(550, 450)
        self.selected_target = ""

        if parent:
            self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout(self)
        lbl = QLabel(
            "Select an open window to capture its current exact size and position:"
        )
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Capture Selected")
        btn_ok.setObjectName("success_btn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self.capture)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        self.populate_windows()

    def populate_windows(self):
        windows = get_visible_windows()
        for hwnd, title, x, y, w, h, exe in windows:
            display_title = title if len(title) < 50 else title[:47] + "..."
            item = QListWidgetItem(f"🪟 {display_title} (Pos: {x},{y} | Size: {w}x{h})")
            item.setData(Qt.ItemDataRole.UserRole, f"{title} | {x}, {y}, {w}, {h}")
            self.list_widget.addItem(item)

    def capture(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_target = item.data(Qt.ItemDataRole.UserRole)
            self.accept()


# --- GLOBAL HOTKEY LISTENER ---
class HotkeyListener(QObject):
    summon_triggered = pyqtSignal()

    def __init__(self):
        super().__init__()
        try:
            keyboard.add_hotkey("ctrl+shift+space", self.summon_triggered.emit)
        except Exception as e:
            print(f"Could not bind global hotkey: {e}")


# --- MAIN CONTEXT SWITCHER APP ---
class ContextSwitcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Context Switcher | Workspace Manager")
        self.resize(1050, 680)

        self.dark_mode = True
        self.current_workspace_id = None
        self.workspaces = []

        # State Tracking: { ws_id: {'processes': [...], 'titles': [...]} }
        self.active_workspaces = {}

        # Background Timer for resizing windows after they launch
        self.pending_resizes = []
        self.resize_attempts = 0
        self.resize_timer = QTimer()
        self.resize_timer.timeout.connect(self._process_pending_resizes)

        self.load_settings()
        self.setup_ui()
        self.apply_theme()
        self.load_workspaces()

        # Setup global summon (Calls separate Nexus Search)
        self.listener = HotkeyListener()
        self.listener.summon_triggered.connect(self.launch_nexus)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- LEFT SIDEBAR (WORKSPACES) ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 20, 20, 20)
        sidebar_layout.setSpacing(15)

        sidebar_layout.addWidget(QLabel("<b>YOUR WORKSPACES</b>"))

        self.ws_list = QListWidget()
        self.ws_list.itemClicked.connect(self.select_workspace)
        sidebar_layout.addWidget(self.ws_list)

        # Added Auto-Capture Button
        btn_capture_ws = QPushButton("📸 Context Weaver")
        btn_capture_ws.setObjectName("success_btn")
        btn_capture_ws.setToolTip("Automatically capture all currently open windows.")
        btn_capture_ws.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_capture_ws.clicked.connect(self.open_context_weaver)
        sidebar_layout.addWidget(btn_capture_ws)

        btn_new_ws = QPushButton("+ New Empty Workspace")
        btn_new_ws.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new_ws.clicked.connect(self.create_workspace)
        sidebar_layout.addWidget(btn_new_ws)

        sidebar_layout.addStretch()

        self.btn_theme = QPushButton("☀️ Light Mode")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.btn_theme)

        # --- RIGHT MAIN AREA (ACTIONS) ---
        content_wrapper = QWidget()
        content_wrapper.setObjectName("main_content")
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Header Area
        header_widget = QFrame()
        header_widget.setObjectName("main_header")
        header_widget.setFixedHeight(80)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(30, 0, 30, 0)

        self.ws_title = QLabel("Select a Workspace")
        self.ws_title.setObjectName("ws_title")
        header_layout.addWidget(self.ws_title)

        header_layout.addStretch()

        self.btn_launch = QPushButton("🚀 LAUNCH WORKSPACE")
        self.btn_launch.setObjectName("success_btn")
        self.btn_launch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_launch.clicked.connect(self.launch_current_workspace_ui)
        header_layout.addWidget(self.btn_launch)

        # Split Teardown buttons
        self.btn_teardown_soft = QPushButton("🛑 GRACEFUL CLOSE")
        self.btn_teardown_soft.setObjectName("warning_btn")
        self.btn_teardown_soft.setToolTip(
            "Sends a close signal. Prompts for unsaved changes."
        )
        self.btn_teardown_soft.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_teardown_soft.clicked.connect(
            lambda: self.teardown_current_workspace(force=False)
        )
        self.btn_teardown_soft.setVisible(False)
        header_layout.addWidget(self.btn_teardown_soft)

        self.btn_teardown_hard = QPushButton("💀 FORCE KILL")
        self.btn_teardown_hard.setObjectName("danger_btn")
        self.btn_teardown_hard.setToolTip("Instantly destroys process tree. No saving.")
        self.btn_teardown_hard.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_teardown_hard.clicked.connect(
            lambda: self.teardown_current_workspace(force=True)
        )
        self.btn_teardown_hard.setVisible(False)
        header_layout.addWidget(self.btn_teardown_hard)

        content_layout.addWidget(header_widget)

        # Inner Content Padding Area
        inner_content = QWidget()
        inner_layout = QVBoxLayout(inner_content)
        inner_layout.setContentsMargins(30, 20, 30, 30)
        inner_layout.setSpacing(20)

        # Action Builder Area
        builder_card = QFrame()
        builder_card.setObjectName("builder_card")
        builder_layout = QHBoxLayout(builder_card)
        builder_layout.setContentsMargins(15, 15, 15, 15)
        builder_layout.setSpacing(10)

        self.action_type = QComboBox()
        self.action_type.addItems(
            [
                "Folder",
                "URL",
                "App (.exe)",
                "Command",
                "VS Code",
                "Delay (ms)",
                "Captured App",
                "Resize Window",
            ]
        )
        self.action_type.setFixedWidth(140)
        self.action_type.currentTextChanged.connect(self.update_action_placeholder)
        builder_layout.addWidget(self.action_type)

        self.action_target = QLineEdit()
        self.action_target.setPlaceholderText("e.g. C:\\Projects\\Frontend")
        builder_layout.addWidget(self.action_target)

        self.btn_browse = QPushButton("📁")
        self.btn_browse.setFixedWidth(40)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self.browse_target)
        builder_layout.addWidget(self.btn_browse)

        btn_add_action = QPushButton("Add Action")
        btn_add_action.setObjectName("action_btn")
        btn_add_action.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_action.clicked.connect(self.add_action)
        builder_layout.addWidget(btn_add_action)

        inner_layout.addWidget(builder_card)

        # Actions Table
        self.actions_table = QTableWidget(0, 2)
        self.actions_table.setHorizontalHeaderLabels(
            ["Action Type", "Target Path / Command / Delay / Window Config"]
        )
        self.actions_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.actions_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.actions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.actions_table.setShowGrid(False)
        self.actions_table.verticalHeader().setVisible(False)
        inner_layout.addWidget(self.actions_table)

        # Footer Actions
        footer_layout = QHBoxLayout()
        btn_del_action = QPushButton("Remove Selected Action")
        btn_del_action.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del_action.clicked.connect(self.delete_action)
        footer_layout.addWidget(btn_del_action)

        footer_layout.addStretch()

        btn_del_ws = QPushButton("🗑 Delete Workspace")
        btn_del_ws.setObjectName("danger_btn_outline")
        btn_del_ws.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del_ws.clicked.connect(self.delete_workspace)
        footer_layout.addWidget(btn_del_ws)

        inner_layout.addLayout(footer_layout)
        content_layout.addWidget(inner_content)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(content_wrapper)

        self.set_editor_enabled(False)

    def closeEvent(self, event):
        """Intercept the close button (X) so the app minimizes to background tray instead of quitting."""
        event.ignore()
        self.hide()

    def apply_theme(self):
        if self.dark_mode:
            self.btn_theme.setText("☀️ Light Mode")
            self.setStyleSheet("""
                QMainWindow, QDialog { background-color: #0c0e14; }
                QWidget { color: #e2e8f0; font-family: 'Outfit', 'Inter', 'Segoe UI'; font-size: 13px; }
                
                QFrame#sidebar { 
                    background-color: #11131c; 
                    border-right: 1px solid #1e212d; 
                }
                QFrame#main_header {
                    background-color: #0f111a;
                    border-bottom: 1px solid #1e212d;
                }
                
                QLabel { color: #8b9bb4; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; }
                QLabel#ws_title { color: #ffffff; font-size: 24px; font-weight: bold; text-transform: none; letter-spacing: -0.5px; }
                
                QLineEdit, QComboBox { 
                    background-color: #1a1d2b; 
                    border: 1px solid #2a2e45; 
                    padding: 10px 14px; 
                    border-radius: 10px; 
                    color: #ffffff;
                }
                QLineEdit:focus, QComboBox:focus { border: 1px solid #3b82f6; background-color: #161925; }
                QComboBox::drop-down { border: none; }
                
                QPushButton { 
                    background-color: #1e2336; 
                    border: 1px solid #2a2e45; 
                    padding: 10px 20px; 
                    border-radius: 10px; 
                    font-weight: bold; 
                    color: #e2e8f0;
                }
                QPushButton:hover { background-color: #2a2e45; border-color: #3b82f6; }
                
                QPushButton#success_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb); 
                    color: white; border: none; 
                }
                QPushButton#success_btn:hover { background: #60a5fa; }
                
                QPushButton#warning_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f59e0b, stop:1 #d97706); 
                    color: white; border: none; 
                }
                QPushButton#warning_btn:hover { background: #fbbf24; }
                
                QPushButton#danger_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ef4444, stop:1 #dc2626); 
                    color: white; border: none; 
                }
                QPushButton#danger_btn:hover { background: #f87171; }
                
                QPushButton#danger_btn_outline { background-color: transparent; color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
                QPushButton#danger_btn_outline:hover { background-color: rgba(239, 68, 68, 0.1); border-color: #ef4444; }

                QListWidget, QTableWidget { 
                    background-color: #11131c; 
                    border: 1px solid #1e212d; 
                    border-radius: 12px; 
                    outline: none; 
                    padding: 5px;
                }
                QListWidget::item { 
                    padding: 14px; 
                    border-radius: 8px; 
                    margin-bottom: 4px; 
                    background: transparent;
                }
                QListWidget::item:hover { background-color: rgba(255, 255, 255, 0.03); }
                QListWidget::item:selected { 
                    background-color: rgba(59, 130, 246, 0.15); 
                    color: #60a5fa; 
                    border: 1px solid rgba(59, 130, 246, 0.3); 
                }
                
                QHeaderView::section { 
                    background-color: #11131c; 
                    color: #8b9bb4; 
                    border: none; 
                    padding: 12px; 
                    font-weight: bold; 
                    border-bottom: 1px solid #1e212d; 
                }
                QTableWidget::item { padding: 10px; border-bottom: 1px solid #1e212d; }
                
                QFrame#builder_card { 
                    background-color: rgba(30, 41, 59, 0.4); 
                    border: 1px solid #2a2e45; 
                    border-radius: 14px; 
                }
            """)
        else:
            self.btn_theme.setText("🌙 Dark Mode")
            self.setStyleSheet("""
                QMainWindow, QDialog { background-color: #f8fafc; }
                QWidget { color: #1e293b; font-family: 'Outfit', 'Inter', 'Segoe UI'; font-size: 13px; }
                
                QFrame#sidebar { 
                    background-color: #f1f5f9; 
                    border-right: 1px solid #e2e8f0; 
                }
                QFrame#main_header {
                    background-color: #ffffff;
                    border-bottom: 1px solid #e2e8f0;
                }
                
                QLabel { color: #64748b; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; }
                QLabel#ws_title { color: #0f172a; font-size: 24px; font-weight: bold; text-transform: none; letter-spacing: -0.5px; }
                
                QLineEdit, QComboBox { 
                    background-color: #ffffff; 
                    border: 1px solid #cbd5e1; 
                    padding: 10px 14px; 
                    border-radius: 10px; 
                    color: #0f172a;
                }
                QLineEdit:focus, QComboBox:focus { border: 1px solid #3b82f6; }
                QComboBox::drop-down { border: none; }
                
                QPushButton { 
                    background-color: #ffffff; 
                    border: 1px solid #cbd5e1; 
                    padding: 10px 20px; 
                    border-radius: 10px; 
                    font-weight: bold; 
                    color: #334155;
                }
                QPushButton:hover { background-color: #f1f5f9; border-color: #3b82f6; }
                
                QPushButton#success_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb); 
                    color: white; border: none; 
                }
                QPushButton#success_btn:hover { background: #2563eb; }
                
                QPushButton#warning_btn { background: #f59e0b; color: white; border: none; }
                QPushButton#warning_btn:hover { background: #d97706; }
                
                QPushButton#danger_btn { background: #ef4444; color: white; border: none; }
                QPushButton#danger_btn:hover { background: #dc2626; }
                
                QPushButton#danger_btn_outline { background-color: transparent; color: #ef4444; border: 1px solid #fecaca; }
                QPushButton#danger_btn_outline:hover { background-color: #fef2f2; }

                QListWidget, QTableWidget { 
                    background-color: #ffffff; 
                    border: 1px solid #e2e8f0; 
                    border-radius: 12px; 
                    outline: none; 
                    padding: 5px;
                }
                QListWidget::item { 
                    padding: 14px; 
                    border-radius: 8px; 
                    margin-bottom: 4px; 
                }
                QListWidget::item:hover { background-color: #f8fafc; }
                QListWidget::item:selected { 
                    background-color: #eff6ff; 
                    color: #2563eb; 
                    border: 1px solid rgba(37, 99, 235, 0.3); 
                }

                QHeaderView::section { 
                    background-color: #f8fafc; 
                    color: #64748b; 
                    border: none; 
                    padding: 12px; 
                    font-weight: bold; 
                    border-bottom: 1px solid #e2e8f0; 
                }
                QTableWidget::item { padding: 10px; border-bottom: 1px solid #f8fafc; }
                
                QFrame#builder_card { 
                    background-color: #ffffff; 
                    border: 1px solid #e2e8f0; 
                    border-radius: 14px; 
                }
            """)

    def load_settings(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key='theme'")
            res = cursor.fetchone()
            if res:
                self.dark_mode = res[0] == "dark"

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("theme", "dark" if self.dark_mode else "light"),
            )
            conn.commit()

    def launch_nexus(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        nexus_path = os.path.join(script_dir, "nexus_search.py")
        subprocess.Popen([sys.executable, nexus_path])

    # --- UI LOGIC ---
    def set_editor_enabled(self, enabled):
        self.action_type.setEnabled(enabled)
        self.action_target.setEnabled(enabled)
        self.btn_browse.setEnabled(enabled)
        self.actions_table.setEnabled(enabled)
        self.btn_launch.setEnabled(enabled)

    def update_action_placeholder(self, action_type):
        if action_type in ["Folder", "App (.exe)", "VS Code"]:
            self.btn_browse.setVisible(True)
            self.btn_browse.setText("📁")
        elif action_type == "Resize Window":
            self.btn_browse.setVisible(True)
            self.btn_browse.setText("🎯")
        else:
            self.btn_browse.setVisible(False)

        if action_type == "Folder":
            self.action_target.setPlaceholderText("e.g. C:\\Projects\\Frontend")
        elif action_type == "URL":
            self.action_target.setPlaceholderText("e.g. https://jira.company.com/board")
        elif action_type == "App (.exe)":
            self.action_target.setPlaceholderText(
                "e.g. C:\\Program Files\\Docker\\Docker Desktop.exe"
            )
        elif action_type == "Command":
            self.action_target.setPlaceholderText("e.g. npm run dev")
        elif action_type == "VS Code":
            self.action_target.setPlaceholderText("Select folder to open in VS Code...")
        elif action_type == "Delay (ms)":
            self.action_target.setPlaceholderText("e.g. 5000 (Waits for 5 seconds)")
        elif action_type == "Captured App":
            self.action_target.setPlaceholderText(
                "Format: Exe_Path | Title Match | x,y,w,h"
            )
        elif action_type == "Resize Window":
            self.action_target.setPlaceholderText(
                "Click the 🎯 target icon to capture an open window ->"
            )

    def browse_target(self):
        a_type = self.action_type.currentText()
        if a_type == "Folder":
            path = QFileDialog.getExistingDirectory(self, "Select Folder")
            if path:
                self.action_target.setText(path)
        elif a_type == "App (.exe)":
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Executable", "", "Executables (*.exe *.bat *.cmd)"
            )
            if path:
                self.action_target.setText(path)
        elif a_type == "VS Code":
            path = QFileDialog.getExistingDirectory(self, "Select Folder for VS Code")
            if path:
                self.action_target.setText(path)
        elif a_type == "Resize Window":
            dialog = WindowCaptureDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.action_target.setText(dialog.selected_target)

    # --- DATABASE LOGIC ---
    def load_workspaces(self):
        self.ws_list.clear()
        self.workspaces.clear()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            for row in cursor.execute(
                "SELECT id, name FROM workspaces ORDER BY name ASC"
            ):
                self.workspaces.append({"id": row[0], "name": row[1]})
                item = QListWidgetItem(row[1])
                item.setData(Qt.ItemDataRole.UserRole, row[0])
                self.ws_list.addItem(item)

        self.update_teardown_visibility()

    def open_context_weaver(self):
        dialog = ContextWeaverDialog(self)
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.captured_workspace_id
        ):
            self.load_workspaces()
            # Select new workspace
            for i in range(self.ws_list.count()):
                if (
                    self.ws_list.item(i).data(Qt.ItemDataRole.UserRole)
                    == dialog.captured_workspace_id
                ):
                    self.ws_list.setCurrentRow(i)
                    self.select_workspace(self.ws_list.item(i))
                    break

    def create_workspace(self):
        name, ok = QInputDialog.getText(self, "New Workspace", "Enter workspace name:")
        if not ok or not name.strip():
            return

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO workspaces (name) VALUES (?)", (name.strip(),)
                )
                ws_id = cursor.lastrowid
                conn.commit()
            self.load_workspaces()

            for i in range(self.ws_list.count()):
                if self.ws_list.item(i).data(Qt.ItemDataRole.UserRole) == ws_id:
                    self.ws_list.setCurrentRow(i)
                    self.select_workspace(self.ws_list.item(i))
                    break
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Error", "A workspace with that name already exists."
            )

    def delete_workspace(self):
        if not self.current_workspace_id:
            return
        reply = QMessageBox.question(
            self,
            "Confirm",
            "Delete this workspace and all its actions?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.teardown_current_workspace()
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM workspaces WHERE id=?", (self.current_workspace_id,)
                )
                conn.commit()
            self.current_workspace_id = None
            self.ws_title.setText("Select a Workspace")
            self.actions_table.setRowCount(0)
            self.set_editor_enabled(False)
            self.load_workspaces()

    def select_workspace(self, item):
        self.current_workspace_id = item.data(Qt.ItemDataRole.UserRole)
        self.ws_title.setText(item.text())
        self.set_editor_enabled(True)
        self.load_actions()
        self.update_teardown_visibility()

    def update_teardown_visibility(self):
        is_running = bool(self.current_workspace_id in self.active_workspaces)
        self.btn_teardown_soft.setVisible(is_running)
        self.btn_teardown_hard.setVisible(is_running)
        if is_running:
            self.btn_launch.setText("↻ RE-LAUNCH")
        else:
            self.btn_launch.setText("🚀 LAUNCH WORKSPACE")

    def load_actions(self):
        self.actions_table.setRowCount(0)
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            for row in cursor.execute(
                "SELECT id, type, target FROM actions WHERE workspace_id=?",
                (self.current_workspace_id,),
            ):
                self.add_action_to_table(row[0], row[1], row[2])

    def add_action_to_table(self, action_id, a_type, target):
        row = self.actions_table.rowCount()
        self.actions_table.insertRow(row)
        type_item = QTableWidgetItem(a_type)
        type_item.setData(Qt.ItemDataRole.UserRole, action_id)
        self.actions_table.setItem(row, 0, type_item)
        self.actions_table.setItem(row, 1, QTableWidgetItem(target))

    def add_action(self):
        a_type = self.action_type.currentText()
        target = self.action_target.text().strip()
        if not target:
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO actions (workspace_id, type, target) VALUES (?, ?, ?)",
                (self.current_workspace_id, a_type, target),
            )
            action_id = cursor.lastrowid
            conn.commit()

        self.add_action_to_table(action_id, a_type, target)
        self.action_target.clear()

    def delete_action(self):
        selected_rows = [item.row() for item in self.actions_table.selectedItems()]
        if not selected_rows:
            return
        row = selected_rows[0]
        action_id = self.actions_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM actions WHERE id=?", (action_id,))
            conn.commit()

        self.actions_table.removeRow(row)

    # --- EXECUTION & WINDOW RESIZING LOGIC ---
    def launch_current_workspace_ui(self):
        if self.current_workspace_id:
            self.launch_workspace_by_id(self.current_workspace_id)

    def _process_pending_resizes(self):
        """Background loop to catch windows as they spawn and resize them."""
        self.resize_attempts += 1
        still_pending = []
        for title, x, y, w, h in self.pending_resizes:
            if not move_matching_windows(title, x, y, w, h):
                still_pending.append((title, x, y, w, h))

        self.pending_resizes = still_pending
        if not self.pending_resizes or self.resize_attempts > 10:
            self.resize_timer.stop()

    def launch_workspace_by_id(self, ws_id):
        # Tear down to prevent duplicates
        if ws_id in self.active_workspaces:
            self.teardown_workspace_by_id(ws_id)

        ws_state = {"processes": [], "titles": []}
        resizes = []

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT type, target FROM actions WHERE workspace_id=?", (ws_id,)
            )
            actions = cursor.fetchall()

        if not actions:
            self.showNormal()
            self.activateWindow()
            QMessageBox.information(
                self, "Empty", "Add some actions to this workspace first."
            )
            return

        self.hide()

        for a_type, target in actions:
            try:
                if a_type == "URL":
                    webbrowser.open(target)
                elif a_type == "Folder":
                    os.startfile(target)
                    folder_name = os.path.basename(target.rstrip("\\/"))
                    ws_state["titles"].append({"type": "folder", "title": folder_name})
                elif a_type == "App (.exe)":
                    proc = subprocess.Popen(target)
                    ws_state["processes"].append(proc)
                    app_name = os.path.basename(target).replace(".exe", "")
                    ws_state["titles"].append({"type": "app", "title": app_name})
                elif a_type == "Captured App":
                    parts = target.split(" | ", 2)
                    exe_path = parts[0]
                    title = parts[1] if len(parts) > 1 else ""
                    bounds = parts[2] if len(parts) > 2 else ""

                    proc = subprocess.Popen(exe_path)
                    ws_state["processes"].append(proc)
                    if title:
                        ws_state["titles"].append({"type": "app", "title": title})
                        if bounds:
                            x, y, w, h = map(int, bounds.split(","))
                            resizes.append((title, x, y, w, h))
                elif a_type == "VS Code":
                    flags = (
                        subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                    )
                    proc = subprocess.Popen(
                        f'code "{target}"', shell=True, creationflags=flags
                    )
                    ws_state["processes"].append(proc)
                    folder_name = os.path.basename(target.rstrip("\\/"))
                    ws_state["titles"].append({"type": "vscode", "title": folder_name})
                elif a_type == "Command":
                    flags = (
                        subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                    )
                    proc = subprocess.Popen(target, shell=True, creationflags=flags)
                    ws_state["processes"].append(proc)
                elif a_type == "Delay (ms)":
                    ms = int(target) if target.isdigit() else 0
                    if ms > 0:
                        loop = QEventLoop()
                        QTimer.singleShot(ms, loop.quit)
                        loop.exec()
                elif a_type == "Resize Window":
                    parts = target.split("|")
                    if len(parts) == 2:
                        title_sub = parts[0].strip()
                        coords = [int(c.strip()) for c in parts[1].split(",")]
                        if len(coords) == 4:
                            resizes.append((title_sub, *coords))
            except Exception as e:
                print(f"Failed to execute {a_type} '{target}': {e}")

        # Save state to allow full teardowns
        self.active_workspaces[ws_id] = ws_state
        if self.current_workspace_id == ws_id:
            self.update_teardown_visibility()

        # Start looking for the windows to resize them!
        if resizes:
            self.pending_resizes.extend(resizes)
            self.resize_attempts = 0
            self.resize_timer.start(500)  # Check every half second

    def teardown_current_workspace(self, force=False):
        if self.current_workspace_id:
            self.teardown_workspace_by_id(self.current_workspace_id, force)

    def teardown_workspace_by_id(self, ws_id, force=False):
        if ws_id not in self.active_workspaces:
            return

        ws_state = self.active_workspaces[ws_id]

        # 1. Kill tracked hard processes
        for proc in ws_state["processes"]:
            try:
                if sys.platform == "win32":
                    f_flag = " /F" if force else ""
                    # Added CREATE_NO_WINDOW so the terminal doesn't briefly flash on screen during kill
                    subprocess.run(
                        f"taskkill{f_flag} /T /PID {proc.pid}",
                        shell=True,
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    if force:
                        proc.kill()
                    else:
                        proc.terminate()
            except Exception:
                pass  # Process might have already died (like the 'code' bootstrapper)

        # 2. Track down and close detached windows safely
        for w_info in ws_state["titles"]:
            close_tracked_window(w_info, force=force)

        self.active_workspaces.pop(ws_id, None)

        if self.current_workspace_id == ws_id:
            self.update_teardown_visibility()


def setup_system_tray(app, manager):
    tray = QSystemTrayIcon(manager)
    icon = (
        QIcon("icon.png")
        if os.path.exists("icon.png")
        else app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    )
    tray.setIcon(icon)
    tray.setToolTip("Context Switcher (Running in background)")

    tray_menu = QMenu()

    # Menu items
    show_action = tray_menu.addAction("Open Workspace Manager")
    show_action.triggered.connect(manager.showNormal)

    spotlight_action = tray_menu.addAction("Nexus Search (Ctrl+Shift+Space)")
    spotlight_action.triggered.connect(manager.launch_nexus)

    tray_menu.addSeparator()

    action_quit = tray_menu.addAction("❌ Quit App")
    action_quit.triggered.connect(lambda: [keyboard.unhook_all(), app.quit()])
    tray_menu.addAction(action_quit)

    tray.setContextMenu(tray_menu)
    tray.show()
    return tray


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Handle Command Line Launching (Headless)
    if "--launch" in sys.argv:
        try:
            ws_id = int(sys.argv[sys.argv.index("--launch") + 1])
            init_db()
            manager = ContextSwitcher()
            manager.launch_workspace_by_id(ws_id)
            sys.exit(0)
        except Exception as e:
            print(f"CLI Launch failed: {e}")
            sys.exit(1)

    init_db()
    window = ContextSwitcher()
    window.show()

    tray_icon = setup_system_tray(app, window)
    sys.exit(app.exec())
