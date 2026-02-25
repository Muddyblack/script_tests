import sys
import os
import json
import time
import sqlite3
from typing import List, Dict

import pyautogui
import keyboard
import mouse
import keyring
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
    QInputDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QSpinBox,
    QFileDialog,
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QObject, QTimer
from PyQt6.QtGui import QIcon

# --- CONFIGURATION & DATABASE ---
DB_PATH = os.path.join(os.getenv("APPDATA", "."), "ghost_typist.db")
VAULT_SERVICE = "GhostTypist_Vault"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS macros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                hotkey TEXT,
                actions TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


# --- CUSTOM HOTKEY INPUT WIDGET ---
class HotkeyInput(QLineEdit):
    """A custom QLineEdit that captures actual keystrokes and formats them as hotkeys."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        # Ignore pure modifier presses (wait for a real key)
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return

        # Allow clearing the hotkey with Backspace or Delete
        if (
            key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete)
            and modifiers == Qt.KeyboardModifier.NoModifier
        ):
            self.clear()
            return

        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("windows")

        key_str = ""
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            key_str = chr(key).lower()
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            key_str = chr(key)
        elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F35:
            key_str = f"f{key - Qt.Key.Key_F1 + 1}"
        else:
            # Map standard special keys to strings understood by the `keyboard` module
            special_keys = {
                Qt.Key.Key_Space: "space",
                Qt.Key.Key_Return: "enter",
                Qt.Key.Key_Enter: "enter",
                Qt.Key.Key_Escape: "esc",
                Qt.Key.Key_Tab: "tab",
                Qt.Key.Key_Up: "up",
                Qt.Key.Key_Down: "down",
                Qt.Key.Key_Left: "left",
                Qt.Key.Key_Right: "right",
                Qt.Key.Key_Comma: ",",
                Qt.Key.Key_Period: ".",
                Qt.Key.Key_Slash: "/",
                Qt.Key.Key_Backslash: "\\",
                Qt.Key.Key_Minus: "-",
                Qt.Key.Key_Equal: "=",
                Qt.Key.Key_Semicolon: ";",
                Qt.Key.Key_Apostrophe: "'",
                Qt.Key.Key_BracketLeft: "[",
                Qt.Key.Key_BracketRight: "]",
                Qt.Key.Key_Insert: "insert",
                Qt.Key.Key_Home: "home",
                Qt.Key.Key_End: "end",
                Qt.Key.Key_PageUp: "page up",
                Qt.Key.Key_PageDown: "page down",
            }
            key_str = special_keys.get(key, "")

        if key_str:
            parts.append(key_str)
            hotkey_sequence = "+".join(parts)
            self.setText(hotkey_sequence)
            self.clearFocus()  # Drop focus after recording so they don't overwrite it


# --- MACRO RECORDER (BACKGROUND LISTENER) ---
class MacroRecorder(QObject):
    finished = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.is_recording = False
        self.actions = []
        self.last_time = 0

    def start_recording(self):
        self.actions = []
        self.is_recording = True
        self.last_time = time.time()

        # Targeted hooking so we don't blow away other global hotkeys (like the Kill Switch)
        keyboard.on_press(self.on_key_press)
        mouse.hook(self.on_mouse_event)

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False

        # Unhook specifically our listeners
        keyboard.unhook(self.on_key_press)
        mouse.unhook(self.on_mouse_event)

        # Emit the recorded actions back to the main UI
        self.finished.emit(self.actions)

    def _add_wait(self):
        now = time.time()
        wait_time = int((now - self.last_time) * 1000)
        # Only add a wait command if the delay was noticeable (> 50ms)
        if wait_time > 50:
            self.actions.append({"type": "wait", "value": wait_time})
        self.last_time = now

    def on_key_press(self, event):
        if not self.is_recording:
            return

        # Stop recording if F9 is pressed
        if event.name == "f9":
            self.stop_recording()
            return

        self._add_wait()
        self.actions.append({"type": "press", "value": event.name})

    def on_mouse_event(self, event):
        if not self.is_recording:
            return

        # Only record mouse clicks (button down events)
        if isinstance(event, mouse.ButtonEvent) and event.event_type == "down":
            self._add_wait()
            x, y = mouse.get_position()

            # Record the click position and which button was pressed
            self.actions.append(
                {
                    "type": "click",
                    "x": x,
                    "y": y,
                    "value": event.button if isinstance(event.button, str) else "left",
                }
            )


# --- MACRO RUNNER (BACKGROUND THREAD) ---
class MacroRunner(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, actions: List[Dict]):
        super().__init__()
        self.actions = actions
        self._is_running = True

    def stop(self):
        """Kill switch triggered flag"""
        self._is_running = False

    def run(self):
        try:
            for i, action in enumerate(self.actions):
                if not self._is_running:
                    self.progress.emit("⏹ Macro aborted by user (Kill Switch).")
                    break

                self.progress.emit(
                    f"Running step {i + 1}/{len(self.actions)}: {action['type']}"
                )

                # Small safety delay broken into chunks for instant kill-switch response
                for _ in range(5):
                    if not self._is_running:
                        break
                    time.sleep(0.01)

                if not self._is_running:
                    break

                if action["type"] == "wait":
                    # Break long waits into small 50ms chunks so Kill Switch is instant
                    wait_ms = action["value"]
                    while wait_ms > 0 and self._is_running:
                        sleep_time = min(50, wait_ms)
                        time.sleep(sleep_time / 1000.0)
                        wait_ms -= sleep_time

                elif action["type"] == "click":
                    button = action.get("value", "left")
                    pyautogui.click(x=action["x"], y=action["y"], button=button)

                elif action["type"] == "image_click":
                    image_path = action["value"]
                    if not os.path.exists(image_path):
                        self.error.emit(f"Image not found at path: {image_path}")
                        return

                    try:
                        # locateCenterOnScreen uses opencv under the hood if confidence is supplied.
                        try:
                            loc = pyautogui.locateCenterOnScreen(
                                image_path, confidence=0.8
                            )
                        except TypeError:
                            loc = pyautogui.locateCenterOnScreen(image_path)

                        if loc:
                            pyautogui.click(loc.x, loc.y)
                        else:
                            self.error.emit(
                                f"Could not find image on screen: {os.path.basename(image_path)}"
                            )
                            return
                    except Exception as img_e:
                        self.error.emit(f"Image detection error: {str(img_e)}")
                        return

                elif action["type"] == "type":
                    pyautogui.write(action["value"], interval=0.02)

                elif action["type"] == "press":
                    pyautogui.press(action["value"])

                elif action["type"] == "vault":
                    # Securely pull password from Windows Credential Manager
                    pwd = keyring.get_password(VAULT_SERVICE, action["value"])
                    if pwd:
                        pyautogui.write(pwd, interval=0.02)
                    else:
                        self.error.emit(f"Vault key '{action['value']}' not found.")
                        return

            if self._is_running:
                self.progress.emit("Macro complete!")

        except pyautogui.FailSafeException:
            self.error.emit(
                "Fail-Safe Triggered! (Mouse moved to screen corner). Macro aborted."
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


# --- GLOBAL HOTKEY LISTENER ---
class HotkeyListener(QObject):
    hotkey_triggered = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.active_hotkeys = []

    def update_hotkeys(self, macros):
        # Gracefully remove only our registered hotkeys
        for hk in self.active_hotkeys:
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self.active_hotkeys.clear()

        # Register new hotkeys
        for macro in macros:
            hk = macro.get("hotkey")
            if hk:
                try:
                    # Capture the macro name in the lambda
                    keyboard.add_hotkey(
                        hk, lambda name=macro["name"]: self.hotkey_triggered.emit(name)
                    )
                    self.active_hotkeys.append(hk)
                except ValueError:
                    print(f"Failed to register hotkey: {hk}")


# --- MAIN UI ---
class GhostTypist(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.setWindowTitle("Ghost-Typist Pro | Automation Suite")
        self.resize(1150, 750)

        if os.path.exists("icon.png"):
            self.setWindowIcon(QIcon("icon.png"))

        self.dark_mode = True
        self.current_macro_id = None
        self.macros = []

        self.setup_ui()
        self.load_settings()
        self.apply_modern_theme()
        self.load_macros()

        # Setup Recorder
        self.recorder = MacroRecorder()
        self.recorder.finished.connect(self.on_recording_finished)

        # Setup Hotkey Listener
        self.listener = HotkeyListener()
        self.listener.hotkey_triggered.connect(self.execute_macro_by_name)
        self.update_global_hotkeys()

        # Register Global Kill Switch
        try:
            keyboard.add_hotkey("f10", self.stop_running_macro)
        except Exception as e:
            print(f"Failed to bind Kill Switch: {e}")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- LEFT SIDEBAR (MACRO LIST) ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(290)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 25, 20, 25)
        sidebar_layout.setSpacing(15)

        sidebar_layout.addWidget(QLabel("<b>YOUR MACROS</b>"))
        self.macro_list = QListWidget()
        self.macro_list.itemClicked.connect(self.select_macro)
        sidebar_layout.addWidget(self.macro_list)

        btn_new_macro = QPushButton("+ New Macro")
        btn_new_macro.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new_macro.clicked.connect(self.create_macro)
        sidebar_layout.addWidget(btn_new_macro)

        btn_vault = QPushButton("🔒 Manage Vault")
        btn_vault.setObjectName("accent_btn")
        btn_vault.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_vault.clicked.connect(self.manage_vault)
        sidebar_layout.addWidget(btn_vault)

        sidebar_layout.addStretch()

        self.btn_theme = QPushButton("☀️ Light Mode")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.btn_theme)

        # --- MAIN CONTENT AREA ---
        content_wrapper = QWidget()
        content_wrapper.setObjectName("main_content")
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(35, 30, 35, 30)
        content_layout.setSpacing(20)

        # Macro Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)
        self.macro_name_input = QLineEdit()
        self.macro_name_input.setPlaceholderText("Macro Name (e.g., Weekly SAP Login)")
        self.macro_name_input.textChanged.connect(self.save_current_macro)

        # Replaced standard QLineEdit with Custom HotkeyInput
        self.hotkey_input = HotkeyInput()
        self.hotkey_input.setPlaceholderText("Click & press hotkey (e.g., ctrl+l)")
        self.hotkey_input.setFixedWidth(220)
        self.hotkey_input.textChanged.connect(self.save_current_macro)

        header_layout.addWidget(self.macro_name_input)
        header_layout.addWidget(self.hotkey_input)
        content_layout.addLayout(header_layout)

        # Action Builder & Recorder Area
        builder_card = QFrame()
        builder_card.setObjectName("builder_card")
        builder_layout = QHBoxLayout(builder_card)
        builder_layout.setContentsMargins(20, 20, 20, 20)
        builder_layout.setSpacing(12)

        self.action_type_combo = QComboBox()
        self.action_type_combo.addItems(
            ["wait", "click", "image_click", "type", "press", "vault"]
        )
        self.action_type_combo.currentTextChanged.connect(self.update_action_inputs)
        builder_layout.addWidget(self.action_type_combo)

        # Container for the text input and optional browse button
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(5)

        self.input_value = QLineEdit()
        self.input_value.setPlaceholderText("Value (ms for wait, text for type)")
        input_layout.addWidget(self.input_value)

        self.btn_browse = QPushButton("📁")
        self.btn_browse.setFixedWidth(40)
        self.btn_browse.setVisible(False)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self.browse_image)
        input_layout.addWidget(self.btn_browse)

        builder_layout.addWidget(input_container, stretch=1)

        self.input_x = QSpinBox()
        self.input_x.setRange(0, 9999)
        self.input_x.setPrefix("X: ")
        self.input_x.setVisible(False)
        builder_layout.addWidget(self.input_x)

        self.input_y = QSpinBox()
        self.input_y.setRange(0, 9999)
        self.input_y.setPrefix("Y: ")
        self.input_y.setVisible(False)
        builder_layout.addWidget(self.input_y)

        btn_add_action = QPushButton("Add Step")
        btn_add_action.setObjectName("action_btn")
        btn_add_action.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_action.clicked.connect(self.add_action)
        builder_layout.addWidget(btn_add_action)

        # New Record Button
        self.btn_record = QPushButton("🔴 Record (F9)")
        self.btn_record.setObjectName("danger_btn")
        self.btn_record.setToolTip(
            "Click to auto-save, minimize, and start recording. Press F9 to stop."
        )
        self.btn_record.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_record.clicked.connect(self.start_recording_ui)
        builder_layout.addWidget(self.btn_record)

        content_layout.addWidget(builder_card)

        # Actions Table
        self.actions_table = QTableWidget(0, 4)
        self.actions_table.setHorizontalHeaderLabels(
            ["Type", "Details / Image / Key", "X", "Y"]
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
        content_layout.addWidget(self.actions_table)

        # Footer Actions
        footer_layout = QHBoxLayout()
        btn_run = QPushButton("▶ Run Macro Now")
        btn_run.setObjectName("success_btn")
        btn_run.setToolTip(
            "Will hide the app, execute, and pop back up. Kill switch: F10"
        )
        btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_run.clicked.connect(self.run_current_macro_ui)
        footer_layout.addWidget(btn_run)

        btn_del_action = QPushButton("Delete Selected Step")
        btn_del_action.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del_action.clicked.connect(self.delete_selected_action)
        footer_layout.addWidget(btn_del_action)

        footer_layout.addStretch()

        lbl_hint = QLabel("💡 Kill Switch: Press F10 or move mouse to screen corner")
        lbl_hint.setStyleSheet("color: #64748b;")
        footer_layout.addWidget(lbl_hint)
        footer_layout.addSpacing(15)

        btn_del_macro = QPushButton("🗑 Delete Macro")
        btn_del_macro.setObjectName("danger_btn")
        btn_del_macro.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del_macro.clicked.connect(self.delete_macro)
        footer_layout.addWidget(btn_del_macro)

        content_layout.addLayout(footer_layout)

        # Status Bar
        status_card = QFrame()
        status_card.setObjectName("status_card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(0, 5, 0, 0)

        self.status_label = QLabel("System Ready")
        self.status_label.setStyleSheet(
            "color: #64748b; font-size: 13px; font-weight: 500;"
        )
        status_layout.addWidget(self.status_label)
        content_layout.addWidget(status_card)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(content_wrapper)

        # Disable main area until macro selected
        self.set_editor_enabled(False)

    def apply_modern_theme(self):
        if self.dark_mode:
            self.btn_theme.setText("☀️ Light Mode")
            self.setStyleSheet("""
                QMainWindow { background-color: #0f111a; }
                QWidget { background-color: #0f111a; color: #e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; }
                
                QFrame#sidebar { background-color: #161925; border-right: 1px solid #2a2e45; }
                QLabel { color: #8b9bb4; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; }
                
                QLineEdit, QComboBox, QSpinBox { 
                    background-color: #1a1d2b; border: 1.5px solid #2a2e45; 
                    padding: 10px 14px; border-radius: 8px; color: #ffffff;
                }
                QLineEdit:focus, QComboBox:focus { border: 1.5px solid #6366f1; background-color: #161925; }
                QComboBox::drop-down { border: none; }
                
                QPushButton { 
                    background-color: #1e2336; border: 1px solid #2a2e45; 
                    padding: 10px 18px; border-radius: 8px; font-weight: bold; color: #e2e8f0;
                }
                QPushButton:hover { background-color: #2a2e45; border: 1px solid #3b4261; }
                
                QPushButton#success_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #059669); 
                    color: white; border: none; 
                }
                QPushButton#success_btn:hover { background: #059669; }
                
                QPushButton#danger_btn { 
                    background-color: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); 
                }
                QPushButton#danger_btn:hover { background-color: #ef4444; color: white; }

                QPushButton#accent_btn { 
                    background-color: transparent; border: 1.5px solid #8b5cf6; color: #a78bfa; 
                }
                QPushButton#accent_btn:hover { background-color: #8b5cf6; color: #ffffff; }

                QListWidget, QTableWidget { 
                    background-color: #161925; border: 1.5px solid #2a2e45; border-radius: 8px; outline: none; 
                }
                QListWidget::item { padding: 12px; border-radius: 6px; margin-bottom: 2px; }
                QListWidget::item:hover { background-color: #1e2336; }
                QListWidget::item:selected { background-color: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid #6366f1; }
                
                QHeaderView::section { background-color: #161925; color: #8b9bb4; border: none; padding: 10px; font-weight: bold; border-bottom: 1px solid #2a2e45; }
                QTableWidget::item { padding: 8px; border-bottom: 1px solid #1e2336; }
                
                QFrame#builder_card { background-color: #161925; border: 1px solid #2a2e45; border-radius: 12px; }
                QScrollBar:vertical { border: none; background: transparent; width: 6px; }
                QScrollBar::handle:vertical { background: #3b4261; border-radius: 3px; min-height: 40px; }
            """)
        else:
            self.btn_theme.setText("🌙 Dark Mode")
            self.setStyleSheet("""
                QMainWindow { background-color: #f8fafc; }
                QWidget { background-color: #f8fafc; color: #0f172a; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; }
                
                QFrame#sidebar { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
                QLabel { color: #64748b; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; }
                
                QLineEdit, QComboBox, QSpinBox { 
                    background-color: #ffffff; border: 1.5px solid #cbd5e1; 
                    padding: 10px 14px; border-radius: 8px; color: #0f172a;
                }
                QLineEdit:focus, QComboBox:focus { border: 1.5px solid #3b82f6; background-color: #f8fafc; }
                QComboBox::drop-down { border: none; }
                
                QPushButton { 
                    background-color: #f1f5f9; border: 1px solid #cbd5e1; 
                    padding: 10px 18px; border-radius: 8px; font-weight: bold; color: #334155;
                }
                QPushButton:hover { background-color: #e2e8f0; border: 1px solid #94a3b8; }
                
                QPushButton#success_btn { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #059669); 
                    color: white; border: none; 
                }
                QPushButton#success_btn:hover { background: #059669; }
                
                QPushButton#danger_btn { 
                    background-color: #fef2f2; color: #ef4444; border: 1px solid #fecaca; 
                }
                QPushButton#danger_btn:hover { background-color: #ef4444; color: white; }

                QPushButton#accent_btn { 
                    background-color: transparent; border: 1.5px solid #8b5cf6; color: #8b5cf6; 
                }
                QPushButton#accent_btn:hover { background-color: #8b5cf6; color: #ffffff; }

                QListWidget, QTableWidget { 
                    background-color: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 8px; outline: none; 
                }
                QListWidget::item { padding: 12px; border-radius: 6px; margin-bottom: 2px; }
                QListWidget::item:hover { background-color: #f8fafc; }
                QListWidget::item:selected { background-color: #eff6ff; color: #2563eb; border: 1px solid #3b82f6; }

                QHeaderView::section { background-color: #f8fafc; color: #64748b; border: none; padding: 10px; font-weight: bold; border-bottom: 1px solid #e2e8f0; }
                QTableWidget::item { padding: 8px; border-bottom: 1px solid #f1f5f9; }
                
                QFrame#builder_card { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; }
                QScrollBar:vertical { border: none; background: transparent; width: 6px; }
                QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 3px; min-height: 40px; }
            """)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_modern_theme()
        self.save_settings()

    def load_settings(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key='theme'")
            res = cursor.fetchone()
            if res:
                self.dark_mode = res[0] == "dark"

    def save_settings(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("theme", "dark" if self.dark_mode else "light"),
            )
            conn.commit()

    # --- UI LOGIC ---
    def set_editor_enabled(self, enabled):
        self.macro_name_input.setEnabled(enabled)
        self.hotkey_input.setEnabled(enabled)
        self.action_type_combo.setEnabled(enabled)
        self.input_value.setEnabled(enabled)
        self.input_x.setEnabled(enabled)
        self.input_y.setEnabled(enabled)
        self.actions_table.setEnabled(enabled)
        self.btn_record.setEnabled(enabled)

    def update_action_inputs(self, action_type):
        self.btn_browse.setVisible(action_type == "image_click")

        if action_type == "click":
            self.input_value.setVisible(False)
            self.input_x.setVisible(True)
            self.input_y.setVisible(True)
        else:
            self.input_value.setVisible(True)
            self.input_x.setVisible(False)
            self.input_y.setVisible(False)

            if action_type == "wait":
                self.input_value.setPlaceholderText("Milliseconds (e.g., 1000)")
            elif action_type == "press":
                self.input_value.setPlaceholderText("Key (e.g., enter, tab, esc)")
            elif action_type == "vault":
                self.input_value.setPlaceholderText("Vault Key Name (e.g., sap_prod)")
            elif action_type == "image_click":
                self.input_value.setPlaceholderText("Path to image.png...")
            else:
                self.input_value.setPlaceholderText("Text to type...")

    def browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image for Recognition",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )
        if file_path:
            self.input_value.setText(file_path)

    def manage_vault(self):
        key, ok1 = QInputDialog.getText(
            self, "Vault", "Enter new/existing Credential Key name:"
        )
        if ok1 and key:
            pwd, ok2 = QInputDialog.getText(
                self,
                "Vault",
                f"Enter password for '{key}':",
                QLineEdit.EchoMode.Password,
            )
            if ok2 and pwd:
                keyring.set_password(VAULT_SERVICE, key, pwd)
                QMessageBox.information(
                    self,
                    "Vault",
                    f"Credential '{key}' saved securely in Windows Credential Manager.",
                )

    # --- RECORDER INTEGRATION ---
    def start_recording_ui(self):
        if not self.current_macro_id:
            QMessageBox.warning(self, "No Macro", "Select or create a macro first.")
            return

        # SAVE FIRST!
        self.save_current_macro()

        # Minimize window to get out of the way
        self.showMinimized()

        self.status_label.setText("🔴 RECORDING... PRESS F9 TO STOP")
        self.status_label.setStyleSheet(
            "color: #ef4444; font-weight: bold; font-size: 14px;"
        )

        # Give the OS a moment to minimize the window before hooking
        QTimer.singleShot(300, self.recorder.start_recording)

    def on_recording_finished(self, new_actions):
        # Bring window back up
        self.showNormal()
        self.activateWindow()

        self.status_label.setText("✅ Recording complete and appended to macro!")
        self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")

        # Read existing actions and append the newly recorded ones
        current_actions = self.get_actions_from_table()
        current_actions.extend(new_actions)

        # Render and save
        self.render_actions_table(current_actions)
        self.save_current_macro()

        # Re-register global hotkeys (since the recorder unhooked everything)
        self.update_global_hotkeys()

    # --- DATABASE LOGIC ---
    def load_macros(self):
        self.macro_list.clear()
        self.macros.clear()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            for row in cursor.execute("SELECT id, name, hotkey, actions FROM macros"):
                macro = {
                    "id": row[0],
                    "name": row[1],
                    "hotkey": row[2] or "",
                    "actions": json.loads(row[3]) if row[3] else [],
                }
                self.macros.append(macro)
                item = QListWidgetItem(macro["name"] or "Unnamed Macro")
                item.setData(Qt.ItemDataRole.UserRole, macro["id"])
                self.macro_list.addItem(item)

    def create_macro(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO macros (name, hotkey, actions) VALUES (?, ?, ?)",
                ("New Macro", "", "[]"),
            )
            conn.commit()
        self.load_macros()
        self.macro_list.setCurrentRow(self.macro_list.count() - 1)
        self.select_macro(self.macro_list.currentItem())

    def select_macro(self, item):
        self.current_macro_id = item.data(Qt.ItemDataRole.UserRole)
        macro = next((m for m in self.macros if m["id"] == self.current_macro_id), None)

        if macro:
            self.set_editor_enabled(True)
            self.macro_name_input.setText(macro["name"])
            self.hotkey_input.setText(macro["hotkey"])
            self.render_actions_table(macro["actions"])

    def get_actions_from_table(self):
        actions = []
        for i in range(self.actions_table.rowCount()):
            a_type = self.actions_table.item(i, 0).text()
            a_val = self.actions_table.item(i, 1).text()
            a_x = self.actions_table.item(i, 2).text()
            a_y = self.actions_table.item(i, 3).text()

            action = {"type": a_type}
            if a_type == "click":
                action["x"] = int(a_x) if a_x else 0
                action["y"] = int(a_y) if a_y else 0
                # Map old/manual values or fallback to left click
                action["value"] = (
                    a_val if a_val in ["left", "right", "middle"] else "left"
                )
            elif a_type == "wait":
                action["value"] = int(a_val) if a_val.isdigit() else 0
            else:
                action["value"] = a_val
            actions.append(action)
        return actions

    def save_current_macro(self):
        if not self.current_macro_id:
            return

        name = self.macro_name_input.text()
        hotkey = self.hotkey_input.text()
        actions = self.get_actions_from_table()

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE macros SET name=?, hotkey=?, actions=? WHERE id=?",
                (name, hotkey, json.dumps(actions), self.current_macro_id),
            )
            conn.commit()

        # Update local list item text
        for i in range(self.macro_list.count()):
            item = self.macro_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == self.current_macro_id:
                item.setText(name if name else "Unnamed Macro")
                break

        # Sync the local array memory for hotkey hook
        for m in self.macros:
            if m["id"] == self.current_macro_id:
                m["name"] = name
                m["hotkey"] = hotkey
                m["actions"] = actions
                break

        self.update_global_hotkeys()

    def delete_macro(self):
        if not self.current_macro_id:
            return
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM macros WHERE id=?", (self.current_macro_id,))
            conn.commit()
        self.set_editor_enabled(False)
        self.macro_name_input.clear()
        self.hotkey_input.clear()
        self.actions_table.setRowCount(0)
        self.current_macro_id = None
        self.load_macros()
        self.update_global_hotkeys()

    # --- ACTIONS TABLE LOGIC ---
    def render_actions_table(self, actions):
        self.actions_table.setRowCount(0)
        for action in actions:
            self.add_action_to_table(action)

    def add_action_to_table(self, action):
        row = self.actions_table.rowCount()
        self.actions_table.insertRow(row)

        self.actions_table.setItem(row, 0, QTableWidgetItem(action["type"]))

        if action["type"] == "click":
            # Display the button used
            self.actions_table.setItem(
                row, 1, QTableWidgetItem(str(action.get("value", "left")))
            )
            self.actions_table.setItem(
                row, 2, QTableWidgetItem(str(action.get("x", 0)))
            )
            self.actions_table.setItem(
                row, 3, QTableWidgetItem(str(action.get("y", 0)))
            )
        else:
            self.actions_table.setItem(
                row, 1, QTableWidgetItem(str(action.get("value", "")))
            )
            self.actions_table.setItem(row, 2, QTableWidgetItem(""))
            self.actions_table.setItem(row, 3, QTableWidgetItem(""))

    def add_action(self):
        a_type = self.action_type_combo.currentText()
        action = {"type": a_type}

        if a_type == "click":
            action["x"] = self.input_x.value()
            action["y"] = self.input_y.value()
            action["value"] = "left"  # Default to left for manual adds
        elif a_type == "wait":
            val = self.input_value.text()
            action["value"] = int(val) if val.isdigit() else 1000
        else:
            action["value"] = self.input_value.text()

        self.add_action_to_table(action)
        self.save_current_macro()

    def delete_selected_action(self):
        for row in reversed(range(self.actions_table.rowCount())):
            if self.actions_table.item(row, 0).isSelected():
                self.actions_table.removeRow(row)
        self.save_current_macro()

    # --- EXECUTION LOGIC ---
    def update_global_hotkeys(self):
        self.listener.update_hotkeys(self.macros)

    def stop_running_macro(self):
        """Global hook kill switch"""
        if hasattr(self, "runner") and self.runner.isRunning():
            self.runner.stop()

    def execute_macro_by_name(self, name):
        macro = next((m for m in self.macros if m["name"] == name), None)
        if macro:
            self.start_macro_runner(macro["actions"])

    def run_current_macro_ui(self):
        """Called when clicking the run button in the GUI."""
        macro = next((m for m in self.macros if m["id"] == self.current_macro_id), None)
        if not macro:
            return

        # SAVE FIRST!
        self.save_current_macro()

        # Hide the UI so the macro clicks the underlying apps, not Ghost-Typist!
        self.showMinimized()

        # Wait 400ms for the OS to finish minimizing the window, then run it
        QTimer.singleShot(400, lambda: self.start_macro_runner(macro["actions"]))

    def start_macro_runner(self, actions):
        if not actions:
            self.status_label.setText("Error: Macro has no actions.")
            self.showNormal()
            return

        # Update UI for Kill Switch
        self.status_label.setText("▶ RUNNING... PRESS F10 TO EMERGENCY STOP")
        self.status_label.setStyleSheet(
            "color: #eab308; font-weight: bold; font-size: 14px;"
        )

        self.runner = MacroRunner(actions)
        self.runner.progress.connect(self.status_label.setText)
        self.runner.error.connect(self.on_runner_error)
        self.runner.finished.connect(self.on_runner_finished)
        self.runner.start()

    def on_runner_error(self, err_msg):
        self.showNormal()
        self.activateWindow()
        QMessageBox.critical(self, "Execution Error", err_msg)

    def on_runner_finished(self):
        # Restore the window when the macro successfully finishes playing
        self.showNormal()
        self.activateWindow()
        self.status_label.setText("✅ Macro Execution Complete / Stopped")
        self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GhostTypist()
    window.show()
    sys.exit(app.exec())
