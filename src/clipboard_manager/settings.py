"""Shared clipboard-manager configuration helpers."""

import json
import os

from src.common.config import CLIPBOARD_SETTINGS_FILE

DEFAULT_HISTORY_LIMIT = 50
_DEFAULT_SETTINGS = {"history_limit": DEFAULT_HISTORY_LIMIT, "enabled": True}


def _ensure_settings_dir() -> None:
    dir_path = os.path.dirname(CLIPBOARD_SETTINGS_FILE)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)


def _write_settings(data: dict) -> None:
    _ensure_settings_dir()
    with open(CLIPBOARD_SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _ensure_settings_file() -> None:
    if not os.path.exists(CLIPBOARD_SETTINGS_FILE):
        _write_settings(_DEFAULT_SETTINGS.copy())


def _load_raw_settings() -> dict:
    _ensure_settings_file()
    try:
        with open(CLIPBOARD_SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_history_limit() -> int:
    env_limit = os.getenv("NEXUS_CLIPBOARD_HISTORY_LIMIT")
    if env_limit:
        try:
            limit = int(env_limit)
        except ValueError:
            pass
        else:
            if limit > 0:
                return limit

    raw = _load_raw_settings()
    limit = raw.get("history_limit")
    if isinstance(limit, int) and limit > 0:
        return limit
    return DEFAULT_HISTORY_LIMIT


def is_clipboard_enabled() -> bool:
    raw = _load_raw_settings()
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        return enabled
    return True


def set_clipboard_enabled(enabled: bool) -> None:
    raw = _load_raw_settings()
    raw["enabled"] = bool(enabled)
    _write_settings(raw)


def toggle_clipboard_enabled() -> bool:
    new_state = not is_clipboard_enabled()
    set_clipboard_enabled(new_state)
    return new_state
