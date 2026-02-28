"""Auto-split module."""

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap


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
        p.drawRoundedRect(1, int(s * 0.38), s - 2, int(s * 0.52), 3, 3)
        # Top tab
        p.setBrush(QBrush(c))
        p.drawRoundedRect(1, int(s * 0.22), int(s * 0.45), int(s * 0.22), 2, 2)
        # Front face
        p.setBrush(QBrush(c))
        p.drawRoundedRect(1, int(s * 0.34), s - 2, int(s * 0.5), 3, 3)
        # Highlight line
        p.setBrush(QBrush(c.lighter(130)))
        p.drawRoundedRect(3, int(s * 0.36), s - 6, int(s * 0.08), 1, 1)
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
        for i, y in enumerate(range(int(s * 0.5), int(s * 0.82), int(s * 0.12))):
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
        p.drawRoundedRect(2, 4, s - 4, s - 8, 3, 3)
        # LED dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#4caf74")))
        p.drawEllipse(s - 9, s - 9, 4, 4)
        # Slot
        p.setPen(QPen(c.darker(150), 1))
        p.drawLine(4, s - 8, s - 10, s - 8)
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
        cx = 1 + r // 2
        cy = 1 + r // 2
        edge = int(r * 0.7)
        p.drawLine(cx + edge // 2, cy + edge // 2, s - 2, s - 2)
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
        p.drawArc(QRectF(2, 2, s - 4, s - 4), 30 * 16, 300 * 16)
        # Arrow head
        p.setPen(QPen(QColor(color), 1.5))
        p.drawLine(s - 4, 3, s - 4, 7)
        p.drawLine(s - 4, 3, s - 8, 3)
        p.end()
        return px

    @staticmethod
    def index_bolt(color="#f0c040", size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        c = QColor(color)
        path = QPainterPath()
        path.moveTo(s * 0.6, 1)
        path.lineTo(s * 0.2, s * 0.5)
        path.lineTo(s * 0.5, s * 0.5)
        path.lineTo(s * 0.35, s - 1)
        path.lineTo(s * 0.8, s * 0.45)
        path.lineTo(s * 0.5, s * 0.45)
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
        p.drawLine(3, 5, s - 3, 5)
        p.drawLine(7, 5, 7, 3)
        p.drawLine(s - 7, 5, s - 7, 3)
        p.drawLine(7, 3, s - 7, 3)
        # Body
        body = QPainterPath()
        body.moveTo(4, 6)
        body.lineTo(5, s - 1)
        body.lineTo(s - 5, s - 1)
        body.lineTo(s - 4, 6)
        p.drawPath(body)
        # Lines inside
        mid = s // 2
        p.drawLine(mid, 8, mid, s - 3)
        p.drawLine(mid - 3, 8, mid - 3, s - 3)
        p.drawLine(mid + 3, 8, mid + 3, s - 3)
        p.end()
        return px

    @staticmethod
    def stop_circle(size=20) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        p.setPen(QPen(QColor("#f47174"), 1.5))
        p.setBrush(QBrush(QColor("#f4717430")))
        p.drawEllipse(QRectF(2, 2, s - 4, s - 4))
        p.setPen(QPen(QColor("#f47174"), 2))
        p.drawLine(s // 2 - 3, s // 2 - 3, s // 2 + 3, s // 2 + 3)
        p.drawLine(s // 2 + 3, s // 2 - 3, s // 2 - 3, s // 2 + 3)
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
        p.setPen(QPen(QColor("#ababab"), 1.2))
        p.setBrush(QBrush(QColor("#ababab")))
        path = QPainterPath()
        path.moveTo(s * 0.7, s * 0.15)
        path.arcTo(QRectF(s * 0.1, s * 0.1, s * 0.7, s * 0.7), 60, -220)
        path.arcTo(QRectF(s * 0.3, s * 0.05, s * 0.6, s * 0.8), -90, 150)
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
            p.drawLine(2, y, s - 2, y)
        p.end()
        return px

    @staticmethod
    def view_icons(color="#ababab", size=20) -> QPixmap:
        px, p = Icons._base(size)
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
        p.drawLine(4, 4, 4, s - 4)
        p.drawLine(4, 4, s - 2, 4)
        p.drawLine(4, 10, s - 2, 10)
        p.drawLine(4, 16, s - 2, 16)
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
        p.drawRoundedRect(1, int(s * 0.34), s - 2, int(s * 0.5), 2, 2)
        p.setBrush(QBrush(QColor("#dcb967").darker(140)))
        p.drawRoundedRect(1, int(s * 0.38), s - 2, int(s * 0.46), 2, 2)
        p.setBrush(QBrush(QColor("#dcb967")))
        p.drawRoundedRect(1, int(s * 0.34), s - 2, int(s * 0.5), 2, 2)
        p.drawRoundedRect(1, int(s * 0.22), int(s * 0.38), int(s * 0.18), 1, 1)
        # Plus badge
        p.setBrush(QBrush(c))
        p.drawEllipse(s - 8, s - 8, 8, 8)
        pen = QPen(QColor("white"), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(s - 4, s - 7, s - 4, s - 1)
        p.drawLine(s - 7, s - 4, s - 1, s - 4)
        p.end()
        return px

    @staticmethod
    def live_dot(size=10) -> QPixmap:
        px, p = Icons._base(size)
        s = size
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#4caf74")))
        p.drawEllipse(1, 1, s - 2, s - 2)
        p.end()
        return px

    @staticmethod
    def file_by_ext(ext: str, size=20) -> QPixmap:
        ext = ext.lower()
        CODE = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".html",
            ".css",
            ".cpp",
            ".c",
            ".h",
            ".java",
            ".cs",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".sh",
            ".bash",
            ".kt",
            ".swift",
            ".vue",
            ".json",
            ".xml",
            ".yaml",
            ".yml",
            ".toml",
        }
        MEDIA = {
            ".mp3",
            ".wav",
            ".flac",
            ".ogg",
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".gif",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".svg",
            ".bmp",
            ".ico",
            ".tiff",
        }
        ARCH = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".dmg", ".iso"}
        DOC = {
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".odt",
            ".ods",
            ".odp",
            ".txt",
            ".md",
            ".rtf",
            ".csv",
        }
        EXE = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".app"}

        if ext in CODE:
            # Color code by language
            lang_colors = {
                ".py": "#3572A5",
                ".js": "#f0d050",
                ".ts": "#2d79c7",
                ".jsx": "#61dafb",
                ".tsx": "#61dafb",
                ".html": "#e44d26",
                ".css": "#264de4",
                ".cpp": "#659ad2",
                ".c": "#555555",
                ".java": "#b07219",
                ".cs": "#178600",
                ".go": "#00acd7",
                ".rs": "#dea584",
                ".rb": "#cc342d",
                ".sh": "#89e051",
                ".kt": "#a97bff",
                ".swift": "#f05138",
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
            font = QFont("Segoe UI", max(4, size // 5), QFont.Weight.Bold)
            p.setFont(font)
            p.setPen(QPen(QColor(color)))
            label = ext.lstrip(".")[:3].upper()
            p.drawText(
                QRect(1, int(s * 0.55), s - 2, int(s * 0.4)),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )
            p.end()
            return px

        elif ext in MEDIA:
            return Icons.file_generic("#c8a0e8", size)
        elif ext in ARCH:
            return Icons.file_generic("#e8b870", size)
        elif ext in DOC:
            doc_colors = {
                ".pdf": "#e84040",
                ".doc": "#2b5eb5",
                ".docx": "#2b5eb5",
                ".xls": "#1e7e45",
                ".xlsx": "#1e7e45",
                ".ppt": "#c04a20",
                ".pptx": "#c04a20",
            }
            return Icons.file_generic(doc_colors.get(ext, "#9db8d2"), size)
        elif ext in EXE:
            return Icons.file_generic("#a0a0a0", size)
        else:
            return Icons.file_generic("#9db8d2", size)
