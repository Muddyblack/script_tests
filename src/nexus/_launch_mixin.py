"""Launch mixin — launch_selected, context menus."""

import os
import subprocess
import sys
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu

from src.common.config import PROJECT_ROOT
from src.common.theme import ThemeManager
from src.file_ops.file_ops import FileToolsWindow, is_archive

from .system_commands import (
    add_task_to_chronos as _add_task_chronos,
)
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
    launch_chronos as _launch_chronos,
)
from .system_commands import (
    launch_clipboard_manager as _launch_clipboard,
)
from .system_commands import (
    launch_color_picker as _launch_color_picker,
)
from .system_commands import (
    launch_file_ops as _launch_file_ops,
)
from .system_commands import (
    launch_ghost_typist as _launch_ghost_typist,
)
from .system_commands import (
    launch_hash_tool as _launch_hash_tool,
)
from .system_commands import (
    launch_port_inspector as _launch_port_inspector,
)
from .system_commands import (
    launch_regex_helper as _launch_regex,
)
from .system_commands import (
    launch_sqlite_viewer as _launch_sqlite_viewer,
)
from .system_commands import (
    launch_xexplorer as _launch_xexplorer,
)
from .system_commands import (
    log_to_chronos as _log_to_chronos,
)


class _LaunchMixin:
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
            f"QMenu::item:selected {{ background-color: {_acc}; "
            f"color: {_c.get('text_on_accent', 'white')}; }}"
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

            # Frequent removal
            frequent_action = None
            if len(data_list) == 1:
                d = data_list[0]
                ukey = None
                dtype = d.get("type")
                if dtype == "app":
                    ukey = f"app_{d.get('path')}"
                elif dtype == "cmd":
                    ukey = f"cmd_{d.get('cmd')}"
                elif dtype == "file":
                    ukey = f"file_{d.get('path')}"
                elif dtype == "script":
                    ukey = f"script_{d.get('path')}"

                if ukey and hasattr(self, "usage_stats") and ukey in self.usage_stats:
                    menu.addSeparator()
                    frequent_action = menu.addAction("❌ Remove from Frequent")
                    frequent_action.setData(ukey)

            action = menu.exec(parent_widget.mapToGlobal(pos))
            if not action:
                return

            if action != search_here and action != frequent_action:
                self.hide()

            if action == copy_path:
                norm_paths = [os.path.normpath(p) for p in paths]
                from src.nexus.utils import copy_to_clipboard

                copy_to_clipboard("\n".join(norm_paths))
                self.status_lbl.setText(f"Copied {len(norm_paths)} path(s)")
            elif action == copy_name:
                names = [os.path.basename(p) for p in paths]
                from src.nexus.utils import copy_to_clipboard

                copy_to_clipboard("\n".join(names))
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
                self.file_ops_win = FileToolsWindow()
                self.file_ops_win.fo_sources = list(paths)
                self.file_ops_win._fo_refresh()
                self.file_ops_win._switch_tab("fileops")
                self.file_ops_win.show()
            elif (
                archive_action
                and action == archive_action
                or extract_action
                and action == extract_action
            ):
                self.archiver_win = FileToolsWindow()
                self.archiver_win.arc_sources = list(paths)
                self.archiver_win._arc_refresh()
                self.archiver_win._switch_tab("archiver")
                self.archiver_win.show()
            elif frequent_action and action == frequent_action:
                ukey = action.data()
                self.remove_usage(ukey)
                self.status_lbl.setText("Removed from Frequent list")
                self.perform_search()

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------
    def launch_selected(self):
        import time

        # Debounce: prevent "doubled" launches from fast clicks
        now = time.time()
        if hasattr(self, "last_launch_time") and (now - self.last_launch_time) < 0.5:
            return
        self.last_launch_time = now

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
            elif data["type"] == "app":
                self.record_usage(f"app_{data['path']}")
                f_path = data["path"]
                if not os.path.exists(f_path):
                    raise FileNotFoundError(f"App not found: {f_path}")
                from .utils import open_path
                open_path(f_path)
            elif data["type"] == "cmd":
                self.record_usage(f"cmd_{data['cmd']}")
                cmd = data["cmd"]
                _CMD_MAP = {
                    "xexplorer": _launch_xexplorer,
                    "regex_helper": _launch_regex,
                    "file_ops": _launch_file_ops,
                    "archiver": _launch_archiver,
                    "color_picker": _launch_color_picker,
                    "chronos_hub": _launch_chronos,
                    "clipboard_manager": _launch_clipboard,
                    "port_inspector": _launch_port_inspector,
                    "hash_tool": _launch_hash_tool,
                    "ghost_typist": _launch_ghost_typist,
                    "sqlite_viewer": _launch_sqlite_viewer,
                }
                if cmd in _CMD_MAP:
                    _CMD_MAP[cmd](self)
                elif cmd == "img_to_text":
                    self.start_img_to_text()
                elif cmd == "img_to_text_gui":
                    self.start_img_to_text_gui()
                elif (
                    cmd.startswith("toggle_")
                    or cmd.startswith("cmd_")
                    or cmd.startswith("ms-settings:")
                    or cmd in ["flush_dns", "restart_explorer", "toggle_desktop"]
                ):
                    _exec_toggle(self, cmd)
            elif data["type"] == "script":
                self.record_usage(f"script_{data['path']}")
                f_path = data["path"]
                if not os.path.exists(f_path):
                    raise FileNotFoundError(f"Script not found: {f_path}")
                if "src" in f_path:
                    rel = os.path.relpath(f_path, PROJECT_ROOT)
                    mod_path = rel.replace(os.sep, ".").rsplit(".", 1)[0]
                    subprocess.Popen([sys.executable, "-m", mod_path])
                else:
                    subprocess.Popen([sys.executable, f_path])
            elif data["type"] == "file":
                f_path = data["path"]
                self.record_usage(f"file_{f_path}")
                # For UNC/network paths, we try to open even if existence check fails
                # (might be unmounted, requires auth, etc.)
                is_unc = f_path.startswith("\\\\") or f_path.startswith("//")
                if not os.path.exists(f_path) and not is_unc:
                    raise FileNotFoundError(f"File not found: {f_path}")

                from .utils import open_path
                open_path(f_path)
            elif data["type"] == "process":
                _kill_proc(self, data["pid"], data["name"])
            elif data["type"] == "process_kill_all":
                _kill_all_procs(self, data["name"])
            elif data["type"] == "ssh":
                self.status_lbl.setText(f"Connecting to {data['host']}...")
                subprocess.Popen(f"start cmd /k ssh {data['host']}", shell=True)
            elif data["type"] == "chronos_log":
                _log_to_chronos(self, data["content"])
            elif data["type"] == "chronos_task":
                _add_task_chronos(self, data["content"])
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
