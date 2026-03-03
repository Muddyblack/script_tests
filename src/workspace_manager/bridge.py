"""Workspace Manager — PyQt/JS bridge exposed to the WebEngine page.

A *workspace* is a named collection of program entries, each with an
executable path (or shell command) and an optional window position/size.
Launching a workspace opens every entry and snaps each window into place.

Also exposes live-window listing so users can pick from currently open
programs and capture their positions into a workspace.
"""
import copy
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import threading
import time
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

try:
    from src.common.config import APPDATA
except ImportError:
    APPDATA = os.getenv("APPDATA", ".")

DATA_FILE = os.path.join(APPDATA, "nexus_workspaces.json")

# ── Win32 constants & helpers ──────────────────────────────────────────────
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
RECT = ctypes.wintypes.RECT

SW_RESTORE = 9
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_SHOW = 5
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",    ctypes.wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork",    RECT),
        ("dwFlags",   ctypes.wintypes.DWORD),
    ]


def _screen_size() -> tuple[int, int]:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _get_monitors() -> list[dict]:
    """Return all monitors, primary first."""
    results: list[dict] = []
    idx = [0]

    @ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.wintypes.HMONITOR,
        ctypes.wintypes.HDC,
        ctypes.POINTER(RECT),
        ctypes.wintypes.LPARAM,
    )
    def _cb(hMon, _hdc, _lprc, _data):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hMon, ctypes.byref(mi))
        r = mi.rcMonitor
        results.append({
            "index":   idx[0],
            "x":       r.left,
            "y":       r.top,
            "w":       r.right  - r.left,
            "h":       r.bottom - r.top,
            "primary": bool(mi.dwFlags & 1),
        })
        idx[0] += 1
        return True

    user32.EnumDisplayMonitors(None, None, _cb, 0)
    results.sort(key=lambda m: (not m["primary"], m["x"]))
    return results


def _get_pid(hwnd: int) -> int:
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _get_proc_name(pid: int) -> str:
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            buf = ctypes.create_unicode_buffer(260)
            size = ctypes.wintypes.DWORD(260)
            ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            kernel32.CloseHandle(h)
            if ok:
                return os.path.basename(buf.value)
    except Exception:
        pass
    return "?"


def _get_exec_path(pid: int) -> str:
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            buf = ctypes.create_unicode_buffer(260)
            size = ctypes.wintypes.DWORD(260)
            ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            kernel32.CloseHandle(h)
            if ok:
                return buf.value
    except Exception:
        pass
    return ""


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _list_windows() -> list[dict]:
    hwnds: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _cb(hwnd, _lp):
        if (
            user32.IsWindowVisible(hwnd)
            and user32.GetWindowTextLengthW(hwnd) > 0
            and user32.GetWindow(hwnd, GW_OWNER) == 0
        ):
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW:
                return True
            hwnds.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    results = []
    for hwnd in hwnds:
        title = _get_window_title(hwnd)
        if not title:
            continue
        pid = _get_pid(hwnd)
        proc_name = _get_proc_name(pid)
        exec_path = _get_exec_path(pid)
        left, top, right, bottom = _get_window_rect(hwnd)
        results.append({
            "hwnd": hwnd,
            "title": title,
            "pid": pid,
            "proc_name": proc_name,
            "exec_path": exec_path,
            "x": left,
            "y": top,
            "w": right - left,
            "h": bottom - top,
        })
    return results


def _move_window(hwnd: int, x: int, y: int, w: int, h: int):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.MoveWindow(hwnd, x, y, w, h, True)


def _focus_window(hwnd: int):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)


# ── Snap presets ───────────────────────────────────────────────────────────

POSITION_PRESETS = [
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
    {"id": "custom", "label": "Custom XY", "icon": "Move"},
]


def _snap_rect(preset: str, monitor_index: int = 0) -> tuple[int, int, int, int]:
    monitors = _get_monitors()
    if monitors and 0 <= monitor_index < len(monitors):
        mon = monitors[monitor_index]
        mx, my, sw, sh = mon["x"], mon["y"], mon["w"], mon["h"]
    else:
        mx, my = 0, 0
        sw, sh = _screen_size()
    hw, hh = sw // 2, sh // 2
    presets = {
        "default":      (0, 0, 0, 0),
        "left_half":    (mx,      my,      hw,           sh),
        "right_half":   (mx + hw, my,      hw,           sh),
        "top_half":     (mx,      my,      sw,           hh),
        "bottom_half":  (mx,      my + hh, sw,           hh),
        "top_left":     (mx,      my,      hw,           hh),
        "top_right":    (mx + hw, my,      hw,           hh),
        "bottom_left":  (mx,      my + hh, hw,           hh),
        "bottom_right": (mx + hw, my + hh, hw,           hh),
        "fullscreen":   (mx,      my,      sw,           sh),
        "center_80":    (mx + int(sw * 0.1), my + int(sh * 0.1), int(sw * 0.8), int(sh * 0.8)),
        "center_60":    (mx + int(sw * 0.2), my + int(sh * 0.2), int(sw * 0.6), int(sh * 0.6)),
    }
    return presets.get(preset, (0, 0, 0, 0))


# ── IDE detection from open windows ─────────────────────────────────────────

# Maps process exe name → (entry_type, ide_key).  Separators used in window title
# to extract the project path: VS Code / Cursor use " — ", JetBrains use " – ".
_PROC_TO_IDE: dict[str, tuple[str, str]] = {
    "code.exe":          ("ide", "vscode"),
    "cursor.exe":        ("ide", "cursor"),
    "windsurf.exe":      ("ide", "windsurf"),
    "idea64.exe":        ("ide", "intellij"),
    "pycharm64.exe":     ("ide", "pycharm"),
    "webstorm64.exe":    ("ide", "webstorm"),
    "clion64.exe":       ("ide", "clion"),
    "rider64.exe":       ("ide", "rider"),
    "goland64.exe":      ("ide", "goland"),
    "rubymine64.exe":    ("ide", "rubymine"),
    "datagrip64.exe":    ("ide", "datagrip"),
    "sublime_text.exe":  ("ide", "sublime"),
    "nvim.exe":          ("ide", "nvim"),
}


def _detect_window_ide(proc_name: str, exec_path: str, title: str) -> tuple[str, str, str]:
    """Return (entry_type, ide_key, path) for a window.

    Tries to extract a project path/name from the window title.
    Falls back to ('program', '', exec_path) for non-IDE windows.
    """
    pn = proc_name.lower()
    match = _PROC_TO_IDE.get(pn)
    if not match:
        for exe, val in _PROC_TO_IDE.items():
            if pn.endswith(exe):
                match = val
                break
    if not match:
        return "program", "", exec_path

    etype, ide_key = match
    path = exec_path
    for sep in (" — ", " – ", " - "):
        if sep in title:
            path = title.split(sep)[0].strip()
            break
    return etype, ide_key, path


# ── VS Code recent scanner ────────────────────────────────────────────────

def _find_vscode_recent() -> list[dict]:
    results = []
    seen = set()
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
            entries = []
            for key in ("openedPathsList", "lastKnownMenubarData"):
                val = data.get(key)
                if isinstance(val, dict):
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
                if folder_uri.startswith("file:///"):
                    parsed = urlparse(folder_uri)
                    folder_path = unquote(parsed.path)
                    if len(folder_path) > 2 and folder_path[0] == "/" and folder_path[2] == ":":
                        folder_path = folder_path[1:]
                    folder_path = folder_path.replace("/", os.sep)
                elif folder_uri.startswith("vscode-remote://"):
                    continue
                else:
                    folder_path = folder_uri
                folder_path = os.path.normpath(folder_path)
                if folder_path in seen:
                    continue
                seen.add(folder_path)
                results.append({
                    "path": folder_path,
                    "name": os.path.basename(folder_path),
                    "exists": os.path.isdir(folder_path),
                    "source": "vscode_recent",
                })
        except Exception:
            continue
    return results


# ── Window list worker (background thread) ─────────────────────────────────

class _WindowListWorker(QThread):
    done = pyqtSignal(str)

    def run(self):
        try:
            self.done.emit(json.dumps(_list_windows()))
        except Exception:
            self.done.emit(json.dumps([]))


# ── Bridge ─────────────────────────────────────────────────────────────────

class WorkspaceBridge(QObject):
    """Singleton object registered as ``pyBridge`` in the QWebChannel."""

    workspace_opened = pyqtSignal(str)
    windows_refreshed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = self._load_data()
        self._worker: _WindowListWorker | None = None

    # ── Persistence ────────────────────────────────────────────────────────

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

    # ── Open windows ───────────────────────────────────────────────────────

    @pyqtSlot()
    def refresh_windows(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = _WindowListWorker(self)
        self._worker.done.connect(self.windows_refreshed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    @pyqtSlot(result=str)
    def list_windows_sync(self) -> str:
        return json.dumps(_list_windows())

    @pyqtSlot(int, str)
    def snap_window(self, hwnd: int, preset: str) -> None:
        rect = _snap_rect(preset)
        if rect != (0, 0, 0, 0):
            _move_window(hwnd, *rect)

    @pyqtSlot(int, int, int, int, int)
    def move_window_to(self, hwnd: int, x: int, y: int, w: int, h: int) -> None:
        _move_window(hwnd, x, y, w, h)

    @pyqtSlot(int)
    def focus_window(self, hwnd: int) -> None:
        _focus_window(hwnd)

    @pyqtSlot(int)
    def minimize_window(self, hwnd: int) -> None:
        user32.ShowWindow(hwnd, SW_MINIMIZE)

    @pyqtSlot(int)
    def maximize_window(self, hwnd: int) -> None:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)

    @pyqtSlot(int)
    def close_window(self, hwnd: int) -> None:
        user32.PostMessageW(hwnd, 0x0010, 0, 0)

    # ── Workspace CRUD ─────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_workspaces(self) -> str:
        return json.dumps(self._data["workspaces"])

    @pyqtSlot(str, result=str)
    def save_workspace(self, json_str: str) -> str:
        """Add or update a workspace.

        Input: { id?, name, entries: [{ type, path?, args?, position?, x?, y?, w?, h?, title_hint?, proc_name? }] }
        If `id` is present, updates; otherwise creates new.
        """
        try:
            entry = json.loads(json_str)
        except Exception:
            return json.dumps({"error": "Invalid JSON"})

        name = entry.get("name", "").strip()
        if not name:
            return json.dumps({"error": "Name is required"})

        ws_id = entry.get("id")

        if ws_id is not None:
            # Update existing
            for ws in self._data["workspaces"]:
                if ws["id"] == ws_id:
                    ws["name"] = name
                    ws["entries"] = entry.get("entries", ws.get("entries", []))
                    if "pinned" in entry:
                        ws["pinned"] = entry["pinned"]
                    if "color" in entry:
                        ws["color"] = entry["color"]
                    self._save_data()
                    return json.dumps(ws)
            return json.dumps({"error": "Not found"})

        # Create new
        ws_id = self._data["next_id"]
        self._data["next_id"] = ws_id + 1

        workspace = {
            "id": ws_id,
            "name": name,
            "entries": entry.get("entries", []),
            "pinned": entry.get("pinned", False),
            "color": entry.get("color", ""),
            "last_opened": None,
            "open_count": 0,
        }
        self._data["workspaces"].append(workspace)
        self._save_data()
        return json.dumps(workspace)

    @pyqtSlot(int, result=str)
    def delete_workspace(self, ws_id: int) -> str:
        before = len(self._data["workspaces"])
        self._data["workspaces"] = [w for w in self._data["workspaces"] if w["id"] != ws_id]
        self._save_data()
        return json.dumps({"deleted": before != len(self._data["workspaces"])})

    @pyqtSlot(int, bool)
    def toggle_pin(self, ws_id: int, pinned: bool) -> None:
        for ws in self._data["workspaces"]:
            if ws["id"] == ws_id:
                ws["pinned"] = pinned
                self._save_data()
                return

    # ── Launch workspace ───────────────────────────────────────────────────

    @pyqtSlot(int, result=str)
    def launch_workspace(self, ws_id: int) -> str:
        ws = None
        for w in self._data["workspaces"]:
            if w["id"] == ws_id:
                ws = w
                break
        if not ws:
            return json.dumps({"error": "Workspace not found"})

        entries = ws.get("entries", [])
        if not entries:
            return json.dumps({"error": "Workspace is empty"})

        ws["last_opened"] = time.time()
        ws["open_count"] = ws.get("open_count", 0) + 1
        self._save_data()

        threading.Thread(
            target=self._launch_entries, args=(entries,), daemon=True
        ).start()

        self.workspace_opened.emit(ws["name"])
        return json.dumps({"ok": True, "launched": len(entries)})

    def _launch_entries(self, entries: list[dict]):
        for entry in entries:
            entry_type  = entry.get("type", "program")
            path        = entry.get("path", "")
            args        = entry.get("args", "")
            position    = entry.get("position", "default")
            monitor     = entry.get("monitor", 0)
            window_wait = float(entry.get("window_wait", 1.8))
            launch_delay = float(entry.get("launch_delay", 0.3))
            custom_rect = (
                entry.get("x", 0), entry.get("y", 0),
                entry.get("w", 0), entry.get("h", 0),
            )

            if entry.get("close_existing", False):
                self._close_existing_processes(path)

            try:
                if entry_type in ("ide", "vscode"):
                    self._launch_ide(path, entry.get("ide", "vscode"))
                elif entry_type == "url":
                    os.startfile(path)
                elif entry_type == "program":
                    if args:
                        subprocess.Popen(f'"{path}" {args}', shell=True)
                    else:
                        subprocess.Popen([path], shell=True)
                elif entry_type == "shell":
                    subprocess.Popen(path, shell=True)
            except Exception:
                continue

            if position != "default" or any(v != 0 for v in custom_rect):
                time.sleep(window_wait)
                hwnd = self._find_new_window(path, entry_type, entry.get("title_hint", ""))
                if hwnd:
                    if position == "custom" and any(v != 0 for v in custom_rect):
                        _move_window(hwnd, *custom_rect)
                    elif position != "default":
                        rect = _snap_rect(position, monitor)
                        if rect != (0, 0, 0, 0):
                            _move_window(hwnd, *rect)

            time.sleep(launch_delay)

    def _close_existing_processes(self, path: str) -> None:
        """Terminate any running processes whose exe name matches *path*."""
        target = os.path.basename(path).lower()
        if not target:
            return
        try:
            seen: set[int] = set()
            for w in _list_windows():
                pn  = w["proc_name"].lower()
                ep  = os.path.basename(w.get("exec_path", "")).lower()
                if target in pn or (ep and target in ep):
                    pid = w["pid"]
                    if pid and pid not in seen:
                        seen.add(pid)
            for pid in seen:
                try:
                    h = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
                    if h:
                        kernel32.TerminateProcess(h, 0)
                        kernel32.CloseHandle(h)
                except Exception:
                    pass
            if seen:
                time.sleep(0.8)
        except Exception:
            pass

    # ── IDE launcher ───────────────────────────────────────────────────────
    _IDE_CLI = {
        "vscode":         "code",
        "cursor":         "cursor",
        "windsurf":       "windsurf",
        "zed":            "zed",
        "intellij":       "idea",
        "pycharm":        "pycharm",
        "webstorm":       "webstorm",
        "clion":          "clion",
        "rider":          "rider",
        "goland":         "goland",
        "android_studio": "studio",
        "rubymine":       "mine",
        "datagrip":       "datagrip",
        "sublime":        "subl",
        "nvim":           "nvim",
    }

    def _launch_ide(self, path: str, ide_key: str = "vscode"):
        import glob as _glob
        # 1. Try CLI on PATH (works for most cross-platform + JetBrains Toolbox shell scripts)
        cli = self._IDE_CLI.get(ide_key, ide_key)
        try:
            subprocess.Popen([cli, path], shell=True)
            return
        except Exception:
            pass

        local = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        prog = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        prog86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")

        # 2. Known install paths per IDE
        candidates: list[str] = {
            "vscode": [
                os.path.join(local, "Programs", "Microsoft VS Code", "Code.exe"),
            ],
            "cursor": [
                os.path.join(local, "Programs", "cursor", "Cursor.exe"),
                os.path.join(local, "cursor", "Cursor.exe"),
            ],
            "windsurf": [
                os.path.join(local, "Programs", "Windsurf", "Windsurf.exe"),
                os.path.join(local, "Windsurf", "Windsurf.exe"),
            ],
            "zed": [
                os.path.join(local, "Zed", "zed.exe"),
                os.path.join(prog, "Zed", "zed.exe"),
            ],
            "sublime": [
                os.path.join(prog, "Sublime Text", "sublime_text.exe"),
                os.path.join(prog, "Sublime Text 4", "sublime_text.exe"),
                os.path.join(prog, "Sublime Text 3", "sublime_text.exe"),
                os.path.join(prog86, "Sublime Text", "sublime_text.exe"),
            ],
            "nvim": [
                os.path.join(prog, "Neovim", "bin", "nvim.exe"),
                os.path.join(local, "Programs", "Neovim", "bin", "nvim.exe"),
            ],
            "android_studio": [
                os.path.join(prog, "Android", "Android Studio", "bin", "studio64.exe"),
            ],
        }.get(ide_key, [])

        # JetBrains: search Program Files install + Toolbox
        _jb_names = {
            "intellij":  ("IntelliJ IDEA*",  "idea64.exe"),
            "pycharm":   ("PyCharm*",         "pycharm64.exe"),
            "webstorm":  ("WebStorm*",        "webstorm64.exe"),
            "clion":     ("CLion*",           "clion64.exe"),
            "rider":     ("Rider*",           "rider64.exe"),
            "goland":    ("GoLand*",          "goland64.exe"),
            "rubymine":  ("RubyMine*",        "rubymine64.exe"),
            "datagrip":  ("DataGrip*",        "datagrip64.exe"),
        }
        if ide_key in _jb_names:
            pattern, exe = _jb_names[ide_key]
            # Standard JetBrains install
            for root in (prog, prog86):
                hits = _glob.glob(os.path.join(root, "JetBrains", pattern, "bin", exe))
                candidates.extend(sorted(hits, reverse=True))
            # JetBrains Toolbox
            toolbox_root = os.path.join(local, "JetBrains", "Toolbox", "apps")
            toolbox_hits = _glob.glob(os.path.join(toolbox_root, "**", "bin", exe), recursive=True)
            candidates.extend(sorted(toolbox_hits, reverse=True))

        for exe_path in candidates:
            if os.path.isfile(exe_path):
                subprocess.Popen([exe_path, path])
                return

    def _find_new_window(self, path: str, entry_type: str, title_hint: str) -> int | None:
        search_terms = []
        if title_hint:
            search_terms.append(title_hint.lower()[:40])
        if entry_type in ("vscode", "ide"):
            search_terms.append(os.path.basename(path).lower())
        else:
            search_terms.append(os.path.splitext(os.path.basename(path))[0].lower())

        for _ in range(12):
            wins = _list_windows()
            for w in wins:
                title_lower = w["title"].lower()
                proc_lower = w["proc_name"].lower()
                for term in search_terms:
                    if term and (term in title_lower or term in proc_lower):
                        return w["hwnd"]
            time.sleep(0.5)
        return None

    # ── Capture from open windows ──────────────────────────────────────────

    @pyqtSlot(str, result=str)
    def capture_windows(self, json_str: str) -> str:
        """Create workspace entries from selected open windows.

        Input: { name, hwnds: [int, ...] }
        """
        try:
            data = json.loads(json_str)
        except Exception:
            return json.dumps({"error": "Invalid JSON"})

        name = data.get("name", "").strip()
        hwnds = data.get("hwnds", [])
        if not name:
            return json.dumps({"error": "Name is required"})
        if not hwnds:
            return json.dumps({"error": "No windows selected"})

        all_wins = _list_windows()
        win_map = {w["hwnd"]: w for w in all_wins}

        entries = []
        for hwnd in hwnds:
            w = win_map.get(hwnd)
            if not w:
                continue
            entry_type, ide_key, path = _detect_window_ide(
                w["proc_name"], w["exec_path"], w["title"]
            )
            entry: dict = {
                "type":       entry_type,
                "path":       path,
                "title_hint": w["title"][:80],
                "proc_name":  w["proc_name"],
                "position":   "custom",
                "x": w["x"], "y": w["y"],
                "w": w["w"], "h": w["h"],
            }
            if ide_key:
                entry["ide"] = ide_key
            entries.append(entry)

        return self.save_workspace(json.dumps({"name": name, "entries": entries}))

    # ── Duplicate / Export / Import ───────────────────────────────────────

    @pyqtSlot(int, result=str)
    def duplicate_workspace(self, ws_id: int) -> str:
        """Clone a workspace with ' (copy)' appended to its name."""
        for ws in self._data["workspaces"]:
            if ws["id"] == ws_id:
                new_ws = copy.deepcopy(ws)
                new_ws["id"]         = self._data["next_id"]
                self._data["next_id"] += 1
                new_ws["name"]       = ws["name"] + " (copy)"
                new_ws["pinned"]     = False
                new_ws["last_opened"] = None
                new_ws["open_count"] = 0
                self._data["workspaces"].append(new_ws)
                self._save_data()
                return json.dumps(new_ws)
        return json.dumps({"error": "Not found"})

    @pyqtSlot(int, result=str)
    def export_workspace(self, ws_id: int) -> str:
        """Save a single workspace to a user-chosen JSON file."""
        ws = next((w for w in self._data["workspaces"] if w["id"] == ws_id), None)
        if not ws:
            return json.dumps({"error": "Not found"})
        path, _ = QFileDialog.getSaveFileName(
            None, "Export Workspace",
            f"{ws['name']}.json", "JSON (*.json)"
        )
        if not path:
            return json.dumps({"cancelled": True})
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(ws, f, indent=2)
            return json.dumps({"ok": True, "path": path})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @pyqtSlot(result=str)
    def import_workspace(self) -> str:
        """Load a workspace from a user-chosen JSON file and add it."""
        path, _ = QFileDialog.getOpenFileName(
            None, "Import Workspace", "", "JSON (*.json)"
        )
        if not path:
            return json.dumps({"cancelled": True})
        try:
            with open(path, "r", encoding="utf-8") as f:
                ws = json.load(f)
        except Exception as e:
            return json.dumps({"error": str(e)})
        ws.pop("id", None)
        ws.pop("open_count", None)
        ws.pop("last_opened", None)
        return self.save_workspace(json.dumps(ws))

    # ── Save all open windows ──────────────────────────────────────────────

    @pyqtSlot(str, result=str)
    def save_all_windows(self, name: str) -> str:
        """Capture every currently visible window as a new workspace."""
        name = name.strip()
        if not name:
            return json.dumps({"error": "Name is required"})
        all_wins = _list_windows()
        if not all_wins:
            return json.dumps({"error": "No open windows found"})
        hwnds = [w["hwnd"] for w in all_wins]
        return self.capture_windows(json.dumps({"name": name, "hwnds": hwnds}))

    # ── VS Code recent ─────────────────────────────────────────────────────

    # ── Installed apps ─────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_installed_apps(self) -> str:
        """Return the nexus apps cache (list of {name, path} dicts)."""
        try:
            cache_path = os.path.join(APPDATA, "nexus_apps_cache.json")
            if not os.path.isfile(cache_path):
                return json.dumps([])
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Filter out junk (uninstallers, docs, urls)
            skip = {"uninstall", "readme", "help", "documentation", "release notes",
                    "website", "faq", "more...", "user guide"}
            filtered = [
                a for a in data
                if isinstance(a, dict)
                and not any(s in a.get("name", "").lower() for s in skip)
                and a.get("path", "").endswith((".lnk", ".exe"))
            ]
            return json.dumps(filtered)
        except Exception as e:
            return json.dumps([])

    # ── Utilities ──────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def browse_folder(self) -> str:
        path = QFileDialog.getExistingDirectory(None, "Select Folder")
        return path or ""

    @pyqtSlot(result=str)
    def browse_file(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            None, "Select Program", "",
            "Executables (*.exe *.bat *.cmd *.lnk);;All Files (*)"
        )
        return path or ""

    @pyqtSlot(result=str)
    def get_screen_info(self) -> str:
        sw, sh = _screen_size()
        return json.dumps({"width": sw, "height": sh})

    @pyqtSlot(result=str)
    def get_monitors(self) -> str:
        """Return list of all connected monitors with geometry."""
        return json.dumps(_get_monitors())

    @pyqtSlot(int, str, int)
    def snap_window_on(self, hwnd: int, preset: str, monitor_index: int) -> None:
        """Snap *hwnd* to *preset* on the given monitor index."""
        rect = _snap_rect(preset, monitor_index)
        if rect != (0, 0, 0, 0):
            _move_window(hwnd, *rect)

    @pyqtSlot(result=str)
    def get_position_presets(self) -> str:
        return json.dumps(POSITION_PRESETS)
