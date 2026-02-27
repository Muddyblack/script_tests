"""Desktop snip-to-text (OCR) for Windows — v3."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QMimeData,
    QObject,
    QPoint,
    QRect,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QClipboard,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QRegion,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Recent snips history (module-level, persists within a process session)
# ---------------------------------------------------------------------------


@dataclass
class _SnipRecord:
    timestamp: datetime
    text: str
    image: QImage


_recent_snips: deque[_SnipRecord] = deque(maxlen=10)


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------


def _capture_virtual_desktop() -> tuple[QPixmap, QRect]:
    """Capture all screens into one stitched pixmap BEFORE the overlay appears."""
    screens = QGuiApplication.screens()
    if not screens:
        raise RuntimeError("No screens detected")

    virtual_geo = screens[0].virtualGeometry()
    canvas = QPixmap(virtual_geo.size())
    canvas.fill(Qt.GlobalColor.black)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for screen in screens:
        geo = screen.geometry()
        shot = screen.grabWindow(0)
        painter.drawPixmap(
            geo.x() - virtual_geo.x(),
            geo.y() - virtual_geo.y(),
            geo.width(),
            geo.height(),
            shot,
        )
    painter.end()
    return canvas, virtual_geo


# ---------------------------------------------------------------------------
# Image preprocessing — multi-pass with color channel separation
# ---------------------------------------------------------------------------


def _scale_factor_for(image: QImage) -> int:
    """Larger upscale for tiny snips where letter-spacing errors dominate."""
    w = image.width()
    if w < 150:
        return 6
    if w < 400:
        return 4
    return 3


def _extract_channel_buf(image: QImage, channel: str) -> bytearray:
    """Extract a single R/G/B channel as a flat grayscale bytearray."""
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = rgba.bits()
    ptr.setsize(rgba.sizeInBytes())
    raw = bytes(ptr)
    offset = {"R": 0, "G": 1, "B": 2}[channel]
    w, h = rgba.width(), rgba.height()
    return bytearray(raw[i * 4 + offset] for i in range(w * h))


def _stretch_contrast(buf: bytearray) -> bytearray:
    mn, mx = min(buf), max(buf)
    rng = mx - mn or 1
    return bytearray(int((v - mn) * 255 / rng) for v in buf)


def _binarize(buf: bytearray, threshold: int, invert: bool) -> bytearray:
    if invert:
        return bytearray(255 if v < threshold else 0 for v in buf)
    return bytearray(0 if v < threshold else 255 for v in buf)


def _buf_to_qimage(buf: bytearray, w: int, h: int) -> QImage:
    img = QImage(bytes(buf), w, h, w, QImage.Format.Format_Grayscale8)
    return img.convertToFormat(QImage.Format.Format_RGBA8888)


def _preprocess_candidates(image: QImage) -> list[QImage]:
    """
    Generate multiple binarized variants of the image for OCR.

    We try:
      - Luma grayscale at thresholds 100 / 128 / 155 / 180, normal + inverted
      - R, G, B channels individually at threshold 128, normal + inverted

    Prioritises inverted variants for dark-background UIs (VS Code, terminals).
    This directly fixes the midnight-marina / colored-filename problem where
    standard luma grayscale loses contrast on teal/blue/green text.
    """
    factor = _scale_factor_for(image)
    scaled = image.scaled(
        image.width() * factor,
        image.height() * factor,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    w, h = scaled.width(), scaled.height()

    # --- Luma grayscale variants ---
    gray_img = scaled.convertToFormat(QImage.Format.Format_Grayscale8)
    ptr = gray_img.bits()
    ptr.setsize(gray_img.sizeInBytes())
    luma = _stretch_contrast(bytearray(ptr))

    dark_count = sum(1 for v in luma if v < 128)
    is_dark_bg = dark_count > (w * h) * 0.5

    luma_candidates: list[QImage] = []
    for t in (100, 128, 155, 180):
        luma_candidates.append(_buf_to_qimage(_binarize(luma, t, invert=False), w, h))
        luma_candidates.append(_buf_to_qimage(_binarize(luma, t, invert=True), w, h))

    # If dark background, put inverted variants first (better for dark themes)
    if is_dark_bg:
        inverted = luma_candidates[1::2]
        normal = luma_candidates[0::2]
        luma_candidates = inverted + normal

    # --- Per-channel variants (key for colored filename text) ---
    channel_candidates: list[QImage] = []
    for ch in ("R", "G", "B"):
        ch_buf = _stretch_contrast(_extract_channel_buf(scaled, ch))
        for inv in (True, False) if is_dark_bg else (False, True):
            channel_candidates.append(_buf_to_qimage(_binarize(ch_buf, 128, inv), w, h))

    return luma_candidates + channel_candidates


# ---------------------------------------------------------------------------
# OCR post-processing
# ---------------------------------------------------------------------------

_CHAR_FIXES: list[tuple[str, str]] = [
    (r"[\u2018\u2019\u0060]", "'"),  # curly/backtick → straight apos
    (r"[\u201c\u201d]", '"'),  # curly doubles
    (r"[\u2013\u2014\u2212]", "-"),  # en/em/minus → hyphen
    (r"[\u00b7\u2022\u25cf\u25e6]", "*"),  # bullets
    (r"\u2026", "..."),  # ellipsis
    (r"\bO(?=\d)", "0"),  # O before digit
    (r"(?<=\d)O\b", "0"),  # digit then O
    (r"(?<=\d)o(?=\d)", "0"),  # digit-o-digit
    (r"(\w)-\n(\w)", r"\1\2"),  # line-wrap hyphen removal
    (r"(?<![.\w])[lI](?=[=({<>!&|+\-])", "1"),  # isolated l/I before operator
]
_CHAR_RE = [(re.compile(p), r) for p, r in _CHAR_FIXES]

# rn → m fusion: the single biggest accuracy win for VS Code / IDE UIs
# Only fuse when 'rn' is surrounded by identifier characters (not at word edges
# next to digits, spaces, or punctuation that would make rn legitimate).
_RN_RE = re.compile(
    r"(?<=[a-zA-Z_\-\.])rn(?=[a-zA-Z_\-\.])"  # rn inside identifier
    r"|(?<=\s)rn(?=[a-z])"  # rn starting a lowercase word
)

# Filename/path-specific fixes applied only when content looks like a file tree
_PATH_FIXES: list[tuple[str, str]] = [
    (r"(?<=[a-z])\*(?=[a-z])", "i"),  # m*dnight → midnight  (* was dotted-i)
    (r"(?<=\w)\$(?=\w)", "s"),  # $ ≈ s at very small sizes
]
_PATH_RE = [(re.compile(p), r) for p, r in _PATH_FIXES]


def _looks_like_filepath_content(text: str) -> bool:
    lines = text.strip().splitlines()
    if not lines:
        return False
    hits = sum(1 for ln in lines if re.search(r"[\./\\]", ln))
    return hits > len(lines) * 0.35


def _postprocess_text(text: str, *, filepath_mode: bool = False) -> str:
    for rx, repl in _CHAR_RE:
        text = rx.sub(repl, text)
    text = _RN_RE.sub("m", text)
    if filepath_mode:
        for rx, repl in _PATH_RE:
            text = rx.sub(repl, text)
    return text.strip()


# ---------------------------------------------------------------------------
# WinRT OCR — multi-candidate engine
# ---------------------------------------------------------------------------


def _qimage_to_rgba_bytes(image: QImage) -> tuple[bytes, int, int]:
    img = image.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())
    return bytes(ptr), img.width(), img.height()


async def _get_engine():
    try:
        from winsdk.windows.media.ocr import OcrEngine
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency. Install with:  python -m pip install winsdk"
        ) from exc
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        langs = OcrEngine.get_available_recognizer_languages()
        if langs:
            engine = OcrEngine.try_create_from_language(langs[0])
    if engine is None:
        raise RuntimeError(
            "Windows OCR engine unavailable — install a language pack with OCR support."
        )
    return engine


async def _ocr_one(engine, rgba: bytes, w: int, h: int) -> tuple[str, int]:
    import winsdk.windows.storage.streams as streams
    from winsdk.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap

    writer = streams.DataWriter()
    writer.write_bytes(rgba)
    bmp = SoftwareBitmap(BitmapPixelFormat.RGBA8, w, h)
    bmp.copy_from_buffer(writer.detach_buffer())
    result = await engine.recognize_async(bmp)
    if not result or not result.lines:
        return "", 0
    lines = [ln.text for ln in result.lines]
    return "\n".join(lines).strip(), len(lines)


async def _ocr_best(candidates: list[QImage]) -> str:
    """
    Run OCR on every candidate image; return the result with the most lines.
    More detected lines = more structure recognised = better read.
    """
    engine = await _get_engine()
    best_text, best_n = "", 0
    for img in candidates:
        rgba, w, h = _qimage_to_rgba_bytes(img)
        text, n = await _ocr_one(engine, rgba, w, h)
        if n > best_n:
            best_n, best_text = n, text
    return best_text


def ocr_qimage(image: QImage) -> str:
    """Run multi-pass preprocessing + best-candidate OCR. Fully offline."""
    candidates = _preprocess_candidates(image)
    raw = asyncio.run(_ocr_best(candidates))
    fp_mode = _looks_like_filepath_content(raw)
    return _postprocess_text(raw, filepath_mode=fp_mode)


# ---------------------------------------------------------------------------
# Snip overlay with magnifier loupe
# ---------------------------------------------------------------------------

_LOUPE_PX = 128  # loupe display size in pixels
_LOUPE_ZOOM = 3  # zoom factor


class SnipOverlay(QWidget):
    snip_taken = pyqtSignal(QRect)
    snip_cancelled = pyqtSignal()

    def __init__(self, desktop: QPixmap, virtual_geo: QRect):
        super().__init__()
        self._desktop = desktop
        self._virtual_geo = virtual_geo

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(virtual_geo)

        self._dragging = False
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._mouse: QPoint = QPoint(0, 0)

    def _sel_rect(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.snip_cancelled.emit()
            self.close()
        else:
            super().keyPressEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._origin = ev.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, ev):
        self._mouse = ev.position().toPoint()
        if self._dragging:
            self._current = self._mouse
        self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._current = ev.position().toPoint()
            rect = self._sel_rect()
            if rect.width() < 4 or rect.height() < 4:
                self.snip_cancelled.emit()
            else:
                self.snip_taken.emit(rect)
            self.close()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        p.drawPixmap(0, 0, self._desktop)
        p.fillRect(self.rect(), QColor(0, 0, 0, 115))

        rect = self._sel_rect()
        if not rect.isNull():
            # Reveal selection through the dim overlay
            p.save()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(rect, Qt.GlobalColor.transparent)
            p.restore()

            # Border
            pen = QPen(QColor(59, 130, 246, 230))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rect)

            # Corner handles
            p.setBrush(QColor(255, 255, 255, 220))
            p.setPen(Qt.PenStyle.NoPen)
            hs = 6
            for cx, cy in [
                (rect.left(), rect.top()),
                (rect.right(), rect.top()),
                (rect.left(), rect.bottom()),
                (rect.right(), rect.bottom()),
            ]:
                p.drawRect(cx - hs // 2, cy - hs // 2, hs, hs)

            # Size badge
            badge = f"  {rect.width()} × {rect.height()} px  "
            p.setFont(QFont("Segoe UI", 9))
            fm = QFontMetrics(p.font())
            bw, bh = fm.horizontalAdvance(badge) + 4, fm.height() + 6
            bx = max(rect.left(), rect.right() - bw)
            by = rect.bottom() + 4
            p.setBrush(QColor(0, 0, 0, 170))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bx, by, bw, bh, 4, 4)
            p.setPen(QColor(255, 255, 255, 210))
            p.drawText(bx + 2, by + fm.ascent() + 3, badge)

        # Loupe — only when not dragging
        if not self._dragging:
            self._draw_loupe(p, self._mouse)

        # Instruction bar
        p.fillRect(QRect(0, 0, self.width(), 44), QColor(0, 0, 0, 150))
        p.setPen(QColor(255, 255, 255, 200))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(
            16,
            28,
            "Drag to select  •  Esc to cancel  •  Release for action menu  [1–6]",
        )
        p.end()

    def _draw_loupe(self, p: QPainter, pos: QPoint) -> None:
        ls, zoom = _LOUPE_PX, _LOUPE_ZOOM
        src_sz = ls // zoom
        src = QRect(pos.x() - src_sz // 2, pos.y() - src_sz // 2, src_sz, src_sz)
        lx = pos.x() + 20
        ly = pos.y() + 20
        if lx + ls > self.width():
            lx = pos.x() - ls - 20
        if ly + ls > self.height():
            ly = pos.y() - ls - 20
        dst = QRect(lx, ly, ls, ls)

        p.save()
        p.setClipRegion(QRegion(dst, QRegion.RegionType.Ellipse))
        p.drawPixmap(dst, self._desktop, src)
        p.restore()

        pen = QPen(QColor(255, 255, 255, 180))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(dst)

        # Crosshair
        cx, cy = lx + ls // 2, ly + ls // 2
        cp = QPen(QColor(59, 130, 246, 200))
        cp.setWidth(1)
        p.setPen(cp)
        p.drawLine(cx - 10, cy, cx + 10, cy)
        p.drawLine(cx, cy - 10, cx, cy + 10)

    def crop_selection(self, rect: QRect) -> QImage:
        return self._desktop.copy(rect).toImage()


# ---------------------------------------------------------------------------
# Action menu
# ---------------------------------------------------------------------------


class ActionMenu(QWidget):
    action_chosen = pyqtSignal(str)

    _ACTIONS = [
        ("1", "📋  Copy Text", "text", "#3b82f6"),
        ("2", "🖼️  Copy Image", "image", "#8b5cf6"),
        ("3", "📑  Copy Both", "both", "#06b6d4"),
        ("4", "💾  Save Image…", "save", "#10b981"),
        ("5", "⌨️  Insert Text", "insert", "#f59e0b"),
        ("6", "📝  Open in Editor", "editor", "#ec4899"),
    ]

    def __init__(self, anchor: QPoint):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        title = QLabel("  Snip Action  •  Esc to dismiss")
        title.setStyleSheet(
            "color: rgba(255,255,255,0.45); font: 8pt 'Segoe UI'; padding-bottom:3px;"
        )
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.08);")
        layout.addWidget(sep)

        self._buttons: dict[str, QPushButton] = {}
        for num, label, key, color in self._ACTIONS:
            btn = QPushButton(f"[{num}]  {label}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(22,22,34,0.97);
                    color: rgba(255,255,255,0.88);
                    border: 1px solid rgba(255,255,255,0.09);
                    border-radius: 6px;
                    padding: 7px 18px 7px 12px;
                    font: 10pt 'Segoe UI';
                    text-align: left;
                    min-width: 195px;
                }}
                QPushButton:hover, QPushButton:focus {{
                    background: {color};
                    border-color: {color};
                    color: white;
                    outline: none;
                }}
            """)
            _k = key
            btn.clicked.connect(lambda _, k=_k: self._emit(k))
            layout.addWidget(btn)
            self._buttons[num] = btn

        self.setStyleSheet("""
            QWidget {
                background: rgba(16,16,26,0.97);
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,0.07);
            }
        """)
        self.adjustSize()

        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        sg = screen.geometry()
        x = min(anchor.x() + 14, sg.right() - self.width() - 8)
        y = min(anchor.y() + 14, sg.bottom() - self.height() - 8)
        self.move(x, y)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._emit("cancel"))
        self._timer.start(30_000)

    def _emit(self, key: str) -> None:
        self._timer.stop()
        self.action_chosen.emit(key)
        self.close()

    def keyPressEvent(self, ev):
        k = ev.text()
        if k in self._buttons:
            self._buttons[k].click()
        elif ev.key() == Qt.Key.Key_Escape:
            self._emit("cancel")
        else:
            super().keyPressEvent(ev)


# ---------------------------------------------------------------------------
# OCR preview tooltip
# ---------------------------------------------------------------------------


class OcrPreviewTooltip(QWidget):
    def __init__(self, anchor: QPoint):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self._lbl = QLabel("⏳ Recognising…")
        self._lbl.setWordWrap(True)
        self._lbl.setMaximumWidth(320)
        self._lbl.setStyleSheet("color: rgba(255,255,255,0.88); font: 9pt 'Consolas';")
        layout.addWidget(self._lbl)
        self.setStyleSheet("""
            QWidget {
                background: rgba(8,8,18,0.93);
                border-radius: 7px;
                border: 1px solid rgba(59,130,246,0.35);
            }
        """)
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        sg = screen.geometry()
        self.adjustSize()
        x = min(anchor.x(), sg.right() - self.width() - 8)
        y = max(anchor.y() - self.height() - 10, sg.top() + 8)
        self.move(x, y)

    def set_text(self, text: str) -> None:
        preview = text[:100].replace("\n", " ↵ ")
        if len(text) > 100:
            preview += " …"
        self._lbl.setText(preview or "⚠️ No text detected")
        self.adjustSize()
        QTimer.singleShot(4000, self.close)


# ---------------------------------------------------------------------------
# OCR worker
# ---------------------------------------------------------------------------


class _Signals(QObject):
    success = pyqtSignal(str)
    error = pyqtSignal(str)


class _OcrWorker(QRunnable):
    def __init__(self, image: QImage):
        super().__init__()
        self.image = image
        self.signals = _Signals()

    def run(self):
        try:
            self.signals.success.emit(ocr_qimage(self.image))
        except Exception as e:
            self.signals.error.emit(str(e).strip() or e.__class__.__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _copy_text(text: str) -> None:
    mime = QMimeData()
    mime.setText(text)
    QApplication.clipboard().setMimeData(mime, QClipboard.Mode.Clipboard)


def _copy_image(image: QImage) -> None:
    mime = QMimeData()
    mime.setImageData(image)
    QApplication.clipboard().setMimeData(mime, QClipboard.Mode.Clipboard)


def _save_image_dialog(image: QImage) -> str | None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default = str(Path.home() / "Pictures" / f"snip_{ts}.png")
    path, _ = QFileDialog.getSaveFileName(
        None, "Save Snip", default, "PNG Image (*.png);;JPEG Image (*.jpg)"
    )
    if path:
        image.save(path)
        return path
    return None


def _open_in_editor(text: str) -> None:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="snip_", delete=False, encoding="utf-8"
    )
    tmp.write(text)
    tmp.close()
    os.startfile(tmp.name)


def _insert_at_cursor(text: str) -> None:
    """Copy to clipboard then SendInput Ctrl+V into previously focused window."""
    _copy_text(text)
    time.sleep(0.15)
    import ctypes

    VK_CTRL, VK_V, KEY_UP = 0x11, 0x56, 0x0002

    class KBI(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INP(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ki", KBI), ("pad", ctypes.c_ubyte * 8)]

    def mk(vk, flags=0):
        i = INP()
        i.type = 1
        i.ki.wVk = vk
        i.ki.dwFlags = flags
        return i

    seq = (INP * 4)(mk(VK_CTRL), mk(VK_V), mk(VK_V, KEY_UP), mk(VK_CTRL, KEY_UP))
    ctypes.windll.user32.SendInput(4, seq, ctypes.sizeof(INP))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnipResult:
    text: str
    image: QImage
    action: str


def start_snip_to_text(
    *,
    nexus=None,
    on_done: Callable[[SnipResult], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    """
    Start the snip → action-menu → OCR/action flow inside an existing Qt app.
    Recommended shortcut:  Alt+Shift+S
    """

    def _status(msg: str) -> None:
        if nexus is not None and hasattr(nexus, "status_lbl"):
            nexus.status_lbl.setText(msg)
            nexus.status_lbl.repaint()

    def _tray(msg: str) -> None:
        if nexus is not None and getattr(nexus, "tray", None) is not None:
            nexus.tray.showMessage("Snip", msg)

    def _pool() -> QThreadPool:
        if nexus is not None and hasattr(nexus, "thread_pool"):
            return nexus.thread_pool
        return QThreadPool.globalInstance()

    def _handle(action: str, image: QImage, anchor: QPoint) -> None:
        if action == "cancel":
            _status("Snip cancelled")
            return

        if action == "image":
            _copy_image(image)
            _status("✓ Image copied")
            _tray("Image copied to clipboard")
            if on_done:
                on_done(SnipResult("", image, action))
            return

        if action == "save":
            path = _save_image_dialog(image)
            if path:
                _status(f"✓ Saved → {Path(path).name}")
                _tray(f"Saved: {Path(path).name}")
                _recent_snips.appendleft(_SnipRecord(datetime.now(), "", image))
                if on_done:
                    on_done(SnipResult("", image, action))
            else:
                _status("Save cancelled")
            return

        _status("⏳ Recognising text…")
        tip = OcrPreviewTooltip(anchor)
        tip.show()

        w = _OcrWorker(image)

        def _ok(text: str) -> None:
            tip.set_text(text)
            if not text:
                _status("⚠️ No text detected")
                _tray("No text detected")
                if on_error:
                    on_error("No text detected")
                return
            _recent_snips.appendleft(_SnipRecord(datetime.now(), text, image))
            if action == "text":
                _copy_text(text)
                _status("✓ Text copied")
                _tray("Text copied")
            elif action == "both":
                _copy_text(text)
                _copy_image(image)
                _status("✓ Text & image copied")
                _tray("Text & image copied")
            elif action == "insert":
                _insert_at_cursor(text)
                _status("✓ Text inserted")
                _tray("Text inserted")
            elif action == "editor":
                _open_in_editor(text)
                _status("✓ Opened in editor")
                _tray("Opened in editor")
            if on_done:
                on_done(SnipResult(text, image, action))

        def _err(err: str) -> None:
            tip.close()
            _status(f"❌ {err}")
            _tray(f"Error: {err}")
            if on_error:
                on_error(err)

        w.signals.success.connect(_ok)
        w.signals.error.connect(_err)
        _pool().start(w)

    def _show_menu(image: QImage, rect: QRect) -> None:
        screens = QGuiApplication.screens()
        vgeo = screens[0].virtualGeometry() if screens else QRect()
        anchor = QPoint(rect.right() + vgeo.x(), rect.bottom() + vgeo.y())
        menu = ActionMenu(anchor)
        menu.action_chosen.connect(lambda a: _handle(a, image, anchor))
        menu.show()
        menu.raise_()
        menu.activateWindow()
        menu.setFocus()
        menu._alive = menu  # prevent GC

    def _on_taken(rect: QRect, overlay: SnipOverlay) -> None:
        image = overlay.crop_selection(rect)
        QTimer.singleShot(60, lambda: _show_menu(image, rect))

    def _start_overlay(desktop: QPixmap, vgeo: QRect) -> None:
        ov = SnipOverlay(desktop, vgeo)
        ov.snip_cancelled.connect(lambda: _status("Snip cancelled"))
        ov.snip_taken.connect(lambda r: _on_taken(r, ov))
        ov.show()
        ov.raise_()
        ov.activateWindow()

    def _capture() -> None:
        try:
            desktop, vgeo = _capture_virtual_desktop()
        except Exception as e:
            _status(f"❌ Capture error: {e}")
            if on_error:
                on_error(str(e))
            return
        QTimer.singleShot(30, lambda: _start_overlay(desktop, vgeo))

    if nexus is not None and hasattr(nexus, "hide"):
        nexus.hide()

    QTimer.singleShot(80, _capture)


# ---------------------------------------------------------------------------
# Utility: access history from other modules
# ---------------------------------------------------------------------------


def get_recent_snips() -> list[_SnipRecord]:
    """Return up to the last 10 snip records (newest first)."""
    return list(_recent_snips)
