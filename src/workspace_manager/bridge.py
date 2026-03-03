"""Workspace Manager — PyQt/JS bridge exposed to the WebEngine page."""

import json
import os
import subprocess
import time
import ctypes
import ctypes.wintypes
from pathlib import Path
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

try:
    from src.common.config import APPDATA
except ImportError:
    APPDATA = os.getenv("APPDATA", ".")

DATA_FILE = os.path.join(APPDATA, "nexus_workspaces.json")

# Win32 helpers for window positioning
user32 = ctypes.windll.user32
SW_RESTORE = 9


def _screen_size() -> tuple[int, int]:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _detect_project_type(path: str) -> str:
    """Detect project type from folder contents."""
    try:
        items = os.listdir(path)
    except Exception:
        return "folder"
    if "Cargo.toml" in items:
        return "rust"
    if "pyproject.toml" in items or "setup.py" in items:
        return "python"
    if "package.json" in items:
        return "node"
    if ".git" in items:
        return "git"
    return "folder"


def _snap_rect(preset: str) -> tuple[int, int, int, int]:
    sw, sh = _screen_size()
    hw, hh = sw // 2, sh // 2
    presets = {
        "default": (0, 0, 0, 0),  # let OS decide
        "left_half": (0, 0, hw, sh),
        "right_half": (hw, 0, hw, sh),
        "top_half": (0, 0, sw, hh),
        "bottom_half": (0, hh, sw, hh),
        "top_left": (0, 0, hw, hh),
        "top_right": (hw, 0, hw, hh),
        "bottom_left": (0, hh, hw, hh),
        "bottom_right": (hw, hh, hw, hh),
        "fullscreen": (0, 0, sw, sh),
        "center_80": (int(sw * 0.1), int(sh * 0.1), int(sw * 0.8), int(sh * 0.8)),
        "center_60": (int(sw * 0.2), int(sh * 0.2), int(sw * 0.6), int(sh * 0.6)),
    }
    return presets.get(preset, (0, 0, 0, 0))


def _find_vscode_recent() -> list[dict]:
    """Read VS Code's recent workspaces from globalStorage/storage.json."""
    results = []
    seen = set()

    # Check common VS Code data paths
    roaming = os.environ.get("APPDATA", "")
    candidates = [
        os.path.join(roaming, "Code", "User", "globalStorage", "storage.json"),
        os.path.join(roaming, "Code - Insiders", "User", "globalStorage", "storage.json"),
    ]

    for storage_path in candidates:
        if not os.path.isfile(storage_path):
            continue
        try:
            with open(storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # VS Code stores opened paths in several keys
            entries = []
            for key in (
                "openedPathsList",
                "lastKnownMenubarData",
            ):
                val = data.get(key)
                if isinstance(val, dict):
                    # openedPathsList has { workspaces3: [...], files2: [...], entries: [...] }
                    for sub_key in ("workspaces3", "entries", "folders3"):
                        items = val.get(sub_key, [])
                        if isinstance(items, list):
                            entries.extend(items)

            for entry in entries:
                folder_uri = None
                if isinstance(entry, str):
                    folder_uri = entry
                elif isinstance(entry, dict):
                    folder_uri = entry.get("folderUri") or entry.get("workspace", {}).get("configPath", "")

                if not folder_uri:
                    continue

                # Convert file:///C:/... URI to path
                if folder_uri.startswith("file:///"):
                    parsed = urlparse(folder_uri)
                    folder_path = unquote(parsed.path)
                    # Windows: strip leading / from /C:/path
                    if len(folder_path) > 2 and folder_path[0] == "/" and folder_path[2] == ":":
                        folder_path = folder_path[1:]
                    folder_path = folder_path.replace("/", os.sep)
                elif folder_uri.startswith("vscode-remote://"):
                    continue  # skip remote workspaces
                else:
                    folder_path = folder_uri

                folder_path = os.path.normpath(folder_path)

                if folder_path in seen:
                    continue
                seen.add(folder_path)

                exists = os.path.isdir(folder_path)
                name = os.path.basename(folder_path)

                results.append({
                    "path": folder_path,
                    "name": name,
                    "exists": exists,
                    "source": "vscode_recent",
                })
        except Exception:
            continue

    return results


class WorkspaceBridge(QObject):
    """Singleton object registered as ``pyBridge`` in the QWebChannel."""

    workspace_opened = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = self._load_data()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load_data(self) -> dict:
        try:
            if os.path.isfile(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"workspaces": [], "next_id": 1}

    def _save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    # ── Bridge slots ────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_workspaces(self) -> str:
        """Return saved workspaces as JSON."""
        for ws in self._data["workspaces"]:
            ws["exists"] = os.path.isdir(ws.get("path", ""))
            # Auto-detect project type if not set
            if ws["exists"] and not ws.get("project_type"):
                ws["project_type"] = _detect_project_type(ws["path"])
                ws["has_git"] = os.path.isdir(os.path.join(ws["path"], ".git"))
        return json.dumps(self._data["workspaces"])

    @pyqtSlot(result=str)
    def scan_vscode_recent(self) -> str:
        """Scan VS Code's recent workspaces and return as JSON."""
        results = _find_vscode_recent()
        return json.dumps(results)

    @pyqtSlot(str, result=str)
    def add_workspace(self, json_str: str) -> str:
        """Add a new workspace. Input: { path, name?, tags?, position?, color? }"""
        try:
            entry = json.loads(json_str)
        except Exception:
            return json.dumps({"error": "Invalid JSON"})

        path = entry.get("path", "").strip()
        if not path:
            return json.dumps({"error": "Path is required"})

        path = os.path.normpath(path)

        # Check for duplicates
        for ws in self._data["workspaces"]:
            if os.path.normpath(ws["path"]) == path:
                return json.dumps({"error": "Workspace already exists", "id": ws["id"]})

        ws_id = self._data["next_id"]
        self._data["next_id"] = ws_id + 1

        workspace = {
            "id": ws_id,
            "path": path,
            "name": entry.get("name") or os.path.basename(path),
            "tags": entry.get("tags", []),
            "pinned": entry.get("pinned", False),
            "position": entry.get("position", "default"),
            "color": entry.get("color", ""),
            "last_opened": None,
            "open_count": 0,
            "exists": os.path.isdir(path),
        }

        self._data["workspaces"].append(workspace)
        self._save_data()
        return json.dumps(workspace)

    @pyqtSlot(str, result=str)
    def update_workspace(self, json_str: str) -> str:
        """Update workspace fields. Input: { id, ...fields }"""
        try:
            updates = json.loads(json_str)
        except Exception:
            return json.dumps({"error": "Invalid JSON"})

        ws_id = updates.get("id")
        for ws in self._data["workspaces"]:
            if ws["id"] == ws_id:
                for key in ("name", "tags", "pinned", "position", "color"):
                    if key in updates:
                        ws[key] = updates[key]
                self._save_data()
                return json.dumps(ws)
        return json.dumps({"error": "Not found"})

    @pyqtSlot(int, result=str)
    def delete_workspace(self, ws_id: int) -> str:
        """Remove a workspace by id."""
        before = len(self._data["workspaces"])
        self._data["workspaces"] = [w for w in self._data["workspaces"] if w["id"] != ws_id]
        self._save_data()
        return json.dumps({"deleted": before != len(self._data["workspaces"])})

    @pyqtSlot(str, str, result=str)
    def open_workspace(self, path: str, position: str) -> str:
        """Open a folder in VS Code, optionally position the window."""
        path = path.strip().strip('"')
        if not os.path.isdir(path):
            return json.dumps({"error": f"Folder not found: {path}"})

        try:
            # Try 'code' command first, fall back to full path
            try:
                subprocess.Popen(["code", path], shell=True)
            except FileNotFoundError:
                # Try standard VS Code install location
                code_exe = os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    "Programs", "Microsoft VS Code", "Code.exe",
                )
                if os.path.isfile(code_exe):
                    subprocess.Popen([code_exe, path])
                else:
                    return json.dumps({"error": "VS Code not found"})

            # Update usage stats
            for ws in self._data["workspaces"]:
                if os.path.normpath(ws["path"]) == os.path.normpath(path):
                    ws["last_opened"] = time.time()
                    ws["open_count"] = ws.get("open_count", 0) + 1
                    self._save_data()
                    break

            # Position the window after a short delay (let VS Code start)
            if position and position != "default":
                rect = _snap_rect(position)
                if rect != (0, 0, 0, 0):
                    self._schedule_position(path, rect)

            self.workspace_opened.emit(path)
            return json.dumps({"ok": True, "path": path})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _schedule_position(self, path: str, rect: tuple):
        """Position the VS Code window after it opens."""
        import threading

        def _do_position():
            folder_name = os.path.basename(path)
            x, y, w, h = rect
            # Wait for VS Code window to appear
            for _ in range(30):
                time.sleep(0.5)
                hwnd = _find_vscode_window(folder_name)
                if hwnd:
                    user32.ShowWindow(hwnd, SW_RESTORE)
                    user32.MoveWindow(hwnd, x, y, w, h, True)
                    return

        threading.Thread(target=_do_position, daemon=True).start()

    @pyqtSlot(result=str)
    def browse_folder(self) -> str:
        """Open native folder picker dialog."""
        path = QFileDialog.getExistingDirectory(None, "Select Workspace Folder")
        return path or ""

    @pyqtSlot(result=str)
    def get_screen_info(self) -> str:
        """Return screen size as JSON."""
        sw, sh = _screen_size()
        return json.dumps({"width": sw, "height": sh})

    @pyqtSlot(result=str)
    def get_position_presets(self) -> str:
        """Return available position presets."""
        presets = [
            {"id": "default", "label": "Default", "icon": "Monitor"},
            {"id": "left_half", "label": "Left Half", "icon": "PanelLeft"},
            {"id": "right_half", "label": "Right Half", "icon": "PanelRight"},
            {"id": "top_half", "label": "Top Half", "icon": "PanelTop"},
            {"id": "bottom_half", "label": "Bottom Half", "icon": "PanelBottom"},
            {"id": "top_left", "label": "Top Left", "icon": "ArrowUpLeft"},
            {"id": "top_right", "label": "Top Right", "icon": "ArrowUpRight"},
            {"id": "bottom_left", "label": "Bottom Left", "icon": "ArrowDownLeft"},
            {"id": "bottom_right", "label": "Bottom Right", "icon": "ArrowDownRight"},
            {"id": "fullscreen", "label": "Full Screen", "icon": "Maximize2"},
            {"id": "center_80", "label": "Center 80%", "icon": "Square"},
            {"id": "center_60", "label": "Center 60%", "icon": "Minimize2"},
        ]
        return json.dumps(presets)

    @pyqtSlot(str, result=str)
    def get_folder_info(self, path: str) -> str:
        """Get folder metadata."""
        path = path.strip().strip('"')
        if not os.path.isdir(path):
            return json.dumps({"error": "Not a directory"})

        try:
            items = os.listdir(path)
            has_git = ".git" in items
            has_package = "package.json" in items
            has_pyproject = "pyproject.toml" in items or "setup.py" in items
            has_cargo = "Cargo.toml" in items
            has_vscode = ".vscode" in items

            # Detect project type
            project_type = "folder"
            if has_cargo:
                project_type = "rust"
            elif has_pyproject:
                project_type = "python"
            elif has_package:
                project_type = "node"
            elif has_git:
                project_type = "git"

            file_count = sum(1 for i in items if os.path.isfile(os.path.join(path, i)))
            dir_count = sum(1 for i in items if os.path.isdir(os.path.join(path, i)))

            return json.dumps({
                "name": os.path.basename(path),
                "path": path,
                "files": file_count,
                "dirs": dir_count,
                "has_git": has_git,
                "has_vscode": has_vscode,
                "project_type": project_type,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(str, result=str)
    def import_from_recent(self, json_str: str) -> str:
        """Import a VS Code recent entry as a saved workspace."""
        try:
            entry = json.loads(json_str)
        except Exception:
            return json.dumps({"error": "Invalid JSON"})

        return self.add_workspace(json.dumps({
            "path": entry.get("path", ""),
            "name": entry.get("name", ""),
        }))


def _find_vscode_window(folder_name: str) -> int | None:
    """Find a VS Code window whose title contains the folder name."""
    RECT = ctypes.wintypes.RECT
    result = [None]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if folder_name.lower() in title.lower() and "visual studio code" in title.lower():
            result[0] = hwnd
            return False  # stop enumeration
        return True

    user32.EnumWindows(_cb, 0)
    return result[0]
