"""
X-Explorer — Windows-11-style file explorer with blazing-fast search.
Drop-in replacement for the original x_explorer.py.
Requires: PyQt6, watchdog (optional)
"""

import contextlib
import json
import os
import sqlite3
import sys
import time

from PyQt6.QtCore import (
    QRect,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.archiver.archiver import ArchiverWindow, is_archive
from src.common.config import ASSETS_DIR
from src.common.config import X_EXPLORER_DB as DB_PATH
from src.common.search_engine import SearchEngine
from src.file_ops.file_ops import FileOpsWindow

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
#  THEME SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

class Theme:
    DARK = {
        "name": "dark",
        # Surfaces
        "bg_base":        "#1c1c1c",
        "bg_elevated":    "#252525",
        "bg_overlay":     "#2d2d2d",
        "bg_control":     "#333333",
        "bg_control_hov": "#3d3d3d",
        "bg_control_prs": "#292929",
        # Accents
        "accent":         "#0078d4",
        "accent_hover":   "#1a86d8",
        "accent_pressed": "#006cbf",
        "accent_subtle":  "#0078d415",
        # Borders
        "border":         "#404040",
        "border_light":   "#505050",
        "border_focus":   "#0078d4",
        # Text
        "text_primary":   "#f3f3f3",
        "text_secondary": "#ababab",
        "text_disabled":  "#666666",
        "text_on_accent": "#ffffff",
        # Semantic
        "sel_bg":         "#0078d4",
        "sel_bg_unfocus": "#394955",
        "row_alt":        "#202020",
        "icon_folder":    "#dcb967",
        "icon_file":      "#9db8d2",
        "icon_code":      "#7ec8a0",
        "icon_media":     "#c8a0e8",
        "icon_archive":   "#e8b870",
        "success":        "#4caf74",
        "danger":         "#f47174",
        "warning":        "#f0a030",
        # Sidebar
        "sidebar_bg":     "#1c1c1c",
        "sidebar_item":   "#1c1c1c",
        "sidebar_hover":  "#2a2a2a",
        "sidebar_sel":    "#0078d420",
        "sidebar_sel_bar":"#0078d4",
        # Tab bar
        "tab_bg":         "#1c1c1c",
        "tab_active":     "#252525",
        "tab_hover":      "#222222",
    }

    LIGHT = {
        "name": "light",
        "bg_base":        "#f3f3f3",
        "bg_elevated":    "#ffffff",
        "bg_overlay":     "#f9f9f9",
        "bg_control":     "#efefef",
        "bg_control_hov": "#e5e5e5",
        "bg_control_prs": "#d9d9d9",
        "accent":         "#0078d4",
        "accent_hover":   "#006cbf",
        "accent_pressed": "#005ba1",
        "accent_subtle":  "#0078d412",
        "border":         "#e0e0e0",
        "border_light":   "#d0d0d0",
        "border_focus":   "#0078d4",
        "text_primary":   "#1a1a1a",
        "text_secondary": "#5d5d5d",
        "text_disabled":  "#aaaaaa",
        "text_on_accent": "#ffffff",
        "sel_bg":         "#cde6f7",
        "sel_bg_unfocus": "#e5e5e5",
        "row_alt":        "#fafafa",
        "icon_folder":    "#dcb850",
        "icon_file":      "#4a8bbf",
        "icon_code":      "#3a9a60",
        "icon_media":     "#9050c8",
        "icon_archive":   "#c08030",
        "success":        "#107c10",
        "danger":         "#c42b1c",
        "warning":        "#9d5d00",
        "sidebar_bg":     "#f3f3f3",
        "sidebar_item":   "#f3f3f3",
        "sidebar_hover":  "#e8e8e8",
        "sidebar_sel":    "#cde6f720",
        "sidebar_sel_bar":"#0078d4",
        "tab_bg":         "#ebebeb",
        "tab_active":     "#f9f9f9",
        "tab_hover":      "#f0f0f0",
    }

    def __init__(self, dark=True):
        self._t = self.DARK.copy() if dark else self.LIGHT.copy()
        self.dark = dark

    def __getitem__(self, key):
        return self._t[key]

    def toggle(self):
        self.dark = not self.dark
        self._t = self.DARK.copy() if self.dark else self.LIGHT.copy()


# ═══════════════════════════════════════════════════════════════════════════════
#  SVG / VECTOR ICON PAINTER  (no emoji, no external files needed)
# ═══════════════════════════════════════════════════════════════════════════════

class Icons:
    """
    Generates QPixmap icons drawn with QPainter.
    All icons are vector-drawn at any size — crisp at all DPI.
    """

    @staticmethod
    def _base(size=20) -> tuple[QPixmap, QPainter]:
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return px, p

    @staticmethod
    def folder(color="#dcb967", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        c = QColor(color)
        # Body
        body = QPainterPath()
        body.moveTo(0, s * 0.35)
        body.lineTo(0, s * 0.85)
        body.arcTo(0, s * 0.7, s * 0.3, s * 0.3, 270, -90)
        body.lineTo(s * 0.15, s * 0.85)
        body.lineTo(s, s * 0.85)
        body.arcTo(s * 0.7, s * 0.7, s * 0.3, s * 0.3, 0, -90)
        body.lineTo(s, s * 0.35)
        body.closeSubpath()

        # Use simple rect approach instead
        p.setPen(Qt.PenStyle.NoPen)
        # Shadow / base
        p.setBrush(QBrush(c.darker(140)))
        p.drawRoundedRect(1, int(s*0.38), s-2, int(s*0.52), 3, 3)
        # Top tab
        p.setBrush(QBrush(c))
        p.drawRoundedRect(1, int(s*0.22), int(s*0.45), int(s*0.22), 2, 2)
        # Front face
        p.setBrush(QBrush(c))
        p.drawRoundedRect(1, int(s*0.34), s-2, int(s*0.5), 3, 3)
        # Highlight line
        p.setBrush(QBrush(c.lighter(130)))
        p.drawRoundedRect(3, int(s*0.36), s-6, int(s*0.08), 1, 1)
        p.end()
        return px

    @staticmethod
    def file_generic(color="#9db8d2", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        c = QColor(color)
        fold = int(s * 0.28)
        # Page outline
        path = QPainterPath()
        path.moveTo(2, 1)
        path.lineTo(s - 2 - fold, 1)
        path.lineTo(s - 2, 1 + fold)
        path.lineTo(s - 2, s - 1)
        path.lineTo(2, s - 1)
        path.closeSubpath()
        p.setPen(QPen(c.darker(120), 1))
        p.setBrush(QBrush(c.lighter(150)))
        p.drawPath(path)
        # Folded corner
        corner = QPainterPath()
        corner.moveTo(s - 2 - fold, 1)
        corner.lineTo(s - 2 - fold, 1 + fold)
        corner.lineTo(s - 2, 1 + fold)
        corner.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(c.darker(110)))
        p.drawPath(corner)
        # Lines (content preview)
        p.setPen(QPen(c.darker(140), 1))
        for i, y in enumerate(range(int(s*0.5), int(s*0.82), int(s*0.12))):
            w = (s - 7) if i % 2 == 0 else (s - 10)
            p.drawLine(4, y, w, y)
        p.end()
        return px

    @staticmethod
    def drive(color="#9db8d2", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        c = QColor(color)
        p.setPen(QPen(c.darker(130), 1))
        p.setBrush(QBrush(c.lighter(130)))
        p.drawRoundedRect(2, 4, s-4, s-8, 3, 3)
        # LED dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#4caf74")))
        p.drawEllipse(s-9, s-9, 4, 4)
        # Slot
        p.setPen(QPen(c.darker(150), 1))
        p.drawLine(4, s-8, s-10, s-8)
        p.end()
        return px

    @staticmethod
    def search(color="#ababab", size=16) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        c = QColor(color)
        pen = QPen(c, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        r = int(s * 0.55)
        p.drawEllipse(1, 1, r, r)
        cx = 1 + r//2; cy = 1 + r//2
        edge = int(r * 0.7)
        p.drawLine(cx + edge//2, cy + edge//2, s-2, s-2)
        p.end()
        return px

    @staticmethod
    def arrow_left(color="#ababab", size=16) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        pen = QPen(QColor(color), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        mid = s // 2
        tip = 4
        p.drawLine(s - tip, mid - 4, tip + 1, mid)
        p.drawLine(tip + 1, mid, s - tip, mid + 4)
        p.end()
        return px

    @staticmethod
    def arrow_right(color="#ababab", size=16) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        pen = QPen(QColor(color), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        mid = s // 2
        tip = s - 4
        p.drawLine(4, mid - 4, tip - 1, mid)
        p.drawLine(tip - 1, mid, 4, mid + 4)
        p.end()
        return px

    @staticmethod
    def arrow_up(color="#ababab", size=16) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        pen = QPen(QColor(color), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        mid = s // 2
        p.drawLine(mid - 4, s - 4, mid, 4)
        p.drawLine(mid, 4, mid + 4, s - 4)
        p.end()
        return px

    @staticmethod
    def refresh(color="#ababab", size=16) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        pen = QPen(QColor(color), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        from PyQt6.QtCore import QRectF
        p.drawArc(QRectF(2, 2, s-4, s-4), 30*16, 300*16)
        # Arrow head
        p.setPen(QPen(QColor(color), 1.5))
        p.drawLine(s-4, 3, s-4, 7)
        p.drawLine(s-4, 3, s-8, 3)
        p.end()
        return px

    @staticmethod
    def index_bolt(color="#f0c040", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        c = QColor(color)
        path = QPainterPath()
        path.moveTo(s*0.6, 1)
        path.lineTo(s*0.2, s*0.5)
        path.lineTo(s*0.5, s*0.5)
        path.lineTo(s*0.35, s-1)
        path.lineTo(s*0.8, s*0.45)
        path.lineTo(s*0.5, s*0.45)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(c))
        p.drawPath(path)
        p.end()
        return px

    @staticmethod
    def trash(color="#ababab", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        c = QColor(color)
        pen = QPen(c, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Lid
        p.drawLine(3, 5, s-3, 5)
        p.drawLine(7, 5, 7, 3)
        p.drawLine(s-7, 5, s-7, 3)
        p.drawLine(7, 3, s-7, 3)
        # Body
        body = QPainterPath()
        body.moveTo(4, 6)
        body.lineTo(5, s-1)
        body.lineTo(s-5, s-1)
        body.lineTo(s-4, 6)
        p.drawPath(body)
        # Lines inside
        mid = s // 2
        p.drawLine(mid, 8, mid, s-3)
        p.drawLine(mid-3, 8, mid-3, s-3)
        p.drawLine(mid+3, 8, mid+3, s-3)
        p.end()
        return px

    @staticmethod
    def stop_circle(size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        from PyQt6.QtCore import QRectF
        p.setPen(QPen(QColor("#f47174"), 1.5))
        p.setBrush(QBrush(QColor("#f4717430")))
        p.drawEllipse(QRectF(2, 2, s-4, s-4))
        p.setPen(QPen(QColor("#f47174"), 2))
        p.drawLine(s//2 - 3, s//2 - 3, s//2 + 3, s//2 + 3)
        p.drawLine(s//2 + 3, s//2 - 3, s//2 - 3, s//2 + 3)
        p.end()
        return px

    @staticmethod
    def sun(size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        import math
        pen = QPen(QColor("#f0c040"), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(QBrush(QColor("#f0c040")))
        cx = cy = s // 2
        p.drawEllipse(cx - 3, cy - 3, 6, 6)
        for i in range(8):
            angle = i * 45
            rad = math.radians(angle)
            x1 = cx + int(5 * math.cos(rad))
            y1 = cy + int(5 * math.sin(rad))
            x2 = cx + int(8 * math.cos(rad))
            y2 = cy + int(8 * math.sin(rad))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(x1, y1, x2, y2)
        p.end()
        return px

    @staticmethod
    def moon(size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        from PyQt6.QtCore import QRectF
        p.setPen(QPen(QColor("#ababab"), 1.2))
        p.setBrush(QBrush(QColor("#ababab")))
        path = QPainterPath()
        path.moveTo(s*0.7, s*0.15)
        path.arcTo(QRectF(s*0.1, s*0.1, s*0.7, s*0.7), 60, -220)
        path.arcTo(QRectF(s*0.3, s*0.05, s*0.6, s*0.8), -90, 150)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
        p.end()
        return px

    @staticmethod
    def view_details(color="#ababab", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        pen = QPen(QColor(color), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for y in [5, 10, 15]:
            p.drawLine(2, y, s-2, y)
        p.end()
        return px

    @staticmethod
    def view_icons(color="#ababab", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        p.setPen(QPen(QColor(color), 1.2))
        p.setBrush(QBrush(QColor(color)))
        for x in [3, 11]:
            for y in [3, 11]:
                p.drawRoundedRect(x, y, 6, 6, 1, 1)
        p.end()
        return px

    @staticmethod
    def view_tree(color="#ababab", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        pen = QPen(QColor(color), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(4, 4, 4, s-4)
        p.drawLine(4, 4, s-2, 4)
        p.drawLine(4, 10, s-2, 10)
        p.drawLine(4, 16, s-2, 16)
        p.drawLine(7, 10, 7, 16)
        p.end()
        return px

    @staticmethod
    def add_folder(color="#0078d4", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        c = QColor(color)
        # Folder base
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#dcb967")))
        p.drawRoundedRect(1, int(s*0.34), s-2, int(s*0.5), 2, 2)
        p.setBrush(QBrush(QColor("#dcb967").darker(140)))
        p.drawRoundedRect(1, int(s*0.38), s-2, int(s*0.46), 2, 2)
        p.setBrush(QBrush(QColor("#dcb967")))
        p.drawRoundedRect(1, int(s*0.34), s-2, int(s*0.5), 2, 2)
        p.drawRoundedRect(1, int(s*0.22), int(s*0.38), int(s*0.18), 1, 1)
        # Plus badge
        p.setBrush(QBrush(c))
        p.drawEllipse(s-8, s-8, 8, 8)
        pen = QPen(QColor("white"), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(s-4, s-7, s-4, s-1)
        p.drawLine(s-7, s-4, s-1, s-4)
        p.end()
        return px

    @staticmethod
    def live_dot(size=10) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#4caf74")))
        p.drawEllipse(1, 1, s-2, s-2)
        p.end()
        return px

    @staticmethod
    def file_by_ext(ext: str, size=20) -> QPixmap:
        ext = ext.lower()
        CODE = {".py",".js",".ts",".jsx",".tsx",".html",".css",".cpp",".c",
                ".h",".java",".cs",".go",".rs",".rb",".php",".sh",".bash",
                ".kt",".swift",".vue",".json",".xml",".yaml",".yml",".toml"}
        MEDIA = {".mp3",".wav",".flac",".ogg",".mp4",".mkv",".avi",".mov",
                 ".wmv",".flv",".gif",".png",".jpg",".jpeg",".webp",".svg",
                 ".bmp",".ico",".tiff"}
        ARCH  = {".zip",".rar",".7z",".tar",".gz",".bz2",".xz",".dmg",".iso"}
        DOC   = {".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",
                 ".odt",".ods",".odp",".txt",".md",".rtf",".csv"}
        EXE   = {".exe",".msi",".bat",".cmd",".ps1",".app"}

        if ext in CODE:
            # Color code by language
            lang_colors = {
                ".py":"#3572A5", ".js":"#f0d050", ".ts":"#2d79c7",
                ".jsx":"#61dafb", ".tsx":"#61dafb", ".html":"#e44d26",
                ".css":"#264de4", ".cpp":"#659ad2", ".c":"#555555",
                ".java":"#b07219", ".cs":"#178600", ".go":"#00acd7",
                ".rs":"#dea584", ".rb":"#cc342d", ".sh":"#89e051",
                ".kt":"#a97bff", ".swift":"#f05138",
            }
            color = lang_colors.get(ext, "#7ec8a0")
            px, p = Icons._base(size)
            s = size
            fold = int(s * 0.26)
            path = QPainterPath()
            path.moveTo(2, 1)
            path.lineTo(s - 2 - fold, 1)
            path.lineTo(s - 2, 1 + fold)
            path.lineTo(s - 2, s - 1)
            path.lineTo(2, s - 1)
            path.closeSubpath()
            bg = QColor(color)
            bg.setAlpha(40)
            p.setPen(QPen(QColor(color), 1))
            p.setBrush(QBrush(bg))
            p.drawPath(path)
            corner = QPainterPath()
            corner.moveTo(s - 2 - fold, 1)
            corner.lineTo(s - 2 - fold, 1 + fold)
            corner.lineTo(s - 2, 1 + fold)
            corner.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(color)))
            p.drawPath(corner)
            # Extension text
            font = QFont("Segoe UI", max(4, size//5), QFont.Weight.Bold)
            p.setFont(font)
            p.setPen(QPen(QColor(color)))
            label = ext.lstrip(".")[:3].upper()
            p.drawText(QRect(1, int(s*0.55), s-2, int(s*0.4)),
                       Qt.AlignmentFlag.AlignCenter, label)
            p.end()
            return px

        elif ext in MEDIA:
            return Icons.file_generic("#c8a0e8", size)
        elif ext in ARCH:
            return Icons.file_generic("#e8b870", size)
        elif ext in DOC:
            doc_colors = {
                ".pdf":"#e84040", ".doc":"#2b5eb5", ".docx":"#2b5eb5",
                ".xls":"#1e7e45", ".xlsx":"#1e7e45",
                ".ppt":"#c04a20", ".pptx":"#c04a20",
            }
            return Icons.file_generic(doc_colors.get(ext, "#9db8d2"), size)
        elif ext in EXE:
            return Icons.file_generic("#a0a0a0", size)
        else:
            return Icons.file_generic("#9db8d2", size)


# ═══════════════════════════════════════════════════════════════════════════════
#  CUSTOM DELEGATES
# ═══════════════════════════════════════════════════════════════════════════════

class DetailsDelegate(QStyledItemDelegate):
    """Renders rows in the details view with proper icon + text layout."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 28)

    def paint(self, painter, option, index):
        T = self.theme
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_hovered  = option.state & QStyle.StateFlag.State_MouseOver

        if is_selected:
            painter.fillRect(option.rect, QColor(T["sel_bg"]))
        elif is_hovered:
            painter.fillRect(option.rect, QColor(T["bg_control_hov"]))
        elif index.row() % 2:
            painter.fillRect(option.rect, QColor(T["row_alt"]))

        # Icon (column 0 only)
        if index.column() == 0:
            icon: QIcon = index.data(Qt.ItemDataRole.DecorationRole)
            if icon:
                icon.paint(painter,
                           option.rect.x() + 4,
                           option.rect.y() + 4,
                           20, 20)
            x_text = option.rect.x() + 30
        else:
            x_text = option.rect.x() + 6

        # Text
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        color = QColor(T["text_primary"] if not is_selected or T.dark
                       else T["text_primary"])
        painter.setPen(color)
        font = QFont("Segoe UI", 10 if index.column() != 2 else 9)
        if index.column() == 2:
            font.setPointSize(9)
            painter.setPen(QColor(T["text_secondary"]))
        painter.setFont(font)
        text_rect = QRect(x_text, option.rect.y(),
                          option.rect.width() - x_text + option.rect.x() - 4,
                          option.rect.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)

        painter.restore()


# ═══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY, name TEXT, parent TEXT,
        is_dir INTEGER, last_seen INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS folder_stats (
        path TEXT PRIMARY KEY, last_indexed TEXT)""")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND INDEXER
# ═══════════════════════════════════════════════════════════════════════════════

class IndexerWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(int)

    def __init__(self, roots, ignore_list):
        super().__init__()
        self.roots = roots
        self.ignore_list = [i.lower() for i in ignore_list]
        self._running = True

    def stop(self): self._running = False

    def run(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=OFF")
        total, batch = 0, []
        BATCH = 5000

        for root_path in self.roots:
            if not self._running or not os.path.exists(root_path):
                continue
            for root, dirs, files in os.walk(root_path):
                if not self._running: break
                dirs[:] = [d for d in dirs
                           if d.lower() not in self.ignore_list
                           and os.path.abspath(os.path.join(root,d)).lower()
                               not in self.ignore_list]
                now = int(time.time())
                for d in dirs:
                    batch.append((os.path.join(root,d), d, root, 1, now))
                for f in files:
                    fp = os.path.abspath(os.path.join(root, f))
                    _, ext = os.path.splitext(f)
                    if (f.lower() not in self.ignore_list
                            and fp.lower() not in self.ignore_list
                            and ext.lower() not in self.ignore_list):
                        batch.append((fp, f, root, 0, now))
                if len(batch) >= BATCH:
                    c.executemany("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)", batch)
                    total += len(batch)
                    self.progress.emit(total, root[:70])
                    batch = []
                    conn.commit()

        if batch:
            c.executemany("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)", batch)
            total += len(batch)
            conn.commit()
        conn.close()
        self.finished.emit(total)


# ═══════════════════════════════════════════════════════════════════════════════
#  LIVE WATCHER
# ═══════════════════════════════════════════════════════════════════════════════

class LiveCacheUpdater(FileSystemEventHandler):
    def __init__(self, ignore_list):
        self.ignore_list = [i.lower() for i in ignore_list]
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._c = self._conn.cursor()

    def _skip(self, path):
        pl, nl = path.lower(), os.path.basename(path).lower()
        return any(ig in nl or ig in pl for ig in self.ignore_list)

    def on_created(self, event):
        if self._skip(event.src_path): return
        try:
            self._c.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)",
                (event.src_path, os.path.basename(event.src_path),
                 os.path.dirname(event.src_path),
                 1 if event.is_directory else 0, int(time.time())))
            self._conn.commit()
        except sqlite3.OperationalError: pass

    def on_deleted(self, event):
        try:
            self._c.execute("DELETE FROM files WHERE path=?", (event.src_path,))
            self._conn.commit()
        except sqlite3.OperationalError: pass

    def on_moved(self, event):
        self.on_deleted(event)
        class FE:
            def __init__(s,p,d): s.src_path=p; s.is_directory=d
        self.on_created(FE(event.dest_path, event.is_directory))


# ═══════════════════════════════════════════════════════════════════════════════
#  ICON-BUTTON WIDGET  (ribbon buttons)
# ═══════════════════════════════════════════════════════════════════════════════

class RibbonBtn(QWidget):
    clicked = pyqtSignal()

    def __init__(self, pixmap: QPixmap, label: str, theme: Theme, parent=None):
        super().__init__(parent)
        self._px = pixmap
        self._label = label
        self._theme = theme
        self._hov = False
        self._pressed = False
        self.setFixedSize(56, 52)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def setPixmap(self, px): self._px = px; self.update()

    def enterEvent(self, e): self._hov = True; self.update()
    def leaveEvent(self, e): self._hov = False; self._pressed = False; self.update()
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True; self.update()
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False; self.update()
            if self.rect().contains(e.pos()): self.clicked.emit()

    def paintEvent(self, e):
        T = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        if self._pressed:
            p.setBrush(QBrush(QColor(T["bg_control_prs"])))
            p.setPen(QPen(QColor(T["border"]), 1))
            p.drawRoundedRect(r, 4, 4)
        elif self._hov:
            p.setBrush(QBrush(QColor(T["bg_control_hov"])))
            p.setPen(QPen(QColor(T["border"]), 1))
            p.drawRoundedRect(r, 4, 4)
        # Icon
        if self._px:
            ix = (self.width() - 20) // 2
            p.drawPixmap(ix, 6, 20, 20, self._px)
        # Label
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        p.setPen(QColor(T["text_secondary"]))
        p.drawText(QRect(0, 28, self.width(), 18),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   self._label)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  ICON-ONLY NAV BUTTON  (back / forward / up / refresh)
# ═══════════════════════════════════════════════════════════════════════════════

class NavBtn(QWidget):
    clicked = pyqtSignal()

    def __init__(self, pixmap: QPixmap, theme: Theme, tooltip="", parent=None):
        super().__init__(parent)
        self._px = pixmap
        self._theme = theme
        self._hov = False
        self._pressed = False
        self.setFixedSize(30, 30)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if tooltip: self.setToolTip(tooltip)

    def setPixmap(self, px): self._px = px; self.update()

    def enterEvent(self, e): self._hov = True; self.update()
    def leaveEvent(self, e): self._hov = False; self._pressed = False; self.update()
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True; self.update()
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False; self.update()
            if self.rect().contains(e.pos()): self.clicked.emit()

    def paintEvent(self, e):
        T = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        if self._pressed:
            p.setBrush(QBrush(QColor(T["bg_control_prs"])))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(r, 4, 4)
        elif self._hov:
            p.setBrush(QBrush(QColor(T["bg_control_hov"])))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(r, 4, 4)
        if self._px:
            ix = (self.width() - 16) // 2
            iy = (self.height() - 16) // 2
            p.drawPixmap(ix, iy, 16, 16, self._px)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  SEARCH BAR
# ═══════════════════════════════════════════════════════════════════════════════

class SearchBar(QWidget):
    textChanged = pyqtSignal(str)

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._focused = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(16, 16)
        self._update_icon()
        layout.addWidget(self._icon_lbl)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Search files — type at least 2 chars")
        self.input.setFrame(False)
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self.textChanged)
        layout.addWidget(self.input)

        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _update_icon(self):
        px = Icons.search(self._theme["text_secondary"], 16)
        self._icon_lbl.setPixmap(px)

    def update_theme(self):
        self._update_icon()
        self.update()

    def paintEvent(self, e):
        T = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(0, 2, 0, -2)
        focused = self.input.hasFocus()
        bg = QColor(T["bg_elevated"] if T.dark else T["bg_control"])
        border = QColor(T["border_focus"] if focused else T["border"])
        p.setBrush(QBrush(bg))
        p.setPen(QPen(border, 1.5 if focused else 1))
        p.drawRoundedRect(r, 5, 5)
        p.end()

    def apply_input_style(self):
        T = self._theme
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {T['text_primary']};
                font-family: 'Segoe UI';
                font-size: 13px;
                selection-background-color: {T['accent']};
            }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR ITEM  (with optional selection indicator bar)
# ═══════════════════════════════════════════════════════════════════════════════

class SidebarList(QListWidget):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(1)
        self.setUniformItemSizes(False)
        self.update_style()

    def update_style(self):
        T = self._theme
        self.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
                padding: 2px 4px;
            }}
            QListWidget::item {{
                border-radius: 4px;
                padding: 5px 8px 5px 32px;
                color: {T['text_primary']};
                min-height: 22px;
            }}
            QListWidget::item:hover {{
                background: {T['sidebar_hover']};
            }}
            QListWidget::item:selected {{
                background: {T['accent']}22;
                color: {T['accent']};
                font-weight: 600;
            }}
            QListWidget::indicator {{
                width: 14px; height: 14px;
                margin-left: 8px;
                border: 1.5px solid {T['border_light']};
                border-radius: 3px;
                background: {T['bg_elevated']};
            }}
            QListWidget::indicator:checked {{
                background: {T['accent']};
                border-color: {T['accent']};
            }}
            QListWidget::indicator:unchecked:hover {{
                border-color: {T['accent']};
            }}
            QScrollBar:vertical {{
                background: transparent; width: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {T['border']}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
#  CHIP FILTER BUTTON
# ═══════════════════════════════════════════════════════════════════════════════

class ChipBtn(QPushButton):
    def __init__(self, text, theme: Theme, parent=None):
        super().__init__(text, parent)
        self._theme = theme
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(26)
        self.update_style()

    def update_style(self):
        T = self._theme
        self.setStyleSheet(f"""
            QPushButton {{
                background: {T['bg_control']};
                border: 1px solid {T['border']};
                border-radius: 13px;
                padding: 0 14px;
                color: {T['text_secondary']};
                font-family: 'Segoe UI';
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {T['bg_control_hov']};
                color: {T['text_primary']};
            }}
            QPushButton:checked {{
                background: {T['accent']};
                border-color: {T['accent']};
                color: white;
                font-weight: 600;
            }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class XExplorer(QMainWindow):

    def __init__(self):
        super().__init__()
        init_db()
        self.T = Theme(dark=True)
        self.view_mode   = "details"
        self.filter_type = "all"
        self._icon_cache: dict[str, QIcon] = {}

        self.setWindowTitle("X-Explorer")
        self.resize(1300, 800)
        self.setMinimumSize(900, 580)

        self._build_all()
        self.load_settings()
        self._apply_theme()

        icon_path = os.path.join(ASSETS_DIR, "xexplorer.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.observer = None
        if WATCHDOG_AVAILABLE:
            self.start_live_watchers()

        self.search_engine = SearchEngine(DB_PATH)

        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

        QTimer.singleShot(100, self.check_args)
        QTimer.singleShot(200, self.update_stats)

    # ──────────────────────────────────────────────────────────────────────────
    #  BUILD
    # ──────────────────────────────────────────────────────────────────────────

    def _build_all(self):
        self._build_titlebar_area()
        self._build_central()
        self._build_statusbar()

    def _build_titlebar_area(self):
        # Toolbar acts as our ribbon
        self._ribbon = QToolBar("Ribbon")
        self._ribbon.setMovable(False)
        self._ribbon.setFloatable(False)
        self._ribbon.setObjectName("ribbon_bar")
        self._ribbon.setFixedHeight(60)

        ribbon_widget = QWidget()
        rbl = QHBoxLayout(ribbon_widget)
        rbl.setContentsMargins(8, 4, 8, 4)
        rbl.setSpacing(2)

        T = self.T
        # Ribbon buttons
        self._rb_index  = RibbonBtn(Icons.index_bolt("#f0c040", 20), "Index", T)
        self._rb_stop   = RibbonBtn(Icons.stop_circle(20),            "Stop",  T)
        self._rb_clear  = RibbonBtn(Icons.trash(T["text_secondary"],20),"Clear DB", T)
        self._rb_theme  = RibbonBtn(Icons.moon(20),                    "Light", T)
        self._rb_detail = RibbonBtn(Icons.view_details(T["text_secondary"],20), "Details", T)
        self._rb_icons  = RibbonBtn(Icons.view_icons(T["text_secondary"],20),   "Icons",   T)
        self._rb_tree   = RibbonBtn(Icons.view_tree(T["text_secondary"],20),    "Tree",    T)

        self._rb_stop.setVisible(False)

        self._rb_index.clicked.connect(self.start_indexing)
        self._rb_stop.clicked.connect(self.stop_indexing)
        self._rb_clear.clicked.connect(self.clear_index)
        self._rb_theme.clicked.connect(self.toggle_theme)
        self._rb_detail.clicked.connect(lambda: self.set_view("details"))
        self._rb_icons.clicked.connect(lambda: self.set_view("icons"))
        self._rb_tree.clicked.connect(lambda: self.set_view("tree"))

        def sep():
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            f.setFixedWidth(1)
            f.setFixedHeight(36)
            return f

        for w in [self._rb_index, self._rb_stop, self._rb_clear, sep(),
                  self._rb_detail, self._rb_icons, self._rb_tree, sep(),
                  self._rb_theme]:
            rbl.addWidget(w)

        rbl.addStretch()
        self._ribbon.addWidget(ribbon_widget)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._ribbon)

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        vl = QVBoxLayout(central)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        vl.addWidget(self._build_address_row())
        vl.addWidget(self._build_filter_row())

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.addWidget(self._build_sidebar())
        self._splitter.addWidget(self._build_results_panel())
        self._splitter.setSizes([220, 1100])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        vl.addWidget(self._splitter, stretch=1)

    def _build_address_row(self):
        self._addr_row = QWidget()
        self._addr_row.setObjectName("addr_row")
        self._addr_row.setFixedHeight(44)
        hl = QHBoxLayout(self._addr_row)
        hl.setContentsMargins(8, 6, 8, 6)
        hl.setSpacing(4)

        T = self.T
        self._nav_back    = NavBtn(Icons.arrow_left(T["text_secondary"]),    T, "Back")
        self._nav_fwd     = NavBtn(Icons.arrow_right(T["text_secondary"]),   T, "Forward")
        self._nav_up      = NavBtn(Icons.arrow_up(T["text_secondary"]),      T, "Up")
        self._nav_refresh = NavBtn(Icons.refresh(T["text_secondary"]),       T, "Refresh")

        self._nav_refresh.clicked.connect(self.update_stats)

        for btn in [self._nav_back, self._nav_fwd, self._nav_up, self._nav_refresh]:
            hl.addWidget(btn)

        hl.addSpacing(4)

        self._search_bar = SearchBar(T)
        self._search_bar.textChanged.connect(self._on_search_changed)
        hl.addWidget(self._search_bar, stretch=1)

        return self._addr_row

    def _build_filter_row(self):
        self._filter_row = QWidget()
        self._filter_row.setObjectName("filter_row")
        self._filter_row.setFixedHeight(38)
        hl = QHBoxLayout(self._filter_row)
        hl.setContentsMargins(12, 5, 12, 5)
        hl.setSpacing(6)

        T = self.T
        self._chip_group = QButtonGroup(self)
        self._chips = {}

        for label, ftype in [("All","all"),("Files","files"),("Folders","folders"),("Content Search","content")]:
            btn = ChipBtn(label, T)
            if ftype == "all": btn.setChecked(True)
            btn.clicked.connect(lambda _, t=ftype: self.change_filter(t))
            self._chip_group.addButton(btn)
            self._chips[ftype] = btn
            hl.addWidget(btn)

        hl.addStretch()

        # Add Folder / Scan Drives
        self._btn_add_folder = QPushButton()
        self._btn_add_folder.setObjectName("add_btn")
        self._btn_add_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_add_folder.clicked.connect(self.add_managed_folder)
        hl.addWidget(self._btn_add_folder)

        self._btn_scan = QPushButton()
        self._btn_scan.setObjectName("add_btn")
        self._btn_scan.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_scan.clicked.connect(self.scan_drives)
        hl.addWidget(self._btn_scan)

        return self._filter_row

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar_frame")
        sidebar.setMinimumWidth(160)
        sidebar.setMaximumWidth(300)
        vl = QVBoxLayout(sidebar)
        vl.setContentsMargins(0, 8, 0, 8)
        vl.setSpacing(0)

        T = self.T

        def section(text):
            lbl = QLabel(text)
            lbl.setObjectName("section_lbl")
            lbl.setContentsMargins(12, 8, 0, 2)
            return lbl

        vl.addWidget(section("MANAGED FOLDERS"))
        self.folder_list = SidebarList(T)
        self.folder_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self.show_folder_ctx)
        self.folder_list.itemChanged.connect(self.save_settings)
        self.folder_list.itemChanged.connect(self.perform_search)
        self.folder_list.itemSelectionChanged.connect(self.perform_search)
        vl.addWidget(self.folder_list, stretch=2)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        vl.addWidget(sep)

        vl.addWidget(section("IGNORE LIST"))
        self.ignore_list = SidebarList(T)
        self.ignore_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ignore_list.customContextMenuRequested.connect(self.show_ignore_ctx)
        self.ignore_list.itemChanged.connect(self.save_settings)
        vl.addWidget(self.ignore_list, stretch=3)

        self._btn_add_ignore = QPushButton()
        self._btn_add_ignore.setObjectName("sidebar_action")
        self._btn_add_ignore.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_add_ignore.clicked.connect(self.add_ignore_rule)
        vl.addWidget(self._btn_add_ignore)

        return sidebar

    def _build_results_panel(self):
        container = QWidget()
        container.setObjectName("results_panel")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        self._stack = QStackedWidget()
        T = self.T

        # ── Details view ────────────────────────────────────────────────────
        self._details = QTreeWidget()
        self._details.setObjectName("details_view")
        self._details.setRootIsDecorated(False)
        self._details.setUniformRowHeights(True)
        self._details.setAlternatingRowColors(True)
        self._details.setHeaderLabels(["Name", "Type", "Location"])
        self._details.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._details.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._details.setSortingEnabled(True)
        self._details.setItemDelegate(DetailsDelegate(T))
        self._details.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._details.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._details.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._details.setColumnWidth(0, 320)
        self._details.setColumnWidth(1, 90)
        self._details.customContextMenuRequested.connect(
            lambda p: self._ctx_details(p))
        self._details.itemDoubleClicked.connect(
            lambda item: self._open_path(item.data(0, Qt.ItemDataRole.UserRole)))

        # ── Icons view ───────────────────────────────────────────────────────
        self._icons_view = QListWidget()
        self._icons_view.setObjectName("icons_view")
        self._icons_view.setViewMode(QListWidget.ViewMode.IconMode)
        self._icons_view.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._icons_view.setSpacing(6)
        self._icons_view.setGridSize(QSize(100, 86))
        self._icons_view.setIconSize(QSize(40, 40))
        self._icons_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._icons_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._icons_view.customContextMenuRequested.connect(
            lambda p: self._ctx_icons(p))
        self._icons_view.itemDoubleClicked.connect(
            lambda item: self._open_path(item.data(Qt.ItemDataRole.UserRole)))

        # ── Tree view ────────────────────────────────────────────────────────
        self._tree_view = QTreeWidget()
        self._tree_view.setObjectName("tree_view")
        self._tree_view.setHeaderLabels(["Name", "Full Path"])
        self._tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree_view.customContextMenuRequested.connect(
            lambda p: self._ctx_tree(p, self._tree_view))
        self._tree_view.itemDoubleClicked.connect(
            lambda item: self._open_path(item.data(0, Qt.ItemDataRole.UserRole)))
        self._tree_view.setColumnWidth(0, 300)

        self._stack.addWidget(self._details)    # 0
        self._stack.addWidget(self._icons_view) # 1
        self._stack.addWidget(self._tree_view)  # 2
        vl.addWidget(self._stack)
        return container

    def _build_statusbar(self):
        sb = QStatusBar()
        sb.setObjectName("main_sb")
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setObjectName("status_lbl")

        self._progress = QProgressBar()
        self._progress.setFixedSize(160, 6)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)

        self._live_dot  = QLabel()
        self._live_dot.setPixmap(Icons.live_dot(8))
        self._live_dot.setVisible(WATCHDOG_AVAILABLE)

        self._live_lbl  = QLabel("Live Sync")
        self._live_lbl.setObjectName("live_lbl")
        self._live_lbl.setVisible(WATCHDOG_AVAILABLE)

        sb.addWidget(self._status_lbl, 1)
        sb.addPermanentWidget(self._progress)
        sb.addPermanentWidget(self._live_dot)
        sb.addPermanentWidget(self._live_lbl)

    # ──────────────────────────────────────────────────────────────────────────
    #  THEMING
    # ──────────────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        T = self.T

        # Update icon colors
        self._rb_clear.setPixmap(Icons.trash(T["text_secondary"], 20))
        self._rb_detail.setPixmap(Icons.view_details(T["text_secondary"], 20))
        self._rb_icons.setPixmap(Icons.view_icons(T["text_secondary"], 20))
        self._rb_tree.setPixmap(Icons.view_tree(T["text_secondary"], 20))
        self._rb_theme.setPixmap(Icons.sun(20) if T.dark else Icons.moon(20))
        self._rb_theme._label = "Light" if T.dark else "Dark"

        # Nav buttons
        self._nav_back.setPixmap(Icons.arrow_left(T["text_secondary"]))
        self._nav_fwd.setPixmap(Icons.arrow_right(T["text_secondary"]))
        self._nav_up.setPixmap(Icons.arrow_up(T["text_secondary"]))
        self._nav_refresh.setPixmap(Icons.refresh(T["text_secondary"]))

        # Sidebar lists
        self.folder_list._theme = T
        self.folder_list.update_style()
        self.ignore_list._theme = T
        self.ignore_list.update_style()

        # Chips
        for btn in self._chips.values():
            btn._theme = T
            btn.update_style()

        # Delegate
        self._details.itemDelegate()._theme = T  # type: ignore

        # Search bar
        self._search_bar._theme = T
        self._search_bar.apply_input_style()
        self._search_bar.update_theme()

        # QSS
        acc  = T["accent"]
        qss = f"""
        /* ── App base ── */
        QMainWindow, QWidget {{
            background: {T['bg_base']};
            color: {T['text_primary']};
            font-family: 'Segoe UI', system-ui, sans-serif;
            font-size: 13px;
        }}

        /* ── Ribbon ── */
        QToolBar#ribbon_bar {{
            background: {T['bg_elevated']};
            border-bottom: 1px solid {T['border']};
            padding: 0;
            spacing: 0;
        }}

        /* ── Address row ── */
        QWidget#addr_row {{
            background: {T['bg_elevated']};
            border-bottom: 1px solid {T['border']};
        }}

        /* ── Filter row ── */
        QWidget#filter_row {{
            background: {T['bg_overlay']};
            border-bottom: 1px solid {T['border']};
        }}

        /* ── Add / scan buttons ── */
        QPushButton#add_btn {{
            background: {T['bg_control']};
            border: 1px solid {T['border']};
            border-radius: 4px;
            padding: 3px 10px;
            color: {T['text_secondary']};
            font-size: 12px;
        }}
        QPushButton#add_btn:hover {{
            background: {T['bg_control_hov']};
            color: {T['text_primary']};
        }}

        /* ── Sidebar ── */
        QFrame#sidebar_frame {{
            background: {T['sidebar_bg']};
            border-right: 1px solid {T['border']};
        }}
        QLabel#section_lbl {{
            color: {T['text_secondary']};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.8px;
            text-transform: uppercase;
        }}
        QFrame#sidebar_sep {{
            color: {T['border']};
            margin: 4px 10px;
        }}
        QPushButton#sidebar_action {{
            background: transparent;
            border: none;
            text-align: left;
            padding: 4px 12px;
            color: {acc};
            font-size: 12px;
        }}
        QPushButton#sidebar_action:hover {{
            color: {T['accent_hover']};
        }}

        /* ── Details view tree widget ── */
        QTreeWidget#details_view {{
            background: {T['bg_elevated']};
            alternate-background-color: {T['row_alt']};
            border: none;
            outline: none;
            show-decoration-selected: 1;
        }}
        QTreeWidget#details_view::item {{ border: none; }}
        QHeaderView::section {{
            background: {T['bg_overlay']};
            color: {T['text_secondary']};
            border: none;
            border-bottom: 1px solid {T['border']};
            border-right: 1px solid {T['border']};
            padding: 5px 8px;
            font-size: 12px;
            font-weight: 600;
        }}
        QHeaderView::section:hover {{
            background: {T['bg_control_hov']};
        }}

        /* ── Icons view ── */
        QListWidget#icons_view {{
            background: {T['bg_elevated']};
            border: none;
            outline: none;
        }}
        QListWidget#icons_view::item {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 5px;
            color: {T['text_primary']};
            padding: 4px;
        }}
        QListWidget#icons_view::item:hover {{
            background: {T['bg_control_hov']};
            border-color: {T['border']};
        }}
        QListWidget#icons_view::item:selected {{
            background: {T['sel_bg']};
            border-color: {acc};
            color: {'white' if T.dark else T['text_primary']};
        }}

        /* ── Tree view ── */
        QTreeWidget#tree_view {{
            background: {T['bg_elevated']};
            border: none;
            outline: none;
        }}
        QTreeWidget#tree_view::item {{
            padding: 3px 4px;
            color: {T['text_primary']};
        }}
        QTreeWidget#tree_view::item:hover  {{ background: {T['bg_control_hov']}; }}
        QTreeWidget#tree_view::item:selected {{ background: {T['sel_bg']};
            color: {'white' if T.dark else T['text_primary']}; }}

        /* ── Results panel ── */
        QWidget#results_panel {{ background: {T['bg_elevated']}; }}

        /* ── Status bar ── */
        QStatusBar#main_sb {{
            background: {T['bg_elevated']};
            border-top: 1px solid {T['border']};
            min-height: 24px;
        }}
        QLabel#status_lbl {{
            color: {T['text_secondary']};
            font-size: 12px;
            padding: 0 8px;
        }}
        QLabel#live_lbl {{
            color: {T['success']};
            font-size: 11px;
            padding: 0 6px;
        }}

        /* ── Progress bar ── */
        QProgressBar {{
            background: {T['border']};
            border: none;
            border-radius: 3px;
        }}
        QProgressBar::chunk {{
            background: {acc};
            border-radius: 3px;
        }}

        /* ── Splitter ── */
        QSplitter::handle {{ background: {T['border']}; }}

        /* ── Menus ── */
        QMenu {{
            background: {T['bg_elevated']};
            border: 1px solid {T['border_light']};
            border-radius: 8px;
            padding: 5px;
            color: {T['text_primary']};
        }}
        QMenu::item {{ padding: 6px 20px 6px 12px; border-radius: 4px; font-size: 13px; }}
        QMenu::item:selected {{ background: {acc}; color: white; }}
        QMenu::separator {{ height: 1px; background: {T['border']}; margin: 4px 0; }}

        /* ── Scrollbars ── */
        QScrollBar:vertical {{
            background: transparent; width: 6px; border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {T['border_light']}; border-radius: 3px; min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {T['text_secondary']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent; height: 6px; border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {T['border_light']}; border-radius: 3px; min-width: 24px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        /* ── Message boxes / dialogs ── */
        QMessageBox {{
            background: {T['bg_elevated']};
        }}
        QDialog {{
            background: {T['bg_elevated']};
        }}
        """
        self.setStyleSheet(qss)

        # Update text labels for action buttons
        self._btn_add_folder.setText("+ Add Folder")
        self._btn_scan.setText("Scan Drives")
        self._btn_add_ignore.setText("+ Add Rule")

        # Refresh pixmaps in ribbon widgets
        for w in [self._rb_index, self._rb_stop, self._rb_clear,
                  self._rb_theme, self._rb_detail, self._rb_icons, self._rb_tree]:
            w.update()

    # ──────────────────────────────────────────────────────────────────────────
    #  ICON HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _folder_icon(self, size=20) -> QIcon:
        key = f"folder_{size}"
        if key not in self._icon_cache:
            self._icon_cache[key] = QIcon(Icons.folder(self.T["icon_folder"], size))
        return self._icon_cache[key]

    def _file_icon(self, name: str, size=20) -> QIcon:
        _, ext = os.path.splitext(name)
        key = f"file_{ext}_{size}"
        if key not in self._icon_cache:
            self._icon_cache[key] = QIcon(Icons.file_by_ext(ext, size))
        return self._icon_cache[key]

    def _ext_type(self, path, is_dir):
        if is_dir: return "Folder"
        _, ext = os.path.splitext(path)
        return (ext.upper().lstrip(".") + " File") if ext else "File"

    # ──────────────────────────────────────────────────────────────────────────
    #  SETTINGS
    # ──────────────────────────────────────────────────────────────────────────

    def load_settings(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("SELECT path, last_indexed FROM folder_stats")
        stats = {r[0]: r[1] for r in c.fetchall()}

        c.execute("SELECT value FROM settings WHERE key='folders'")
        res = c.fetchone()
        if res:
            try:
                for f in json.loads(res[0]):
                    path  = f.get("path", "")
                    label = f.get("label", path)
                    state = f.get("state", "1")
                    item  = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, path)
                    item.setIcon(QIcon(Icons.folder(self.T["icon_folder"], 16)))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.CheckState.Checked if state == "1" else Qt.CheckState.Unchecked)
                    item.setToolTip(f"Path: {path}\nLast: {stats.get(path,'Never')}")
                    self.folder_list.addItem(item)
            except (json.JSONDecodeError, TypeError):
                pass

        # Ignore list defaults
        win_dir    = os.environ.get("SYSTEMROOT", "C:\\Windows")
        prog_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
        prog_x86   = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
        defaults = [
            "node_modules","venv",".venv","env","__pycache__",".git",".svn",
            ".idea",".vscode","dist","build","AppData","Local Settings",
            "System Volume Information","$RECYCLE.BIN",
            ".exe",".dll",".sys",".tmp",".pyc",
            win_dir, prog_files, prog_x86, "C:\\MSOCache","C:\\$Recycle.Bin",
        ]

        c.execute("SELECT value FROM settings WHERE key='ignore'")
        res = c.fetchone()
        current = {}
        if res:
            for raw in res[0].split("|"):
                if ":" in raw:
                    rule, st = raw.rsplit(":", 1); current[rule] = st
                elif raw: current[raw] = "1"
        for d in defaults:
            if d not in current: current[d] = "1"

        for rule in sorted(current.keys(), key=str.lower):
            item = QListWidgetItem(rule)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if current[rule] == "1" else Qt.CheckState.Unchecked)
            self.ignore_list.addItem(item)

        c.execute("SELECT value FROM settings WHERE key='theme'")
        res = c.fetchone()
        if res:
            self.T.dark = (res[0] == "dark")
            if not self.T.dark:
                self.T._t = Theme.LIGHT.copy()

        self.save_settings()
        conn.close()

    def save_settings(self, *_):
        folders = []
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            st   = "1" if item.checkState() == Qt.CheckState.Checked else "0"
            path = item.data(Qt.ItemDataRole.UserRole)
            folders.append({"path": path, "state": st, "label": item.text()})

        ignores = []
        for i in range(self.ignore_list.count()):
            item = self.ignore_list.item(i)
            st   = "1" if item.checkState() == Qt.CheckState.Checked else "0"
            ignores.append(f"{item.text()}:{st}")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", ("folders", json.dumps(folders)))
        c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", ("ignore",  "|".join(ignores)))
        c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)",
                  ("theme", "dark" if self.T.dark else "light"))
        conn.commit(); conn.close()

    # ──────────────────────────────────────────────────────────────────────────
    #  FOLDER MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def add_managed_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Folder to Index")
        if path:
            item = QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setIcon(QIcon(Icons.folder(self.T["icon_folder"], 16)))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(f"Path: {path}")
            self.folder_list.addItem(item)
            self.save_settings()

    def add_ignore_rule(self):
        rule, ok = QInputDialog.getText(
            self, "Add Ignore Rule",
            "Folder name, file name, or extension to ignore:")
        if ok and rule:
            item = QListWidgetItem(rule)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.ignore_list.addItem(item)
            self.save_settings()

    def scan_drives(self):
        try:
            import string
            from ctypes import windll
            bitmask = windll.kernel32.GetLogicalDrives()
            drives = [f"{l}:\\" for l in string.ascii_uppercase if bitmask & (1 << ord(l)-65)]
        except Exception:
            drives = ["/"]  # Linux fallback

        existing = [self.folder_list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.folder_list.count())]
        added = []
        for d in drives:
            if d not in existing:
                item = QListWidgetItem(d)
                item.setData(Qt.ItemDataRole.UserRole, d)
                item.setIcon(QIcon(Icons.drive(self.T["icon_file"], 16)))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.folder_list.addItem(item)
                added.append(d)
        if added:
            self.save_settings()
            QMessageBox.information(self, "Drives Found",
                f"Added: {', '.join(added)}")

    # ──────────────────────────────────────────────────────────────────────────
    #  INDEXING
    # ──────────────────────────────────────────────────────────────────────────

    def _get_checked_roots(self):
        return [
            (item.data(Qt.ItemDataRole.UserRole) or item.text())
            for i in range(self.folder_list.count())
            if (item := self.folder_list.item(i))
            and item.checkState() == Qt.CheckState.Checked
        ]

    def _get_checked_ignores(self):
        return [
            item.text()
            for i in range(self.ignore_list.count())
            if (item := self.ignore_list.item(i))
            and item.checkState() == Qt.CheckState.Checked
        ]

    def start_indexing(self, targets=None):
        roots   = targets or self._get_checked_roots()
        ignores = self._get_checked_ignores()
        if not roots:
            QMessageBox.warning(self, "No Folders",
                "Add at least one folder to index first.")
            return
        self._current_roots = roots
        self._rb_index.setVisible(False)
        self._rb_stop.setVisible(True)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._start_time = time.time()
        self.worker = IndexerWorker(roots, ignores)
        self.worker.progress.connect(self._on_index_progress)
        self.worker.finished.connect(self._on_index_done)
        self.worker.start()

    def stop_indexing(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
            self._status_lbl.setText("Stopping…")
            self._rb_stop.setEnabled(False)

    def _on_index_progress(self, count, msg):
        self._status_lbl.setText(f"Indexing… {count:,} items — {msg[:60]}")

    def _on_index_done(self, count):
        self._rb_index.setVisible(True)
        self._rb_stop.setVisible(False)
        self._rb_stop.setEnabled(True)
        self._progress.setVisible(False)

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for root in getattr(self, "_current_roots", []):
            c.execute("INSERT OR REPLACE INTO folder_stats VALUES(?,?)", (root, now_str))
        c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", ("last_indexed", now_str))
        conn.commit()
        c.execute("SELECT COUNT(*) FROM files")
        total = c.fetchone()[0]
        conn.close()

        self.update_stats()
        dur = time.time() - self._start_time
        if "--daemon" not in sys.argv and "--index" not in sys.argv:
            QMessageBox.information(self, "Indexing Complete",
                f"Done!\n\nProcessed:  {count:,} items\n"
                f"Duration:   {dur:.1f}s\n"
                f"Index size: {total:,} items\n"
                f"Completed:  {now_str}")

    def clear_index(self):
        if QMessageBox.question(self, "Clear Index",
                "Wipe the entire index cache?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM files")
            conn.commit(); conn.close()
            for w in [self._details, self._icons_view, self._tree_view]:
                w.clear()
            self.update_stats()

    def update_stats(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM files")
            count = c.fetchone()[0]
            c.execute("SELECT value FROM settings WHERE key='last_indexed'")
            res = c.fetchone()
            last = res[0] if res else "Never"
            conn.close()
            self._status_lbl.setText(
                f"{count:,} items indexed  ·  Last run: {last}")
        except Exception:
            self._status_lbl.setText("Ready")

    # ──────────────────────────────────────────────────────────────────────────
    #  SEARCH
    # ──────────────────────────────────────────────────────────────────────────

    def _on_search_changed(self, text):
        self.search_timer.start(120)

    def change_filter(self, ftype):
        self.filter_type = ftype
        self.perform_search()

    def set_view(self, mode):
        self.view_mode = mode
        self._stack.setCurrentIndex({"details":0,"icons":1,"tree":2}[mode])
        self.perform_search()

    def perform_search(self):
        query = self._search_bar.input.text().strip()

        if len(query) < 2:
            for w in [self._details, self._icons_view, self._tree_view]:
                w.clear()
            self._status_lbl.setText("Type at least 2 characters…")
            return

        terms = query.split()
        sel = self.folder_list.selectedItems()
        filter_paths = ([i.data(Qt.ItemDataRole.UserRole) for i in sel]
                        if sel else self._get_checked_roots())

        if not filter_paths and self.folder_list.count():
            for w in [self._details, self._icons_view, self._tree_view]:
                w.clear()
            self._status_lbl.setText("No folders checked.")
            return

        t0 = time.perf_counter()

        if self.filter_type == "content":
            results = [(r[0], r[1]) for r in
                       self.search_engine.search_content(
                           query_terms=terms, target_folders=filter_paths)]
        else:
            raw = self.search_engine.search_files(
                query_terms=terms, target_folders=filter_paths,
                files_only=(self.filter_type == "files"),
                folders_only=(self.filter_type == "folders"))
            results = [(r[0], r[1]) for r in raw]

        elapsed = (time.perf_counter() - t0) * 1000

        if self.view_mode == "details":
            self._fill_details(results)
        elif self.view_mode == "icons":
            self._fill_icons(results)
        else:
            self._fill_tree(results)

        self._status_lbl.setText(
            f"⚡  {len(results):,} results  in  {elapsed:.1f} ms")

    # ──────────────────────────────────────────────────────────────────────────
    #  POPULATORS
    # ──────────────────────────────────────────────────────────────────────────

    def _fill_details(self, results):
        tree = self._details
        tree.setUpdatesEnabled(False)
        tree.setSortingEnabled(False)
        tree.clear()
        for path, is_dir in results[:3000]:
            name  = os.path.basename(path) or path
            ttype = self._ext_type(path, is_dir)
            loc   = os.path.dirname(path)
            item  = QTreeWidgetItem([name, ttype, loc])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            icon  = self._folder_icon(20) if is_dir else self._file_icon(name, 20)
            item.setIcon(0, icon)
            item.setToolTip(0, path)
            item.setToolTip(2, loc)
            tree.addTopLevelItem(item)
        tree.setSortingEnabled(True)
        tree.setUpdatesEnabled(True)

    def _fill_icons(self, results):
        lw = self._icons_view
        lw.setUpdatesEnabled(False)
        lw.clear()
        for path, is_dir in results[:800]:
            name  = os.path.basename(path) or path
            short = name if len(name) <= 14 else name[:12] + "…"
            icon  = self._folder_icon(40) if is_dir else self._file_icon(name, 40)
            item  = QListWidgetItem(icon, short)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            lw.addItem(item)
        lw.setUpdatesEnabled(True)

    def _fill_tree(self, results):
        tree = self._tree_view
        tree.setUpdatesEnabled(False)
        tree.clear()
        nodes: dict[str, QTreeWidgetItem] = {}
        for path, is_dir in results[:1500]:
            parts = path.replace("\\", "/").split("/")
            parent = tree.invisibleRootItem()
            so_far = ""
            for i, part in enumerate(parts):
                sep = "/" if i < len(parts) - 1 else ""
                so_far += part + sep
                full = so_far.replace("/", "\\")
                if so_far in nodes:
                    parent = nodes[so_far]
                else:
                    folder = (i < len(parts) - 1) or is_dir
                    icon   = self._folder_icon(16) if folder else self._file_icon(part, 16)
                    new    = QTreeWidgetItem(parent, [part, full])
                    new.setData(0, Qt.ItemDataRole.UserRole, full)
                    new.setIcon(0, icon)
                    nodes[so_far] = new
                    parent = new
        tree.setUpdatesEnabled(True)

    # ──────────────────────────────────────────────────────────────────────────
    #  CONTEXT MENUS
    # ──────────────────────────────────────────────────────────────────────────

    def _ctx_details(self, pos):
        sel = self._details.selectedItems()
        if not sel: return
        paths = [i.data(0, Qt.ItemDataRole.UserRole) for i in sel if i.data(0, Qt.ItemDataRole.UserRole)]
        self._common_menu(pos, paths, self._details)

    def _ctx_icons(self, pos):
        sel = self._icons_view.selectedItems()
        if not sel: return
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in sel if i.data(Qt.ItemDataRole.UserRole)]
        self._common_menu(pos, paths, self._icons_view)

    def _ctx_tree(self, pos, widget):
        sel = widget.selectedItems()
        if not sel: return
        paths = [i.data(0, Qt.ItemDataRole.UserRole) for i in sel if i.data(0, Qt.ItemDataRole.UserRole)]
        self._common_menu(pos, paths, widget)

    def _common_menu(self, pos, paths, parent_widget):
        if not paths: return
        path = paths[0]
        menu = QMenu(self)
        open_a    = menu.addAction("Open")
        explore_a = menu.addAction("Show in Explorer")
        copy_a    = menu.addAction("Copy Path")
        menu.addSeparator()
        ops_a     = menu.addAction("Copy / Move / Delete…")
        arch_a = extr_a = None
        if len(paths) == 1 and is_archive(path):
            extr_a = menu.addAction("Extract Archive…")
        else:
            arch_a = menu.addAction("Compress to Archive…")

        action = menu.exec(parent_widget.mapToGlobal(pos))
        if action == open_a:
            for p in paths:
                self._open_path(p)
        elif action == explore_a:
            d = path if os.path.isdir(path) else os.path.dirname(path)
            if os.path.exists(d): os.startfile(d)
        elif action == copy_a:
            QApplication.clipboard().setText("\n".join(paths))
        elif action == ops_a:
            self.file_ops_win = FileOpsWindow()
            self.file_ops_win.source_paths = list(paths)
            self.file_ops_win._refresh_list()
            self.file_ops_win.show()
        elif (arch_a and action == arch_a) or (extr_a and action == extr_a):
            self.archiver_win = ArchiverWindow()
            self.archiver_win.source_paths = list(paths)
            self.archiver_win._refresh_list()
            self.archiver_win.show()

    def show_folder_ctx(self, pos):
        item = self.folder_list.itemAt(pos)
        if not item: return
        menu = QMenu(self)
        idx_a  = menu.addAction("Index This Folder Only")
        ren_a  = menu.addAction("Rename Label")
        rem_a  = menu.addAction("Remove")
        action = menu.exec(self.folder_list.mapToGlobal(pos))
        if action == idx_a:
            self.start_indexing(targets=[item.data(Qt.ItemDataRole.UserRole)])
        elif action == ren_a:
            new_name, ok = QInputDialog.getText(
                self, "Rename", "Label:", text=item.text())
            if ok and new_name:
                item.setText(new_name); self.save_settings()
        elif action == rem_a:
            self.folder_list.takeItem(self.folder_list.row(item))
            self.save_settings()

    def show_ignore_ctx(self, pos):
        item = self.ignore_list.itemAt(pos)
        if not item: return
        menu = QMenu(self)
        rem_a = menu.addAction("Remove Rule")
        if menu.exec(self.ignore_list.mapToGlobal(pos)) == rem_a:
            self.ignore_list.takeItem(self.ignore_list.row(item))
            self.save_settings()

    def _open_path(self, path):
        if not path: return
        if os.path.exists(path):
            os.startfile(path)
        else:
            QMessageBox.critical(self, "Not Found",
                "File or folder no longer exists or is unreachable.")

    # ──────────────────────────────────────────────────────────────────────────
    #  THEME TOGGLE
    # ──────────────────────────────────────────────────────────────────────────

    def toggle_theme(self):
        self.T.toggle()
        self._icon_cache.clear()
        self._apply_theme()
        self.save_settings()

    # ──────────────────────────────────────────────────────────────────────────
    #  KEYBOARD SHORTCUTS
    # ──────────────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key.Key_F
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            self._search_bar.input.setFocus()
            self._search_bar.input.selectAll()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._details.hasFocus():
                items = self._details.selectedItems()
                if items:
                    self._open_path(items[0].data(0, Qt.ItemDataRole.UserRole))
        super().keyPressEvent(event)

    # ──────────────────────────────────────────────────────────────────────────
    #  LIVE WATCHER
    # ──────────────────────────────────────────────────────────────────────────

    def start_live_watchers(self):
        if self.observer:
            self.observer.stop(); self.observer.join()
        active = [item.data(Qt.ItemDataRole.UserRole)
                  for i in range(self.folder_list.count())
                  if (item := self.folder_list.item(i))
                  and item.checkState() == Qt.CheckState.Checked
                  and item.data(Qt.ItemDataRole.UserRole)
                  and os.path.exists(item.data(Qt.ItemDataRole.UserRole))]
        if not active: return
        self.observer = Observer()
        handler = LiveCacheUpdater(self._get_checked_ignores())
        for f in active:
            with contextlib.suppress(Exception):
                self.observer.schedule(handler, f, recursive=True)
        self.observer.start()

    # ──────────────────────────────────────────────────────────────────────────
    #  DAEMON / CLI
    # ──────────────────────────────────────────────────────────────────────────

    def check_args(self):
        if "--index" in sys.argv or "--daemon" in sys.argv:
            self.hide()
            self.start_indexing()
            if "--daemon" not in sys.argv:
                self.worker.finished.connect(lambda: QApplication.quit())
            else:
                self.daemon_timer = QTimer()
                self.daemon_timer.timeout.connect(self.start_indexing)
                self.daemon_timer.start(3600000)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # High-DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Set Fusion palette to dark base so dialogs/menus inherit correctly
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#1c1c1c"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#f3f3f3"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#252525"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#202020"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#f3f3f3"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#2d2d2d"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#f3f3f3"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#0078d4"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

    window = XExplorer()
    if "--no-ui" not in sys.argv and "--daemon" not in sys.argv and "--index" not in sys.argv:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
