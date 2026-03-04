"""Virtual-desktop screenshot capture with Wayland fallback."""
from __future__ import annotations

import contextlib
import os
import time

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QGuiApplication, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication


def _is_wayland() -> bool:
    import sys

    if sys.platform != "linux":
        return False
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    display = os.environ.get("WAYLAND_DISPLAY", "")
    return session == "wayland" or bool(display)


def _capture_wayland() -> tuple[QPixmap, QRect] | None:
    """Try to capture the screen on Wayland using grim or spectacle CLI."""
    import shutil
    import subprocess
    import tempfile

    screens = QGuiApplication.screens()
    virtual_geo = QRect(
        min(s.geometry().left() for s in screens),
        min(s.geometry().top() for s in screens),
        max(s.geometry().right() for s in screens)
        - min(s.geometry().left() for s in screens),
        max(s.geometry().bottom() for s in screens)
        - min(s.geometry().top() for s in screens),
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name

    try:
        # grim: wlroots/KDE Wayland screenshooter (most reliable)
        if shutil.which("grim"):
            ret = subprocess.run(["grim", tmp], timeout=5)
            if ret.returncode == 0:
                px = QPixmap(tmp)
                if not px.isNull():
                    return px, virtual_geo

        # spectacle (KDE) — background fullscreen capture
        if shutil.which("spectacle"):
            ret = subprocess.run(
                ["spectacle", "--background", "--nonotify", "--fullscreen", "--output", tmp],
                timeout=8,
            )
            if ret.returncode == 0:
                px = QPixmap(tmp)
                if not px.isNull():
                    return px, virtual_geo

        # gnome-screenshot fallback
        if shutil.which("gnome-screenshot"):
            ret = subprocess.run(["gnome-screenshot", "-f", tmp], timeout=5)
            if ret.returncode == 0:
                px = QPixmap(tmp)
                if not px.isNull():
                    return px, virtual_geo
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            os.unlink(tmp)

    return None


def capture_virtual_desktop() -> tuple[QPixmap, QRect]:
    """Capture the virtual desktop with robust handling for Linux/KDE/Wayland."""
    # Aggressive event pump and delay to ensure launcher is hidden
    for _ in range(12):
        QApplication.processEvents()
        time.sleep(0.04)

    screens = QGuiApplication.screens()
    if not screens:
        raise RuntimeError("No screens detected")

    # On Wayland, grabWindow(0) returns black — use native tools instead
    if _is_wayland():
        result = _capture_wayland()
        if result is not None:
            return result

    # Calculate virtual geometry
    v_left = min(s.geometry().left() for s in screens)
    v_top = min(s.geometry().top() for s in screens)
    v_right = max(s.geometry().right() for s in screens)
    v_bottom = max(s.geometry().bottom() for s in screens)
    virtual_geo = QRect(v_left, v_top, v_right - v_left, v_bottom - v_top)

    canvas = QPixmap(virtual_geo.size())
    canvas.fill(Qt.GlobalColor.black)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    for screen in screens:
        geo = screen.geometry()
        shot = screen.grabWindow(0)
        if not shot.isNull():
            painter.drawPixmap(
                geo.x() - virtual_geo.x(), geo.y() - virtual_geo.y(), shot
            )
    painter.end()

    # If the capture is somehow still black/empty, try primary screen direct grab
    if canvas.isNull() or (canvas.width() < 10 and canvas.height() < 10):
        primary = QGuiApplication.primaryScreen()
        canvas = primary.grabWindow(0)
        virtual_geo = primary.geometry()

    return canvas, virtual_geo
