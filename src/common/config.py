"""Centralized configuration and path constants for Nexus Search."""

import os
import sys

# ---------------------------------------------------------------------------
# Root resolution — behaves differently when running as a frozen .exe
# ---------------------------------------------------------------------------
# When bundled with PyInstaller (--onefile or --onedir):
#   sys.frozen  = True
#   sys._MEIPASS = temp extraction dir that holds assets / src code
#   sys.executable = the actual .exe on disk
#
# We keep the ``data/`` folder NEXT TO the exe so user data survives upgrades.
# Everything else (assets, HTML/CSS/JS) lives inside the bundle.
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # Frozen: code/assets come from the bundle; data lives beside the exe
    _BUNDLE_ROOT: str = sys._MEIPASS          # type: ignore[attr-defined]
    _DATA_ROOT:   str = os.path.dirname(sys.executable)
else:
    # Development: everything is relative to the repo root
    _BUNDLE_ROOT = os.path.dirname(           # repo root
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    _DATA_ROOT = _BUNDLE_ROOT

# Legacy alias used by a few internal modules (keep pointing at bundle root)
PROJECT_ROOT = _BUNDLE_ROOT

APPDATA = os.path.join(_DATA_ROOT, "data")
os.makedirs(APPDATA, exist_ok=True)

# --- Per-module databases & settings ---
DB_PATH = os.path.join(APPDATA, "context_switcher.db")
X_EXPLORER_DB = os.path.join(APPDATA, "x_explorer_cache.db")
GHOST_TYPIST_DB = os.path.join(APPDATA, "ghost_typist.db")
CLIPBOARD_DB = os.path.join(APPDATA, "nexus_clipboard.db")
CLIPBOARD_SETTINGS_FILE = os.path.join(APPDATA, "nexus_clipboard.json")
SETTINGS_FILE = os.path.join(APPDATA, "nexus_settings.json")
USAGE_FILE = os.path.join(APPDATA, "nexus_usage.json")
APPS_CACHE_FILE = os.path.join(APPDATA, "nexus_apps_cache.json")
SEARCH_HISTORY_FILE = os.path.join(APPDATA, "nexus_history.json")
FILE_OPS_SETTINGS = os.path.join(APPDATA, "nexus_file_ops.json")
ARCHIVER_SETTINGS = os.path.join(APPDATA, "nexus_archiver.json")
WORKSPACES_FILE = os.path.join(APPDATA, "nexus_workspaces.json")
COLOR_PICKER_CONFIG = os.path.join(APPDATA, "nexus_color_picker.json")

# Chronos sub-folder
CHRONOS_DIR = os.path.join(APPDATA, "chronos")
CHRONOS_DB = os.path.join(CHRONOS_DIR, "chronos_data.db")
CHRONOS_SETTINGS = os.path.join(CHRONOS_DIR, "chronos_settings.json")
os.makedirs(CHRONOS_DIR, exist_ok=True)

# --- HOTKEY ---
SUMMON_HOTKEY = "ctrl+shift+space"
IMG_TO_TEXT_HOTKEY = "ctrl+shift+q"
CHRONOS_HOTKEY = "ctrl+shift+c"

# --- PROJECT PATHS ---
ASSETS_DIR = os.path.join(_BUNDLE_ROOT, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "nexus_icon.png")
OCR_ICON_PATH = os.path.join(ASSETS_DIR, "ocr_icon.png")
CHRONOS_ICON_PATH = os.path.join(ASSETS_DIR, "chronos.png")
GHOST_TYPIST_ICON_PATH = os.path.join(ASSETS_DIR, "ghost_typist.png")
PORT_INSPECTOR_ICON_PATH = os.path.join(ASSETS_DIR, "port_inspector.png")
X_EXPLORER_ICON_PATH = os.path.join(ASSETS_DIR, "xexplorer.png")
HASH_TOOL_ICON_PATH = os.path.join(ASSETS_DIR, "hash_tool.png")
CLIPBOARD_MANAGER_ICON_PATH = os.path.join(ASSETS_DIR, "clipboard_manager.png")
COLOR_PICKER_ICON_PATH = os.path.join(ASSETS_DIR, "color_picker.png")
REGEX_HELPER_ICON_PATH = os.path.join(ASSETS_DIR, "regex_sandbox.png")
