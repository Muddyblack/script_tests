"""Hash Tool — WebEngine-powered file & text hashing window."""

import os
import sys

from PyQt6.QtWidgets import QApplication

from src.common.web_app_window import BaseWebApp
from src.hash_tool.bridge import HashToolBridge


class HashTool(BaseWebApp):
    WINDOW_TITLE = "Hash Tool"
    ICON_NAME = "hash_tool"
    DEFAULT_SIZE = (780, 680)
    MIN_SIZE = (620, 520)

    def create_bridge(self) -> HashToolBridge:
        return HashToolBridge(self)

    def html_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "hash_tool.html")


def launch() -> "HashTool":
    """Create and show the window."""
    win = HashTool()
    win.show()
    return win


def main() -> None:
    """Standalone entry point — creates its own QApplication."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.hash_tool")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = HashTool()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

