"""Small utility functions shared across the Nexus package."""

import os
import subprocess
import sys


def format_display_name(name: str, max_len: int = 60) -> str:
    """Middle-elide long filenames to keep the UI clean."""
    if not name:
        return ""
    if len(name) <= max_len:
        return name
    half = (max_len - 3) // 2
    return f"{name[:half]}...{name[-half:]}"


def run_workspace(ws_id: int) -> None:
    """Launch a workspace by calling the context switcher script."""
    from src.common.config import PROJECT_ROOT

    script_path = os.path.join(PROJECT_ROOT, "context_switcher.py")
    subprocess.Popen([sys.executable, script_path, "--launch", str(ws_id)])


def is_opacity_supported() -> bool:
    """Return True if the current platform / window system supports window opacity.
    
    Avoids 'This plugin does not support setting window opacity' spam on Linux Wayland.
    """
    if sys.platform != "linux":
        return True

    # Check for Wayland (known problematic for Qt window opacity)
    if "WAYLAND_DISPLAY" in os.environ or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return False

    # For X11, we could check for a compositor via _NET_WM_CM_Sn, but usually it works.
    # However, for now, we'll assume it's OK unless it's Wayland.
    return True
