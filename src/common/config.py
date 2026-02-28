"""Centralized configuration and path constants for Nexus Search."""


import os


# --- CONFIGURATION (Shared with other apps) ---
def get_appdata_dir():
    if os.name == "nt":
        # Windows: use APPDATA
        return os.getenv("APPDATA", ".")
    # Unix/Linux: use XDG_DATA_HOME or ~/.local/share/fast-explorer
    xdg_data_home = os.getenv("XDG_DATA_HOME")
    if xdg_data_home:
        return os.path.join(xdg_data_home, "fast-explorer")
    return os.path.expanduser("~/.local/share/fast-explorer")

APPDATA = get_appdata_dir()
os.makedirs(APPDATA, exist_ok=True)
DB_PATH = os.path.join(APPDATA, "context_switcher.db")
X_EXPLORER_DB = os.path.join(APPDATA, "x_explorer_cache.db")
GHOST_TYPIST_DB = os.path.join(APPDATA, "ghost_typist.db")
SETTINGS_FILE = os.path.join(APPDATA, "nexus_settings.json")
USAGE_FILE = os.path.join(APPDATA, "nexus_usage.json")
APPS_CACHE_FILE = os.path.join(APPDATA, "nexus_apps_cache.json")
SEARCH_HISTORY_FILE = os.path.join(APPDATA, "nexus_history.json")
FILE_OPS_SETTINGS = os.path.join(APPDATA, "nexus_file_ops.json")
ARCHIVER_SETTINGS = os.path.join(APPDATA, "nexus_archiver.json")
CHRONOS_DIR = os.path.join(APPDATA, ".chronos_app")
CHRONOS_DB = os.path.join(CHRONOS_DIR, "chronos_data.db")
CHRONOS_SETTINGS = os.path.join(CHRONOS_DIR, "chronos_settings.json")

# --- HOTKEY ---
SUMMON_HOTKEY = "ctrl+shift+space"
IMG_TO_TEXT_HOTKEY = "ctrl+shift+q"

# --- PROJECT PATHS ---
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "nexus_icon.png")
