"""System tray icon for Nexus Search — shows the app is running in the background."""

import os

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from src.common.config import ICON_PATH


def create_tray_icon(app, nexus) -> QSystemTrayIcon:
    """Create and configure the system-tray icon.

    Returns the QSystemTrayIcon so the caller can keep a reference
    (prevents garbage collection).
    """
    # Build icon — fall back to a default if asset is missing
    if os.path.exists(ICON_PATH):
        icon = QIcon(ICON_PATH)
    else:
        icon = app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon)

    tray = QSystemTrayIcon(icon, parent=app)
    tray.setToolTip("Nexus Search — Ctrl+Shift+Space to summon")

    # --- Context menu ---
    menu = QMenu()
    menu.setStyleSheet(
        "QMenu { background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; "
        "border-radius: 8px; } "
        "QMenu::item { padding: 6px 20px; } "
        "QMenu::item:selected { background-color: #3b82f6; color: white; }"
    )

    show_action = QAction("🔍  Show Nexus", menu)
    show_action.triggered.connect(nexus.summon)
    menu.addAction(show_action)

    ocr_action = QAction("🖼️  Snip → Text (OCR)", menu)
    ocr_action.triggered.connect(nexus.start_img_to_text)
    menu.addAction(ocr_action)

    menu.addSeparator()

    quit_action = QAction("❌  Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)

    # Double-click / single-click to toggle
    tray.activated.connect(lambda reason: _on_tray_activated(reason, nexus))

    tray.show()
    return tray


def _on_tray_activated(reason, nexus) -> None:
    """Toggle visibility on tray icon click."""
    if reason in (
        QSystemTrayIcon.ActivationReason.Trigger,
        QSystemTrayIcon.ActivationReason.DoubleClick,
    ):
        if nexus.isVisible():
            nexus.hide()
        else:
            nexus.summon()
