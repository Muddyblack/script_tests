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
    return not (
        "WAYLAND_DISPLAY" in os.environ
        or os.environ.get("XDG_SESSION_TYPE") == "wayland"
    )


def parse_chronos_input(text: str):
    """Parses special syntax like !high, #tag, due:2024-05-01 from a string."""
    import re

    content = text
    priority = "Medium"
    tags = []
    due_date = ""

    # Priority
    if "!high" in content.lower() or "!h" in content.lower():
        priority = "High"
        content = re.sub(r"!(?:high|h)\b", "", content, flags=re.IGNORECASE)
    elif "!low" in content.lower() or "!l" in content.lower():
        priority = "Low"
        content = re.sub(r"!(?:low|l)\b", "", content, flags=re.IGNORECASE)

    # Tags
    tag_matches = re.findall(r"#(\w+)", content)
    if tag_matches:
        tags = tag_matches
        content = re.sub(r"#\w+", "", content)

    # Due date (e.g. due:2024-05-01 or due:today)
    date_match = re.search(r"due:(\S+)", content, flags=re.IGNORECASE)
    if date_match:
        dv = date_match.group(1).lower()
        import datetime

        d = datetime.date.today()
        if dv == "today":
            due_date = d.isoformat()
        elif dv == "tomorrow":
            due_date = (d + datetime.timedelta(days=1)).isoformat()
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", dv):
            due_date = dv
        content = content.replace(date_match.group(0), "")

    return content.strip(), priority, tags, due_date
