"""Run Ghost Typist standalone: python -m src.ghost_typist"""

import sys

from PyQt6.QtWidgets import QApplication

from src.ghost_typist.ghost_typist import GhostTypistApp

if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.ghost_typist")
    app = QApplication(sys.argv)
    win = GhostTypistApp()
    win.show()
    sys.exit(app.exec())
