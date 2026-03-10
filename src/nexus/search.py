"""Nexus Search main UI widget."""

import ctypes
import os
import sys
import threading

try:
    from pynput import keyboard as _pynput_kb  # type: ignore
except ImportError:
    _pynput_kb = None
from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QCursor, QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import QApplication, QFileIconProvider, QWidget

from src.common.config import DB_PATH, SETTINGS_FILE, X_EXPLORER_DB
from src.common.search_engine import SearchEngine
from src.common.theme import ThemeManager, apply_win32_titlebar
from src.img_to_text import start_snip_to_text
from src.img_to_text.gui import start_file_to_text
from src.nexus.theme_picker_popup import ThemePickerPopup

from ._data_mixin import _DataMixin
from ._launch_mixin import _LaunchMixin
from ._results_mixin import _ResultsMixin
from ._search_mixin import _SearchMixin
from ._ui_mixin import _UIMixin
from .system_commands import (
    add_task_to_chronos as _add_task_chronos,
)
from .system_commands import (
    execute_system_toggle as _exec_toggle,
)
from .system_commands import (
    kill_process as _kill_proc,
)
from .system_commands import (
    launch_chronos as _launch_chronos,
)
from .system_commands import (
    launch_ghost_typist as _launch_ghost_typist,
)
from .system_commands import (
    launch_text_summarizer as _launch_text_summarizer,
)
from .system_commands import (
    launch_xexplorer as _launch_xexplorer,
)
from .system_commands import (
    log_to_chronos as _log_to_chronos,
)
from .system_commands import (
    update_process_cache as _update_procs,
)
from .themes import get_nexus_theme
from .utils import is_opacity_supported


class NexusSearch(
    _LaunchMixin, _ResultsMixin, _SearchMixin, _UIMixin, _DataMixin, QWidget
):
    """Nexus Search launcher — thin core, logic delegated to mixins."""

    # Signal emitted from pynput thread, handled on the Qt main thread.
    _global_key_signal = pyqtSignal(str, bool)  # (key_name, has_modifier)
    file_search_finished = pyqtSignal(list, int)  # (candidates, generation)

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
            "frequent": True,
            "apps": True,
            "bookmarks": True,
            "files": False,
            "processes": False,
            "toggles": True,
            "ssh": True,
            "files_only": False,
            "folders_only": False,
            "target_folders": [],
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
        self.search_engine.warm_cache()  # warm DB connections in background for fast first :f search
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
        self.search_timer.timeout.connect(self.perform_search_files)

        self.last_search_time = 0
        self.last_launch_time = 0.0
        # Clock timer — live updates
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()
        self.current_candidates = []

        # Global input redirect via pynput (no sudo required on any platform)
        self._held_modifiers: set[str] = set()  # currently-held modifier names
        self._global_listener = None
        self._global_key_signal.connect(self._handle_global_key)
        self.file_search_finished.connect(self._handle_file_results)
        self._start_global_listener()

    # ------------------------------------------------------------------
    # Global key redirect
    # ------------------------------------------------------------------
    def _start_global_listener(self) -> None:
        """Attach a pynput global keyboard listener for input redirect."""
        if _pynput_kb is None:
            return
        self._global_listener = _pynput_kb.Listener(
            on_press=self._on_global_key_press,
            on_release=self._on_global_key_release,
            daemon=True,
        )
        self._global_listener.start()

    @staticmethod
    def _resolve_pynput_key_name(key) -> str:
        """Convert a pynput key object to a normalised lowercase name string."""
        if _pynput_kb is None:
            return ""
        if isinstance(key, _pynput_kb.Key):
            # e.g. Key.page_up → "page up", Key.esc → "esc"
            return key.name.replace("_", " ")
        if hasattr(key, "char") and key.char:
            return key.char.lower()
        return ""

    def _on_global_key_release(self, key) -> None:
        """Track which modifier keys are currently held (pynput thread)."""
        try:
            if _pynput_kb is None or not isinstance(key, _pynput_kb.Key):
                return
            base = key.name.split("_")[0]
            self._held_modifiers.discard(base)
        except Exception:
            pass

    def _on_global_key_press(self, key) -> None:
        """Capture key on pynput thread and emit signal to Qt main thread."""
        try:
            # Update modifier tracking (pure Python set, safe on any thread)
            if _pynput_kb is not None and isinstance(key, _pynput_kb.Key):
                base = key.name.split("_")[0]
                if base in ("ctrl", "alt", "cmd", "shift"):
                    self._held_modifiers.add(base)

            key_name = self._resolve_pynput_key_name(key)
            if not key_name:
                return

            has_modifier = bool(self._held_modifiers & {"ctrl", "alt", "cmd"})
            # Thread-safe: pyqtSignal.emit() → slot runs on the main thread
            self._global_key_signal.emit(key_name, has_modifier)
        except Exception:
            pass

    def _handle_global_key(self, key_name: str, has_modifier: bool) -> None:
        """Process redirected keypress — runs on the Qt main thread (slot)."""
        if not self.isVisible():
            return

        # If any window of this application is active, let Qt handle the keys natively
        if QApplication.activeWindow():
            return

        navigation_keys = {
            "up": -1,
            "down": 1,
            "page up": -10,
            "page down": 10,
        }

        # Alt + 1-9 shortcuts
        if (
            "alt" in self._held_modifiers
            and key_name.isdigit()
            and "1" <= key_name <= "9"
        ):
            self.launch_by_index(int(key_name) - 1)
            return

        if key_name in navigation_keys:
            self.navigate_results(navigation_keys[key_name])
        elif key_name == "enter":
            self.launch_selected()
        elif key_name == "esc":
            self.hide()
        elif len(key_name) == 1 and not has_modifier:
            self.search_input.setText(self.search_input.text() + key_name)
            self.summon_and_focus()

    def launch_by_index(self, idx):
        """Select and launch an item by its visual index (0-indexed)."""
        if self.view_mode == "tree":
            # For tree view, we traverse visible items to find the Nth one
            count = 0
            target_item = None

            def find_visible(parent=None):
                nonlocal count, target_item
                item_count = (
                    self.results_tree.topLevelItemCount()
                    if parent is None
                    else parent.childCount()
                )
                for i in range(item_count):
                    child = (
                        self.results_tree.topLevelItem(i)
                        if parent is None
                        else parent.child(i)
                    )
                    if not child.isHidden() and count == idx:
                        target_item = child
                        return True
                    if not child.isHidden():
                        count += 1
                        if child.isExpanded() and find_visible(child):
                            return True
                return False

            find_visible()
            if target_item:
                self.results_tree.setCurrentItem(target_item)
                self.launch_selected()
        else:
            if 0 <= idx < self.results_list.count():
                self.results_list.setCurrentRow(idx)
                self.launch_selected()

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
    # Event overrides
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        key = event.key()
        if (
            event.modifiers() & Qt.KeyboardModifier.AltModifier
            and Qt.Key.Key_1 <= key <= Qt.Key.Key_9
        ):
            self.launch_by_index(key - Qt.Key.Key_1)
            event.accept()
            return

        if key == Qt.Key.Key_Escape:
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
        super().hide()

    def summon(self):
        self.center_on_screen()
        self.search_input.clear()
        self.perform_search()

        if is_opacity_supported():
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

        if is_opacity_supported():
            self.anim = QPropertyAnimation(self, b"windowOpacity")
            self.anim.setDuration(250)
            self.anim.setStartValue(0)
            self.anim.setEndValue(1)
            self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim.start()

        self.rainbow_frame.trigger_animation()

    # ------------------------------------------------------------------
    # App / tool launchers (thin wrappers)
    # ------------------------------------------------------------------
    def start_img_to_text(self) -> None:
        """Snip a region on screen and OCR it into clipboard."""
        start_snip_to_text(nexus=self)

    def start_img_to_text_gui(self) -> None:
        """Open the full Image OCR dialog (file / drag-drop / paste)."""
        if not hasattr(self, "_ocr_dlg") or self._ocr_dlg is None:
            self._ocr_dlg = start_file_to_text(nexus=self)
            self._ocr_dlg.destroyed.connect(lambda: setattr(self, "_ocr_dlg", None))
        else:
            self._ocr_dlg.show()
            self._ocr_dlg.raise_()
            self._ocr_dlg.activateWindow()

    def start_chronos(self) -> None:
        _launch_chronos(self)

    def start_ghost_typist(self) -> None:
        _launch_ghost_typist(self)

    def start_xexplorer(self) -> None:
        _launch_xexplorer(self)

    def start_text_summarizer(self) -> None:
        _launch_text_summarizer(self)

    def toggle_ghost_watcher(self, enabled: bool) -> None:
        """Enable or disable the background Ghost Typist keyboard listener."""
        if not hasattr(self, "ghost_watcher"):
            return

        from src.ghost_typist.db import set_setting

        set_setting("watcher_enabled", "1" if enabled else "0")

        if enabled:
            self.ghost_watcher.start()
            self.status_lbl.setText("⌨️ Ghost Typist Listener Started")
        else:
            self.ghost_watcher.stop()
            self.status_lbl.setText("⌨️ Ghost Typist Listener Stopped")

        self.status_lbl.setStyleSheet("color: #a855f7; font-weight: bold;")

    def toggle_clipboard_watcher(self, enabled: bool) -> None:
        """Enable or disable the background Clipboard Manager watcher."""
        if not hasattr(self, "clipboard_watcher"):
            return

        from src.clipboard_manager.watcher import set_watcher_enabled

        set_watcher_enabled(enabled)

        if enabled:
            self.clipboard_watcher.start()
            self.status_lbl.setText("📋 Clipboard Monitor Started")
        else:
            self.clipboard_watcher.stop()
            self.status_lbl.setText("📋 Clipboard Monitor Stopped")

        self.status_lbl.setStyleSheet("color: #f472b6; font-weight: bold;")

    # ------------------------------------------------------------------
    # System command delegates
    # ------------------------------------------------------------------
    def execute_system_toggle(self, cmd):
        _exec_toggle(self, cmd)

    def kill_process(self, pid, name):
        _kill_proc(self, pid, name)

    def update_process_cache(self, force=False):
        _update_procs(self, force)

    def _log_to_chronos(self, text):
        _log_to_chronos(self, text)

    def _add_task_to_chronos(self, text):
        _add_task_chronos(self, text)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def apply_theme(self):
        mgr = ThemeManager()
        self.setStyleSheet(get_nexus_theme(mgr))
        if hasattr(self, "_theme_btn"):
            self._theme_btn.setText(
                f"— {mgr.theme_data.get('name', mgr.current_theme_name)}"
            )

        apply_win32_titlebar(int(self.winId()), mgr["bg_base"], mgr.is_dark)

        if hasattr(self, "current_candidates") and self.current_candidates:
            self.results_list.clear()
            self.populate_list_results(self.current_candidates)

    def _open_theme_picker(self):
        """Open the VS Code-style floating theme picker (from button)."""
        if hasattr(self, "_theme_picker") and self._theme_picker:
            self._theme_picker.close()

        self._theme_picker = ThemePickerPopup(self)
        btn_pos = self._theme_btn.mapToGlobal(self._theme_btn.rect().bottomLeft())
        self._theme_picker.move(btn_pos.x(), btn_pos.y() + 4)
        self._theme_picker.show()
        self._theme_picker.raise_()
        self._theme_picker.activateWindow()

    def open_theme_picker_global(self):
        """Open the theme picker from a global hotkey — centered on screen."""
        if (
            hasattr(self, "_theme_picker")
            and self._theme_picker
            and self._theme_picker.isVisible()
        ):
            self._theme_picker.close()
            return

        self._theme_picker = ThemePickerPopup(None)
        self._theme_picker.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        screen = (
            QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        )
        sg = screen.availableGeometry()
        pw = self._theme_picker.sizeHint().width() or 280
        ph = self._theme_picker.sizeHint().height() or 330
        self._theme_picker.move(
            sg.x() + (sg.width() - pw) // 2,
            sg.y() + (sg.height() - ph) // 3,
        )
        self._theme_picker.show()
        self._theme_picker.raise_()
        self._theme_picker.activateWindow()

        # Aggressive focus for Windows
        QTimer.singleShot(50, self._theme_picker.activateWindow)
        QTimer.singleShot(100, lambda: self._theme_picker._list.setFocus())

    def _open_settings_folder(self):
        """Open the folder where Nexus settings are stored."""
        settings_dir = os.path.dirname(SETTINGS_FILE)
        if os.path.exists(settings_dir):
            QDesktopServices.openUrl(QUrl.fromLocalFile(settings_dir))
        else:
            self.status_lbl.setText("Settings directory not found")
