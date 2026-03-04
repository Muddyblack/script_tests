"""OCR language/mode settings and recent-snip history.

All mutable globals live here so every sibling module accesses them through
a single authoritative location.
"""
from __future__ import annotations

import contextlib
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtGui import QImage

from src.common.config import APPDATA as _APPDATA

# ── Recent snip history ────────────────────────────────────────────────────


@dataclass
class SnipRecord:
    timestamp: datetime
    text: str
    image: QImage


recent_snips: deque[SnipRecord] = deque(maxlen=10)

# ── Persisted OCR settings ─────────────────────────────────────────────────

_OCR_SETTINGS_FILE = Path(_APPDATA) / "nexus_ocr_settings.json"

# Mutable globals — modified at runtime by _LangBar
ocr_langs: list[str] = ["en", "de"]
ocr_code_mode: bool = False
ocr_symbol_priority: bool = False
ocr_code_fix: bool = False


def load_ocr_settings() -> None:
    global ocr_langs, ocr_code_mode, ocr_symbol_priority, ocr_code_fix
    with contextlib.suppress(Exception):
        data = json.loads(_OCR_SETTINGS_FILE.read_text(encoding="utf-8"))
        ocr_langs = data.get("languages", ["en", "de"])
        ocr_code_mode = bool(data.get("code_mode", False))
        ocr_symbol_priority = bool(data.get("symbol_priority", False))
        ocr_code_fix = bool(data.get("code_fix", False))


def save_ocr_settings() -> None:
    with contextlib.suppress(Exception):
        _OCR_SETTINGS_FILE.write_text(
            json.dumps(
                {
                    "languages": ocr_langs,
                    "code_mode": ocr_code_mode,
                    "symbol_priority": ocr_symbol_priority,
                    "code_fix": ocr_code_fix,
                }
            ),
            encoding="utf-8",
        )


# Load on import
load_ocr_settings()
