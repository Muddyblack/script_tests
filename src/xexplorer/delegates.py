"""Auto-split module."""


from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

from src.xexplorer.theme import Theme


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


