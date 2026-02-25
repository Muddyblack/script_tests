import sys
import os
import sqlite3
import subprocess
import json
import threading
import time
import keyboard
import ctypes
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QFrame,
    QGraphicsDropShadowEffect,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
)
from PyQt6.QtCore import (
    Qt,
    QObject,
    pyqtSignal,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QSize,
)
from PyQt6.QtGui import QColor, QCursor, QGuiApplication

# --- CONFIGURATION (Shared with other apps) ---
APPDATA = os.getenv("APPDATA", ".")
DB_PATH = os.path.join(APPDATA, "context_switcher.db")
X_EXPLORER_DB = os.path.join(APPDATA, "x_explorer_cache.db")
GHOST_TYPIST_DB = os.path.join(APPDATA, "ghost_typist.db")
SETTINGS_FILE = os.path.join(APPDATA, "nexus_settings.json")
USAGE_FILE = os.path.join(APPDATA, "nexus_usage.json")


# --- UTILITIES ---
def format_display_name(name, max_len=60):
    """Middle-elides long filenames to keep the UI clean."""
    if not name:
        return ""
    if len(name) <= max_len:
        return name
    half = (max_len - 3) // 2
    return f"{name[:half]}...{name[-half:]}"


# --- NATIVE WINDOWS HELPERS ---
def run_workspace(ws_id):
    """Launch a workspace by calling the context switcher script."""
    # We assume context_switcher.py is in the same directory
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "context_switcher.py"
    )
    subprocess.Popen([sys.executable, script_path, "--launch", str(ws_id)])


# --- CUSTOM HOTKEY RECORDER DIALOG ---
class HotkeyCapturer(QWidget):
    """A sleek dialog that captures actual keystrokes for hotkey binding."""

    finished = pyqtSignal(str)

    def __init__(self, current_hk):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(400, 200)

        layout = QVBoxLayout(self)
        self.bg = QFrame()
        self.bg.setStyleSheet("""
            QFrame { 
                background: #111827; 
                border: 2px solid #3b82f6; 
                border-radius: 20px; 
            }
            QLabel { color: #f3f4f6; font-family: 'Outfit', sans-serif; }
        """)
        bg_layout = QVBoxLayout(self.bg)

        title = QLabel("PRESS NEW HOTKEY COMBINATION")
        title.setStyleSheet("font-weight: bold; font-size: 16px; color: #60a5fa;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.keys_lbl = QLabel(current_hk.upper())
        self.keys_lbl.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #ffffff;"
        )
        self.keys_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel(
            "Press Enter to Save • Esc to Cancel\n(e.g. Ctrl + Shift + Space)"
        )
        hint.setStyleSheet("color: #6b7280; font-size: 11px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bg_layout.addWidget(title)
        bg_layout.addStretch()
        bg_layout.addWidget(self.keys_lbl)
        bg_layout.addStretch()
        bg_layout.addWidget(hint)

        layout.addWidget(self.bg)
        self.current_parts = []

    def keyPressEvent(self, event):
        key = event.key()
        mod = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self.finished.emit("")
            self.close()
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.current_parts:
                self.finished.emit("+".join(self.current_parts))
                self.close()
            return

        # Map modifiers
        parts = []
        if mod & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mod & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mod & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mod & Qt.KeyboardModifier.MetaModifier:
            parts.append("windows")

        # Map key
        key_name = ""
        # Handle special keys that don't have text representation
        special_keys = {
            Qt.Key.Key_F1: "f1",
            Qt.Key.Key_F2: "f2",
            Qt.Key.Key_F3: "f3",
            Qt.Key.Key_F4: "f4",
            Qt.Key.Key_F5: "f5",
            Qt.Key.Key_F6: "f6",
            Qt.Key.Key_F7: "f7",
            Qt.Key.Key_F8: "f8",
            Qt.Key.Key_F9: "f9",
            Qt.Key.Key_F10: "f10",
            Qt.Key.Key_F11: "f11",
            Qt.Key.Key_F12: "f12",
            Qt.Key.Key_Space: "space",
            Qt.Key.Key_Tab: "tab",
            Qt.Key.Key_Backspace: "backspace",
            Qt.Key.Key_Delete: "delete",
            Qt.Key.Key_Insert: "insert",
            Qt.Key.Key_Home: "home",
            Qt.Key.Key_End: "end",
            Qt.Key.Key_PageUp: "pageup",
            Qt.Key.Key_PageDown: "pagedown",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_Down: "down",
        }

        if key in special_keys:
            key_name = special_keys[key]
        else:
            txt = event.text().lower()
            if txt and txt.strip():
                key_name = txt
            else:
                # Fallback to key sequence name for symbols
                from PyQt6.QtGui import QKeySequence

                key_name = QKeySequence(key).toString().lower()

        # Filter out modifier names that might appear as primary keys
        if key_name in ["ctrl", "shift", "alt", "meta", "win"]:
            key_name = ""

        if key_name and key_name not in parts:
            parts.append(key_name)

        self.current_parts = parts
        self.keys_lbl.setText(" + ".join(parts).upper())


# --- CUSTOM SEARCH INPUT ---
class NexusInput(QLineEdit):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nexus = parent

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Down:
            self.nexus.navigate_results(1)
            event.accept()
        elif event.key() == Qt.Key.Key_Up:
            self.nexus.navigate_results(-1)
            event.accept()
        elif event.key() == Qt.Key.Key_PageDown:
            self.nexus.navigate_results(10)
            event.accept()
        elif event.key() == Qt.Key.Key_PageUp:
            self.nexus.navigate_results(-10)
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.nexus.launch_selected()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.nexus.hide()
            event.accept()
        else:
            super().keyPressEvent(event)


# --- MAIN NEXUS SEARCH UI ---
class NexusSearch(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus Search")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(800, 680)  # Taller window for more results

        # Window State
        self.dragging = False
        self.drag_pos = None

        # Mode State
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
        }
        self.view_mode = "list"
        self.summon_hotkey = "ctrl+shift+space"
        self.is_light_mode = False
        self.load_settings()

        # Usage History
        self.usage_stats = {}
        self.load_usage()

        # Data Cache
        self.workspaces = []
        self.ssh_hosts = []
        self.process_cache = []
        self.last_proc_update = 0
        self.scan_installed_apps()
        self.scan_ssh_hosts()
        self.load_workspaces()

        self.setup_ui()
        self.apply_theme()
        self.center_on_screen()

        # Debounce Timer for Search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

        # Global Input Redirect
        keyboard.on_press(self.on_global_key)

    def scan_installed_apps(self):
        """Scan Windows Start Menu for application shortcuts."""
        paths = [
            os.path.join(
                os.environ.get("ProgramData", "C:\\ProgramData"),
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(
                os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"
            ),
        ]
        self.installed_apps = []
        for p in paths:
            if not os.path.exists(p):
                continue
            for root, _, files in os.walk(p):
                for f in files:
                    if f.lower().endswith((".lnk", ".url")):
                        name = f.rsplit(".", 1)[0]
                        self.installed_apps.append(
                            {"name": name, "path": os.path.join(root, f)}
                        )

    def scan_ssh_hosts(self):
        """Parse ~/.ssh/config for professional SSH sessions."""
        self.ssh_hosts = []
        ssh_config = os.path.expanduser("~/.ssh/config")
        if os.path.exists(ssh_config):
            try:
                with open(ssh_config, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.lower().startswith("host ") and "*" not in line:
                            host = line.split(" ", 1)[1].strip()
                            if host:
                                self.ssh_hosts.append(host)
            except Exception:
                pass

    def on_global_key(self, event):
        """Expert-level focus management: redirect keys to Nexus if visible."""
        if not self.isVisible():
            return

        # If Nexus is visible but NOT active, intercept major control keys
        if not self.isActiveWindow():
            # Support both standard names and common aliases
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
            elif key_name == "esc" or key_name == "escape":
                self.hide()
                return

            # If it's a single character/digit, grab focus AND redirect the character
            if len(key_name) == 1:
                # IMPORTANT: Only redirect if NO modifiers (except Shift) are pressed.
                # This allows Ctrl+C, Ctrl+V, Alt+Tab, etc. to work in the background app.
                if (
                    keyboard.is_pressed("ctrl")
                    or keyboard.is_pressed("alt")
                    or keyboard.is_pressed("windows")
                ):
                    return

                # Redirect character to nexus search input immediately
                self.search_input.setText(self.search_input.text() + event.name)
                # And force focus
                QTimer.singleShot(0, self.summon_and_focus)
                return

    def summon_and_focus(self):
        """Aggressively grab focus for the search input on Windows using Thread Input attachment."""
        self.show()
        self.raise_()
        self.activateWindow()

        # Windows-specific foreground logic (The "Aggressive" Way)
        hwnd = int(self.winId())

        # Get the thread IDs
        foreground_thread = ctypes.windll.user32.GetWindowThreadProcessId(
            ctypes.windll.user32.GetForegroundWindow(), None
        )
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()

        # Attach input threads (allows us to 'steal' focus)
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

        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW

        # Ensure the input field specifically handles the cursor
        self.search_input.setFocus(Qt.FocusReason.OtherFocusReason)
        self.search_input.activateWindow()

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
                    # Optional: Wrap around in tree? (Complex, so we just stop at boundaries)
                    break
            self.results_tree.setCurrentItem(target)
        else:
            idx = self.results_list.currentRow()
            count = self.results_list.count()
            if count > 0:
                # Optimized wrap-around navigation
                new_idx = (idx + delta) % count
                self.results_list.setCurrentRow(new_idx)

    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.modes.update(
                            {
                                k: v
                                for k, v in data.items()
                                if k not in ["hotkey", "light_mode"]
                            }
                        )
                        self.summon_hotkey = data.get("hotkey", "ctrl+shift+space")
                        self.is_light_mode = data.get("light_mode", False)
        except Exception:
            pass

    def save_settings(self):
        try:
            settings = self.modes.copy()
            settings["hotkey"] = self.summon_hotkey
            settings["light_mode"] = self.is_light_mode
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f)
        except Exception:
            pass

    def load_usage(self):
        try:
            if os.path.exists(USAGE_FILE):
                with open(USAGE_FILE, "r") as f:
                    self.usage_stats = json.load(f)
        except Exception:
            self.usage_stats = {}

    def record_usage(self, key):
        """Increments usage count for a specific item key (e.g., path or id)."""
        count = self.usage_stats.get(key, 0) + 1
        self.usage_stats[key] = count
        try:
            with open(USAGE_FILE, "w") as f:
                json.dump(self.usage_stats, f)
        except Exception:
            pass

    def get_usage_boost(self, key):
        """Calculates a score boost based on how many times an item was used."""
        count = self.usage_stats.get(key, 0)
        # Cap the boost so a favorite file doesn't override a perfect match workspace
        return min(count * 50, 600)

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

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("nexus_bg")

        # Drop Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(12)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.bg_frame.setGraphicsEffect(shadow)

        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(25, 20, 25, 12)
        bg_layout.setSpacing(12)

        # Header Area
        header_layout = QHBoxLayout()
        self.search_input = NexusInput(self)
        self.search_input.setObjectName("nexus_search")
        self.search_input.setPlaceholderText(
            "Search Workspaces, Files, Macros, or Scripts..."
        )
        self.search_input.textChanged.connect(lambda: self.search_timer.start(50))
        header_layout.addWidget(self.search_input)

        bg_layout.addLayout(header_layout)

        # Mode Bar
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(10)
        self.mode_btns = {}

        modes_metadata = [
            ("apps", "📦 Apps"),
            ("workspaces", "🚀 Workspaces"),
            ("files", "📄 Files"),
            ("macros", "⌨️ Macros"),
            ("scripts", "🐍 Scripts"),
            ("ssh", "🔗 SSH"),
            ("processes", "💥 Processes"),
            ("toggles", "⚙️ Toggles"),
        ]

        for key, label in modes_metadata:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(self.modes[key])
            btn.setObjectName("mode_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self.toggle_mode(k, checked))
            mode_layout.addWidget(btn)
            self.mode_btns[key] = btn

        mode_layout.addStretch()
        bg_layout.addLayout(mode_layout)

        # Folder selection UI area
        self.filter_bar = QFrame()
        self.filter_bar.setObjectName("filter_bar")
        self.filter_bar.setVisible(self.modes.get("files", False))
        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setContentsMargins(10, 0, 10, 0)

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

        self.btn_pick_folders = QPushButton("Pick Search Folders...")
        self.btn_pick_folders.setObjectName("mode_btn")
        self.btn_pick_folders.clicked.connect(self.show_folder_picker)

        self.btn_view_toggle = QPushButton("🌲 Tree")
        self.btn_view_toggle.setCheckable(True)
        self.btn_view_toggle.setObjectName("mode_btn")
        self.btn_view_toggle.clicked.connect(self.toggle_view_mode)

        lbl = QLabel("Filters:")
        lbl.setObjectName("filter_label")
        filter_layout.addWidget(lbl)
        filter_layout.addWidget(self.btn_f_only)
        filter_layout.addWidget(self.btn_d_only)
        filter_layout.addWidget(self.btn_view_toggle)
        filter_layout.addStretch()
        filter_layout.addWidget(self.btn_pick_folders)

        bg_layout.addLayout(QHBoxLayout())  # Spacer
        bg_layout.addWidget(self.filter_bar)

        # Results Container
        self.results_stack = QStackedWidget()
        self.results_stack.setObjectName("results_stack")

        # Results List
        self.results_list = QListWidget()
        self.results_list.setObjectName("nexus_list")
        self.results_list.itemDoubleClicked.connect(self.launch_selected)

        # Results Tree
        self.results_tree = QTreeWidget()
        self.results_tree.setObjectName("nexus_tree")
        self.results_tree.viewport().setStyleSheet("background: transparent;")
        self.results_tree.setHeaderHidden(True)
        self.results_tree.setIndentation(20)
        self.results_tree.itemDoubleClicked.connect(self.launch_selected)

        self.results_stack.addWidget(self.results_list)
        self.results_stack.addWidget(self.results_tree)
        bg_layout.addWidget(self.results_stack)

        # Action Handler for List Item Selection
        self.results_list.currentRowChanged.connect(self.on_item_hover)

        # Footer / Action Hint
        footer_layout = QHBoxLayout()
        self.status_lbl = QLabel("Ready to launch...")
        self.status_lbl.setObjectName("status_text")
        footer_layout.addWidget(self.status_lbl)
        footer_layout.addStretch()

        hint_lbl = QLabel("Enter to Run • Esc to Hide")
        hint_lbl.setObjectName("hint_text")
        footer_layout.addWidget(hint_lbl)

        bg_layout.addLayout(footer_layout)
        main_layout.addWidget(self.bg_frame)

    def toggle_mode(self, mode, checked):
        self.modes[mode] = checked
        if mode == "files":
            self.filter_bar.setVisible(checked)
        if mode == "processes" and checked:
            self.update_process_cache(force=True)
        self.save_settings()
        self.perform_search()

    def toggle_view_mode(self, checked):
        self.view_mode = "tree" if checked else "list"
        self.results_stack.setCurrentIndex(1 if checked else 0)
        self.btn_view_toggle.setText("📄 List" if checked else "🌲 Tree")
        self.perform_search()

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
        # Load managed folders from X-Explorer
        managed = []
        if os.path.exists(X_EXPLORER_DB):
            try:
                with sqlite3.connect(X_EXPLORER_DB) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM settings WHERE key='folders'")
                    res = cursor.fetchone()
                    if res:
                        try:  # JSON format
                            folders_data = json.loads(res[0])
                            managed = [f["path"] for f in folders_data]
                        except json.JSONDecodeError:  # Old pipe format
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

        # Show a simple multi-selection menu or similar
        # For Nexus, we can just use a list in results
        self.status_lbl.setText("Select Search Folders (ESC to return)")
        self.results_list.clear()

        # Add clear filter option
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        """Auto-hide when clicking outside reliably."""
        # Use a tiny delay to see if focus actually landed on a child widget
        QTimer.singleShot(150, self.check_focus_and_hide)
        super().focusOutEvent(event)

    def check_focus_and_hide(self):
        if not self.isActiveWindow() and self.isVisible():
            self.hide()

    def center_on_screen(self):
        # Reliably find screen where the mouse is
        cursor_pos = QCursor.pos()
        screen = None
        for s in QGuiApplication.screens():
            if s.geometry().contains(cursor_pos):
                screen = s
                break

        if not screen:
            screen = QGuiApplication.primaryScreen()

        screen_geo = screen.geometry()

        # Perfectly center horizontally, and set at 20% height for visibility
        x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
        y = screen_geo.y() + int(screen_geo.height() * 0.2)
        self.move(x, y)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

    def hide(self):
        # Clean up global hooks
        for hk in ["esc", "up", "down", "enter"]:
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        super().hide()

    def summon(self):
        self.load_workspaces()  # Refresh workspaces list
        self.center_on_screen()
        self.search_input.clear()
        self.perform_search()

        # Force foreground priority
        self.setWindowOpacity(0)
        self.show()
        self.raise_()
        self.activateWindow()

        # Bind temporary global navigation to ensure it works even without focus
        try:
            keyboard.add_hotkey("esc", self.hide)
            keyboard.add_hotkey("up", lambda: self.navigate_results(-1))
            keyboard.add_hotkey("down", lambda: self.navigate_results(1))
            keyboard.add_hotkey("enter", self.launch_selected)
        except (ValueError, KeyError, OSError):
            pass

        # Super-Aggressive Focus Logic: Multiple stages to ensure focus on Windows
        self.summon_and_focus()
        QTimer.singleShot(10, self.summon_and_focus)
        QTimer.singleShot(100, self.summon_and_focus)
        QTimer.singleShot(300, self.summon_and_focus)

        # Fade In
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(250)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

    def perform_search(self):
        search = self.search_input.text().lower().strip()
        self.results_list.clear()
        self.results_tree.clear()
        candidates = []

        def matches_all_terms(text, terms):
            if not terms:
                return True
            tl = text.lower()
            return all(t in tl for t in terms)

        # 0. CHRONOS QUICK-LOG (Logging achievement via + prefix)
        if search.startswith("+") and len(search) > 1:
            log_text = search[1:].strip()
            candidates.append(
                {
                    "score": 10000,  # Absolute priority
                    "title": f"CHRONOS: Log '{log_text}'",
                    "path": "Record this achievement instantly to Chronos Hub",
                    "icon": "🏆",
                    "color": "#fbbf24",
                    "data": {"type": "chronos_log", "content": log_text},
                }
            )
            self.results_list.clear()
            self.results_tree.clear()
            # We skip other searches if we are in log mode to keep it clean
            self.populate_list_results(candidates)
            return

        # Prefix logic (Flow Launcher style)
        prefixes = {
            ":w": "workspaces",
            ":f": "files",
            ":m": "macros",
            ":s": "scripts",
            ":p": "processes",
            ":t": "toggles",
            ":ssh": "ssh",
            ":a": "apps",
        }
        active_modes = self.modes.copy()
        search_term = search

        for pref, mode_key in prefixes.items():
            if search.startswith(pref + " ") or search == pref:
                # Disable others if a prefix is present
                for k in active_modes:
                    if k in prefixes.values():
                        active_modes[k] = False
                active_modes[mode_key] = True
                search_term = search[len(pref) :].strip()
                break

        terms = [t for t in search_term.split() if t]

        # Update Footer / Hint
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
                    "📡",
                    "#60a5fa",
                ),
                (
                    "Change Summon Hotkey",
                    f"Current: {self.summon_hotkey}",
                    "change_hotkey",
                    "⌨️",
                    "#fbbf24",
                ),
            ]
            for title, path, cmd, icon, color in mgmt_cmds:
                if not terms or matches_all_terms(title, t_terms):
                    candidates.append(
                        {
                            "score": score_base,
                            "title": title,
                            "path": f"System Command • {path}",
                            "icon": icon,
                            "color": color,
                            "data": {"type": "cmd", "cmd": cmd},
                        }
                    )

            power_commands = [
                (
                    "Toggle Dark/Light Mode",
                    "System Theme Preference",
                    "toggle_dark_mode",
                    "🌓",
                    ["dark", "light", "theme", "night"],
                ),
                (
                    "Toggle Hidden Files",
                    "Explorer View Settings",
                    "toggle_hidden_files",
                    "👁️",
                    ["hidden", "files", "view", "explorer"],
                ),
                (
                    "Toggle Desktop Icons",
                    "Show/Hide Desktop Shortcuts",
                    "toggle_desktop_icons",
                    "🔳",
                    ["icons", "desktop", "shortcuts"],
                ),
                (
                    "Toggle System Mute",
                    "Audio Master Control",
                    "toggle_mute",
                    "🔇",
                    ["mute", "audio", "volume", "sound"],
                ),
                (
                    "Show/Hide Desktop",
                    "Minimize All Windows",
                    "toggle_desktop",
                    "🖥️",
                    ["desktop", "reveal", "hide"],
                ),
                (
                    "Restart Windows Explorer",
                    "Refresh UI & Taskbar",
                    "restart_explorer",
                    "🔄",
                    ["restart", "explorer", "refresh", "taskbar"],
                ),
                (
                    "Flush DNS Cache",
                    "Network Reset Utility",
                    "flush_dns",
                    "🌐",
                    ["dns", "flush", "network", "reset"],
                ),
                (
                    "Lock Workstation",
                    "Secure Current Session",
                    "cmd_lock",
                    "🔒",
                    ["lock", "security", "sign out"],
                ),
                (
                    "Put PC to Sleep",
                    "Low Power Standby",
                    "cmd_sleep",
                    "💤",
                    ["sleep", "standby", "power"],
                ),
                (
                    "Restart Computer",
                    "Full System Reboot",
                    "cmd_restart",
                    "♻️",
                    ["restart", "reboot", "power"],
                ),
                (
                    "Shutdown System",
                    "Power Off Complete",
                    "cmd_shutdown",
                    "🛑",
                    ["shutdown", "power off", "exit"],
                ),
                (
                    "Windows Settings",
                    "System Dashboard",
                    "ms-settings:default",
                    "⚙️",
                    ["settings", "config", "windows"],
                ),
                (
                    "Display Settings",
                    "Resolution & Brightness",
                    "ms-settings:display",
                    "📺",
                    ["display", "monitor", "resolution", "brightness"],
                ),
                (
                    "Wi-Fi Settings",
                    "Wireless Connections",
                    "ms-settings:network-wifi",
                    "📶",
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
                            "path": f"System Control • {path}",
                            "icon": icon,
                            "color": "#a855f7",
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
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            script_paths = [curr_dir, os.path.join(APPDATA, "scripts")]
            for spath in script_paths:
                if not os.path.exists(spath):
                    continue
                for f in os.listdir(spath):
                    if f.endswith(".py") and f not in [
                        "nexus_launcher.py",
                        "nexus_search.py",
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

        # 6. File Search (X-Explorer DB)
        # 6. File Search (X-Explorer DB + Fallback DB)
        if active_modes.get("files"):
            for database in [X_EXPLORER_DB, DB_PATH]:
                if not os.path.exists(database):
                    continue
                try:
                    with sqlite3.connect(database) as conn:
                        cursor = conn.cursor()
                        f_conds, f_params = [], []
                        if terms:
                            f_conds.append(
                                "(" + " AND ".join(["name LIKE ?" for _ in terms]) + ")"
                            )
                            f_params.extend([f"%{t}%" for t in terms])

                        if active_modes.get("files_only"):
                            f_conds.append("is_dir = 0")
                        elif active_modes.get("folders_only"):
                            f_conds.append("is_dir = 1")

                        target_folders = active_modes.get("target_folders", [])
                        if target_folders:
                            path_conds = ["path LIKE ?" for _ in target_folders]
                            f_params.extend([f"{p}%" for p in target_folders])
                            f_conds.append(f"({' OR '.join(path_conds)})")

                        sql = (
                            "SELECT name, path, is_dir FROM files WHERE "
                            + (" AND ".join(f_conds) if f_conds else "1")
                            + " LIMIT 100"
                        )
                        cursor.execute(sql, f_params)
                        for name, path, is_dir in cursor.fetchall():
                            score = 200 + (50 if is_dir else 0)
                            if search_term and name.lower() == search_term:
                                score += 500
                            score += self.get_usage_boost(f"file_{path}")
                            candidates.append(
                                {
                                    "score": score,
                                    "title": format_display_name(name),
                                    "path": path,
                                    "icon": "📁" if is_dir else "📄",
                                    "data": {"type": "file", "path": path},
                                }
                            )
                except Exception:
                    pass

        # 7. Processes
        if active_modes.get("processes") and terms:
            self.update_process_cache()
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

    def populate_list_results(self, candidates):
        for c in candidates[:100]:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, c["data"])
            self.results_list.addItem(item)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(15)
            icon_label = QLabel(c.get("icon", "🔹"))
            icon_label.setStyleSheet("font-size: 20px;")
            row_layout.addWidget(icon_label)
            text_container = QVBoxLayout()
            text_container.setContentsMargins(0, 0, 0, 0)
            text_container.setSpacing(2)
            title_lbl = QLabel(c["title"])
            title_lbl.setObjectName("item_title")
            if "color" in c:
                title_lbl.setStyleSheet(f"color: {c['color']};")
            path_lbl = QLabel(format_display_name(c.get("path", ""), max_len=80))
            path_lbl.setObjectName("item_path")
            text_container.addWidget(title_lbl)
            text_container.addWidget(path_lbl)
            row_layout.addLayout(text_container, stretch=1)
            item.setSizeHint(QSize(row_widget.sizeHint().width(), 62))
            self.results_list.setItemWidget(item, row_widget)

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)

    def populate_tree_results(self, candidates):
        # Adapt X-Explorer tree logic for Nexus
        tree_data = {}
        for c in candidates[:150]:  # More items in tree is okay
            path = c.get("path", "")
            if os.path.isabs(path):
                parts = path.split(os.sep)
                current = tree_data
                for i, part in enumerate(parts):
                    if not part and i == 0:
                        continue  # handle C:\
                    if part not in current:
                        current[part] = {"_data": None, "_children": {}}
                    if i == len(parts) - 1:
                        current[part]["_data"] = c
                    current = current[part]["_children"]
            else:
                # Group non-file items under a cleaner "System & Core" category
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
                    icon = content["_data"].get("icon", "🔹")
                    item.setText(0, f"{icon} {name}")
                else:
                    item.setText(0, f"📁 {name}")
                    item.setForeground(0, QColor("#60a5fa"))  # Better visibility

                if content["_children"]:
                    add_items_to_tree(item, content["_children"])
                    item.setExpanded(True)

        add_items_to_tree(None, tree_data)

    def on_item_hover(self, row):
        if row >= 0:
            item = self.results_list.item(row)
            if item:
                pass  # System is ready for future hover metadata (like status bar updates)

    def launch_selected(self):
        # Works for both List and Tree items
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
            return  # Directory in tree might not have data

        # Smart Hide: Don't hide for internal UI commands like selection pickers
        should_hide = True
        if data.get("type") in ["filter_toggle", "filter_clear"]:
            should_hide = False
        elif data["type"] == "cmd" and data["cmd"] in [
            "reset_position",
            "change_hotkey",
        ]:
            should_hide = False

        if should_hide:
            self.hide()

        if data.get("type") == "filter_toggle":
            path = data["path"]
            if path in self.modes.get("target_folders", []):
                self.modes["target_folders"].remove(path)
            else:
                self.modes["target_folders"].append(path)
            self.save_settings()
            self.show_folder_picker()  # Refresh
            return
        elif data.get("type") == "filter_clear":
            self.modes["target_folders"] = []
            self.save_settings()
            self.show_folder_picker()  # Refresh
            return
        elif data.get("type") == "app":
            os.startfile(data["path"])
        elif data.get("type") == "workspace":
            self.record_usage(f"ws_{data['id']}")
            run_workspace(data["id"])
        elif data["type"] == "cmd":
            if data["cmd"] == "reindex_files":
                self.trigger_reindex()
            elif data["cmd"] == "change_hotkey":
                self.request_new_hotkey()
            elif (
                data["cmd"].startswith("toggle_")
                or data["cmd"].startswith("cmd_")
                or data["cmd"].startswith("ms-settings:")
                or data["cmd"] in ["flush_dns", "restart_explorer", "toggle_desktop"]
            ):
                self.execute_system_toggle(data["cmd"])
        elif data["type"] == "script":
            self.record_usage(f"script_{data['path']}")
            subprocess.Popen([sys.executable, data["path"]])
        elif data["type"] == "file":
            self.record_usage(f"file_{data['path']}")
            os.startfile(data["path"])
        elif data["type"] == "macro":
            self.record_usage(f"macro_{data['id']}")
            # Logic to run macro (copy/paste from previous)
            self._run_macro(data["id"])
        elif data["type"] == "process":
            self.kill_process(data["pid"], data["name"])
        elif data["type"] == "ssh":
            self.status_lbl.setText(f"🔗 Connecting to {data['host']}...")
            subprocess.Popen(f"start cmd /k ssh {data['host']}", shell=True)
        elif data["type"] == "chronos_log":
            self._log_to_chronos(data["content"])

    def _log_to_chronos(self, text):
        """Helper to inject achievement into Chronos DB."""
        import sqlite3
        import datetime

        impact = "Medium"
        if text.startswith("!!! "):
            impact, text = "High", text[4:]
        elif text.startswith(". "):
            impact, text = "Low", text[2:]

        try:
            db_path = os.path.join(os.getenv("APPDATA", "."), "chronos_achievements.db")
            now = datetime.datetime.now()
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO achievements (content, impact, week_number, year) VALUES (?, ?, ?, ?)",
                    (text, impact, now.isocalendar()[1], now.year),
                )
            self.status_lbl.setText(f"🏆 Logged to Chronos: {text}")
            self.status_lbl.setStyleSheet("color: #fbbf24; font-weight: bold;")
        except Exception as e:
            self.status_lbl.setText(f"Chronos Log Error: {e}")

    def update_process_cache(self, force=False):
        """Fetches running processes using tasklist (throttled)."""
        now = time.time()
        if not force and now - self.last_proc_update < 5:  # 5 sec throttle
            return

        try:
            # Use tasklist for Windows (no dependencies needed)
            output = subprocess.check_output("tasklist /fo csv /nh", shell=True).decode(
                "utf-8", errors="ignore"
            )
            lines = output.strip().split("\n")
            new_cache = []
            for line in lines:
                parts = line.replace('"', "").split(",")
                if len(parts) >= 5:
                    new_cache.append(
                        {"name": parts[0], "pid": parts[1], "mem": parts[4]}
                    )
            self.process_cache = new_cache
            self.last_proc_update = now
        except Exception:
            pass

    def kill_process(self, pid, name):
        """Terminates a process by PID."""
        try:
            subprocess.Popen(f"taskkill /F /PID {pid}", shell=True)
            self.status_lbl.setText(f"💀 Terminated: {name}")
            self.status_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
            # Refresh cache after a small delay
            QTimer.singleShot(500, lambda: self.update_process_cache(force=True))
        except Exception as e:
            self.status_lbl.setText(f"Error killing {name}: {e}")

    def trigger_reindex(self):
        """Launches X-Explorer in indexing mode."""
        self.status_lbl.setText("📡 Triggering File Indexer...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        xe_path = os.path.join(script_dir, "xexplorer.py")
        subprocess.Popen([sys.executable, xe_path])

    def request_new_hotkey(self):
        """Asks the user to press a key combination."""
        self.recorder = HotkeyCapturer(self.summon_hotkey)
        self.recorder.show()
        # Center the recorder on the hub
        self.recorder.move(
            self.x() + (self.width() - self.recorder.width()) // 2,
            self.y() + (self.height() - self.recorder.height()) // 2,
        )
        self.recorder.finished.connect(self.on_hotkey_recorded)

    def on_hotkey_recorded(self, new_hk):
        if new_hk:
            old_hk = self.summon_hotkey
            self.summon_hotkey = new_hk.lower().strip()
            self.save_settings()
            rebind_hotkey(old_hk, self.summon_hotkey)
            self.status_lbl.setText(f"⌨️ Hotkey updated to: {self.summon_hotkey}")
            self.status_lbl.setStyleSheet("color: #10b981; font-weight: bold;")
            # Re-perform search to update the label
            self.perform_search()

    def execute_system_toggle(self, cmd):
        """Executes Windows system level toggles."""
        try:
            if cmd == "toggle_dark_mode":
                # Check current state first
                import winreg

                path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    path,
                    0,
                    winreg.KEY_READ | winreg.KEY_WRITE,
                )
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                new_state = 0 if value == 1 else 1
                winreg.SetValueEx(
                    key, "AppsUseLightTheme", 0, winreg.REG_DWORD, new_state
                )
                winreg.SetValueEx(
                    key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, new_state
                )
                winreg.CloseKey(key)
                state_name = "Dark" if new_state == 0 else "Light"
                self.status_lbl.setText(f"🌓 System Theme set to {state_name}")
                # Sync Nexus Theme immediately
                self.is_light_mode = new_state == 1
                self.save_settings()
                self.apply_theme()

            elif cmd == "toggle_hidden_files":
                import winreg

                path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    path,
                    0,
                    winreg.KEY_READ | winreg.KEY_WRITE,
                )
                value, _ = winreg.QueryValueEx(key, "Hidden")
                new_state = 1 if value == 2 else 2  # 1=Show, 2=Hide
                winreg.SetValueEx(key, "Hidden", 0, winreg.REG_DWORD, new_state)
                winreg.CloseKey(key)

                # Refresh explorer
                subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], shell=True)
                subprocess.Popen(["explorer.exe"])
                state_name = "VISIBLE" if new_state == 1 else "HIDDEN"
                self.status_lbl.setText(f"👁️ Hidden Files: {state_name}")

            elif cmd == "toggle_desktop_icons":
                import winreg

                path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    path,
                    0,
                    winreg.KEY_READ | winreg.KEY_WRITE,
                )
                value, _ = winreg.QueryValueEx(key, "HideIcons")
                new_state = 1 if value == 0 else 0
                winreg.SetValueEx(key, "HideIcons", 0, winreg.REG_DWORD, new_state)
                winreg.CloseKey(key)
                # Refresh desktop
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        '(New-Object -ComObject Shell.Application).Namespace(0).Self.InvokeVerb("Refresh")',
                    ],
                    shell=True,
                )
                state_name = "HIDDEN" if new_state == 1 else "VISIBLE"
                self.status_lbl.setText(f"� Desktop Icons: {state_name}")

            elif cmd == "toggle_mute":
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "(new-object -com wscript.shell).SendKeys([char]173)",
                    ],
                    shell=True,
                )
                self.status_lbl.setText("🔇 Master Audio Toggled")

            elif cmd == "flush_dns":
                subprocess.run(["ipconfig", "/flushdns"], shell=True)
                self.status_lbl.setText("🌐 DNS Cache Flushed")

            elif cmd == "restart_explorer":
                subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], shell=True)
                subprocess.Popen(["explorer.exe"])
                self.status_lbl.setText("🔄 Windows Explorer Restarted")

            elif cmd == "toggle_desktop":
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "(New-Object -ComObject shell.application).toggleDesktop()",
                    ],
                    shell=True,
                )
                self.status_lbl.setText("🖥️ Desktop Toggled")

            # --- POWER CONTROLS ---
            elif cmd == "cmd_lock":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
                self.status_lbl.setText("🔒 Workstation Locked")

            elif cmd == "cmd_sleep":
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "Add-Type -Assembly System.Windows.Forms; "
                        + "[System.Windows.Forms.Application]::SetSuspendState("
                        + "[System.Windows.Forms.PowerState]::Suspend, $false, $false)",
                    ],
                    shell=True,
                )
                self.status_lbl.setText("💤 System Sleeping...")

            elif cmd == "cmd_restart":
                subprocess.run(["shutdown", "/r", "/t", "0"])

            elif cmd == "cmd_shutdown":
                subprocess.run(["shutdown", "/s", "/t", "0"])

            # --- SETTINGS LAUNCHERS ---
            elif cmd.startswith("ms-settings:"):
                # Dynamically launch any Windows settings URI
                import webbrowser

                webbrowser.open(cmd)
                setting_name = cmd.split(":")[-1].replace("-", " ").upper()
                self.status_lbl.setText(f"⚙️ Launched: {setting_name}")

            self.status_lbl.setStyleSheet("color: #a855f7; font-weight: bold;")

        except Exception as e:
            self.status_lbl.setText(f"Error executing toggle: {e}")
            self.status_lbl.setStyleSheet("color: #ef4444;")

    def _run_macro(self, macro_id):
        # We'll just define a minimal runner here
        def runner():
            try:
                with sqlite3.connect(GHOST_TYPIST_DB) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT actions FROM macros WHERE id=?", (macro_id,))
                    res = cursor.fetchone()
                    if res:
                        import pyautogui

                        actions = json.loads(res[0])
                        time.sleep(0.3)
                        for a in actions:
                            if a["type"] == "wait":
                                time.sleep(a["value"] / 1000.0)
                            elif a["type"] == "type":
                                pyautogui.write(a["value"], interval=0.01)
                            elif a["type"] == "press":
                                pyautogui.press(a["value"])
                            elif a["type"] == "click":
                                pyautogui.click(x=a["x"], y=a["y"])
            except Exception:
                pass

        threading.Thread(target=runner, daemon=True).start()

    def apply_theme(self):
        if self.is_light_mode:
            # --- VIBRANT LIGHT THEME ---
            self.setStyleSheet("""
                QWidget#nexus_bg {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                        stop:0 rgba(255, 255, 255, 245), 
                        stop:1 rgba(240, 243, 248, 255));
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 30px;
                }
                QLineEdit#nexus_search {
                    background: rgba(0, 0, 0, 0.04);
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 12px;
                    padding: 10px 20px;
                    color: #111827;
                    font-size: 16px;
                    font-family: 'Outfit', 'Inter', 'Segoe UI';
                }
                QLineEdit#nexus_search:focus {
                    border: 1px solid rgba(59, 130, 246, 0.5);
                    background: #ffffff;
                }
                QPushButton#mode_btn {
                    background: rgba(0, 0, 0, 0.03);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 10px;
                    padding: 6px 14px;
                    color: #4b5563;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton#mode_btn:checked {
                    background: rgba(59, 130, 246, 0.12);
                    border: 1px solid rgba(59, 130, 246, 0.4);
                    color: #1d4ed8;
                }
                QPushButton#mode_btn:hover {
                    background: rgba(0, 0, 0, 0.08);
                }
                QListWidget#nexus_list {
                    background: transparent;
                    border: none;
                    outline: none;
                }
                QListWidget#nexus_list::item {
                    background: rgba(0, 0, 0, 0.02);
                    border-radius: 18px;
                    margin-bottom: 8px;
                    padding: 2px 18px;
                    color: #1f2937;
                    border: 1px solid transparent;
                }
                QListWidget#nexus_list::item:selected {
                    background: rgba(59, 130, 246, 0.08);
                    border: 1px solid rgba(59, 130, 246, 0.15);
                }
                QLabel#item_title { color: #111827; font-size: 15px; font-weight: 600; }
                QLabel#item_path { color: #6b7280; font-size: 11px; }
                QLabel#status_text, QLabel#hint_text { color: #9ca3af; font-size: 11px; font-weight: 500; }
                QFrame#filter_bar { background: rgba(0, 0, 0, 0.02); border-radius: 12px; margin-bottom: 5px; }
                QTreeWidget#nexus_tree { background: transparent !important; color: #1f2937; border: none; font-size: 14px; outline: none; }
                QTreeWidget#nexus_tree::viewport { background: transparent; }
                QTreeWidget#nexus_tree::item {
                    padding: 10px 14px;
                    border-bottom: 1px solid rgba(0, 0, 0, 0.03);
                    border-radius: 12px;
                    margin-bottom: 4px;
                    background: rgba(0, 0, 0, 0.015);
                }
                QTreeWidget#nexus_tree::item:selected {
                    background: rgba(59, 130, 246, 0.08);
                    color: #1d4ed8;
                    border: 1px solid rgba(59, 130, 246, 0.2);
                }
                QStackedWidget#results_stack {
                    background: transparent;
                    border: none;
                }
            """)
        else:
            # --- PREMIUM DARK THEME ---
            self.setStyleSheet("""
                QWidget#nexus_bg {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                        stop:0 rgba(15, 25, 45, 220), 
                        stop:0.4 rgba(10, 15, 30, 210), 
                        stop:1 rgba(7, 10, 20, 230));
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 30px;
                }
                QLineEdit#nexus_search {
                    background: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 12px;
                    padding: 10px 20px;
                    color: #e5e7eb;
                    font-size: 16px;
                    font-family: 'Outfit', 'Inter', 'Segoe UI';
                }
                QLineEdit#nexus_search:focus {
                    border: 1px solid rgba(96, 165, 250, 0.5);
                    background: rgba(0, 0, 0, 0.3);
                }
                QPushButton#mode_btn {
                    background: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.06);
                    border-radius: 10px;
                    padding: 6px 14px;
                    color: #94a3b8;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton#mode_btn:checked {
                    background: rgba(59, 130, 246, 0.2);
                    border: 1px solid rgba(59, 130, 246, 0.5);
                    color: #60a5fa;
                }
                QListWidget#nexus_list { background: transparent; border: none; outline: none; }
                QListWidget#nexus_list::item {
                    background: rgba(255, 255, 255, 0.02);
                    border-radius: 18px;
                    margin-bottom: 8px;
                    padding: 2px 18px;
                    color: #d1d5db;
                    border: 1px solid transparent;
                }
                QListWidget#nexus_list::item:selected {
                    background: rgba(255, 255, 255, 0.06);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }
                QLabel#item_title { color: #ffffff; font-size: 15px; font-weight: 600; }
                QLabel#item_path { color: rgba(255, 255, 255, 0.45); font-size: 11px; }
                QLabel#status_text, QLabel#hint_text { color: rgba(255, 255, 255, 0.35); font-size: 11px; font-weight: 500; }
                QFrame#filter_bar { background: rgba(255, 255, 255, 0.02); border-radius: 12px; margin-bottom: 5px; }
                QTreeWidget#nexus_tree { background: transparent !important; color: #d1d5db; border: none; font-size: 14px; outline: none; }
                QTreeWidget#nexus_tree::viewport { background: transparent; }
                QTreeWidget#nexus_tree::item {
                    padding: 10px 14px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.02);
                    border-radius: 12px;
                    margin-bottom: 4px;
                    background: rgba(255, 255, 255, 0.01);
                }
                QTreeWidget#nexus_tree::item:selected {
                    background: rgba(59, 130, 246, 0.1);
                    color: #60a5fa;
                    border: 1px solid rgba(59, 130, 246, 0.2);
                }
                QStackedWidget#results_stack {
                    background: transparent;
                    border: none;
                }
            """)


# --- SIGNAL HUB (For Thread-Safe Communication) ---
class NexusBridge(QObject):
    toggle_signal = pyqtSignal()


# --- MAIN EXECUTION ---
app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

nexus = NexusSearch()
bridge = NexusBridge()

# Connect the signal (triggered from BG thread) to the UI method (runs on Main thread)
bridge.toggle_signal.connect(
    lambda: nexus.summon() if not nexus.isVisible() else nexus.hide()
)


def on_toggle():
    bridge.toggle_signal.emit()


def rebind_hotkey(old_hk, new_hk):
    try:
        keyboard.unhook_all()
        keyboard.add_hotkey(new_hk, on_toggle)
        # CRITICAL: re-hook the global interceptor or app will "hang/freeze"
        # because the window exists but no longer intercepts navigation keys
        if hasattr(nexus, "on_global_key"):
            keyboard.on_press(nexus.on_global_key)
        print(f"Hotkey bound to: {new_hk}")
    except Exception as e:
        print(f"Failed to rebind hotkey: {e}")


# Initial Bind
try:
    keyboard.add_hotkey(nexus.summon_hotkey, on_toggle)
except Exception as e:
    print(f"Initial Hotkey bind failed: {e}")

# If launched with --summon, show immediately
if "--summon" in sys.argv:
    nexus.summon()

sys.exit(app.exec())
