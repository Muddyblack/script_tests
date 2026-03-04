"""Nexus File Tools — web-powered File Ops & Archiver window.

Converted to use the shared BaseWebApp / QWebEngineView pattern so the UI
is a React app (same stack as Hash Tool, Ghost Typist, etc.).

External API (backward-compat with Nexus launcher + XExplorer callers):
    win = FileToolsWindow()
    win.fo_sources  = [...]          # pre-populate FILE OPS queue
    win.arc_sources = [...]          # pre-populate ARCHIVER queue
    win.source_paths = [...]         # alias used by some callers
    win._fo_refresh()                # flush fo_sources → bridge
    win._arc_refresh()               # flush arc_sources → bridge
    win._refresh_list()              # flush both
    win._switch_tab("archiver")      # set initial tab
    win.show()

Also re-exports is_archive() for legacy import compatibility.
"""

import argparse
import ctypes
import os
import sys

from PyQt6.QtWidgets import QApplication

from src.common.web_app_window import BaseWebApp
from src.file_ops.bridge import FileToolsBridge, _is_archive


# ── Public compat re-export ───────────────────────────────────────────────────

def is_archive(path: str) -> bool:
    """Return True if *path* is a recognised archive format."""
    return _is_archive(path)


# ── Window ────────────────────────────────────────────────────────────────────

class FileToolsWindow(BaseWebApp):
    WINDOW_TITLE = "NEXUS FILE TOOLS"
    ICON_NAME    = "fileops"
    DEFAULT_SIZE = (820, 720)
    MIN_SIZE     = (660, 560)

    def __init__(self) -> None:
        # Public backward-compat attributes — set BEFORE show().
        # Callers set these then call the refresh/switch shims.
        self.fo_sources:   list[str] = []
        self.arc_sources:  list[str] = []
        self.source_paths: list[str] = []
        self._initial_tab: str = "fileops"
        super().__init__()

    def create_bridge(self) -> FileToolsBridge:
        return FileToolsBridge(self)

    def html_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_ops.html")

    # ── Backward-compat shims ─────────────────────────────────────────────────

    def _fo_refresh(self) -> None:
        """Push fo_sources into the bridge so JS picks them up on load."""
        self.bridge.set_initial_fo_sources(self.fo_sources)

    def _arc_refresh(self) -> None:
        """Push arc_sources into the bridge so JS picks them up on load."""
        self.bridge.set_initial_arc_sources(self.arc_sources)

    def _refresh_list(self) -> None:
        if self.source_paths:
            self.fo_sources  = list(self.source_paths)
            self.arc_sources = list(self.source_paths)
        self._fo_refresh()
        self._arc_refresh()

    def _switch_tab(self, tab: str) -> None:
        self._initial_tab = tab
        self.bridge.set_initial_tab(tab)


# ── Entry points ──────────────────────────────────────────────────────────────

def launch() -> FileToolsWindow:
    """Create and show the window (called from Nexus / other tools)."""
    win = FileToolsWindow()
    win.show()
    return win


def main() -> None:
    """Standalone entry point — creates its own QApplication."""
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.filetools")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tab",
        choices=["fileops", "archiver"],
        default="fileops",
        help="Which tab to open on launch",
    )
    args, _ = parser.parse_known_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = FileToolsWindow()
    win._switch_tab(args.tab)
    win.show()
    sys.exit(app.exec())


def main_archiver() -> None:
    """Entry point that opens directly on the Archiver tab."""
    sys.argv += ["--tab", "archiver"]
    main()


if __name__ == "__main__":
    main()