"""Color helpers — theme-aware QColor accessors for the img_to_text package.

Mirrors the pattern used in nexus/themes.py but returns QColor / rgba strings
directly from the active ThemeManager instance.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor

from src.common.theme import ThemeManager

# ── rgba helper (mirrors nexus/themes.py _c_rgba) ─────────────────────────

def _c_rgba(mgr: ThemeManager, key: str, alpha: int) -> str:
    """Return theme color *key* as ``rgba(r,g,b,alpha)`` string."""
    hex_col = mgr[key]
    h = hex_col.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_col


# ── Lazy QColor accessors ──────────────────────────────────────────────────

class _C:
    """Thin wrapper that pulls live theme colors as QColor on every access.

    Use the module-level ``C`` singleton everywhere in this package.
    """

    def __init__(self) -> None:
        self._mgr: ThemeManager | None = None

    @property
    def mgr(self) -> ThemeManager:
        if self._mgr is None:
            self._mgr = ThemeManager()
        return self._mgr

    @property
    def ACCENT(self) -> QColor:
        return QColor(self.mgr["accent"])

    @property
    def ACCENT_LITE(self) -> QColor:
        return QColor(self.mgr["accent_pressed"])

    @property
    def SUCCESS(self) -> QColor:
        return QColor(self.mgr["success"])

    @property
    def WARNING(self) -> QColor:
        return QColor(self.mgr["warning"])

    @property
    def ERROR(self) -> QColor:
        return QColor(self.mgr["danger"])

    @property
    def BG(self) -> QColor:
        c = QColor(self.mgr["bg_base"])
        c.setAlpha(245)
        return c

    @property
    def TEXT(self) -> QColor:
        return QColor(self.mgr["text_primary"])

    @property
    def TEXT_DIM(self) -> QColor:
        return QColor(self.mgr["text_secondary"])

    @property
    def OVERLAY_DIM(self) -> QColor:
        return QColor(0, 0, 0, 160)


#: Module-level singleton — import ``C`` directly in sibling modules.
C = _C()
