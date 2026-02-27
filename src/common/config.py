"""Centralized configuration and path constants for Nexus Search."""

import os

# --- CONFIGURATION (Shared with other apps) ---
APPDATA = os.getenv("APPDATA", ".")
DB_PATH = os.path.join(APPDATA, "context_switcher.db")
X_EXPLORER_DB = os.path.join(APPDATA, "x_explorer_cache.db")
GHOST_TYPIST_DB = os.path.join(APPDATA, "ghost_typist.db")
SETTINGS_FILE = os.path.join(APPDATA, "nexus_settings.json")
USAGE_FILE = os.path.join(APPDATA, "nexus_usage.json")
APPS_CACHE_FILE = os.path.join(APPDATA, "nexus_apps_cache.json")
SEARCH_HISTORY_FILE = os.path.join(APPDATA, "nexus_history.json")

# --- HOTKEY ---
SUMMON_HOTKEY = "ctrl+shift+space"

# --- PROJECT PATHS ---
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "nexus_icon.png")
