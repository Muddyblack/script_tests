"""Centralized configuration and path constants for Nexus Search."""

import os

# ---------------------------------------------------------------------------
# Data directory — everything lives INSIDE the project.
# ---------------------------------------------------------------------------
# Absolute path to the repository root (two levels up from src/common/)
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

APPDATA = os.path.join(PROJECT_ROOT, "data")
os.makedirs(APPDATA, exist_ok=True)

# --- Per-module databases & settings ---
DB_PATH = os.path.join(APPDATA, "context_switcher.db")
X_EXPLORER_DB = os.path.join(APPDATA, "x_explorer_cache.db")
GHOST_TYPIST_DB = os.path.join(APPDATA, "ghost_typist.db")
CLIPBOARD_DB = os.path.join(APPDATA, "nexus_clipboard.db")
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
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
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