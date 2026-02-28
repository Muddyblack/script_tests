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
