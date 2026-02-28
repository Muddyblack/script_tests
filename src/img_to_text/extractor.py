"""OCR extraction — persistent subprocess to avoid Qt/torch DLL conflicts and model reloads."""

from __future__ import annotations

import atexit
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QImage

_WORKER = Path(__file__).parent / "ocr_worker.py"

_proc: subprocess.Popen | None = None
_proc_languages: list[str] = []


def _get_proc(languages: list[str]) -> subprocess.Popen:
    global _proc, _proc_languages

    if _proc is not None and _proc.poll() is not None:
        _proc = None  # died, restart

    if _proc is None or languages != _proc_languages:
        if _proc is not None:
            _proc.stdin.close()
            _proc.wait()
        _proc = subprocess.Popen(
            [sys.executable, "-u", str(_WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _proc.stdin.write(",".join(languages) + "\n")
        _proc.stdin.flush()
        # Wait for "ready"
        _proc.stdout.readline()
        _proc_languages = languages

    return _proc


@atexit.register
def _shutdown():
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.stdin.close()
        _proc.wait()


def _run_ocr(image: QImage, languages: list[str]) -> list[dict]:
    if image.isNull():
        return []

    buf = QByteArray()
    qbuf = QBuffer(buf)
    qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = image.save(qbuf, "PNG")
    qbuf.close()

    if not ok or buf.isEmpty():
        raise RuntimeError("Failed to encode QImage to PNG")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(bytes(buf))
        tmp_path = f.name

    try:
        proc = _get_proc(languages)
        proc.stdin.write(tmp_path + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not line:
        raise RuntimeError("OCR worker died unexpectedly")

    data = json.loads(line)
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("results", [])


def ocr_qimage(image: QImage, languages: list[str] | None = None) -> str:
    results = _run_ocr(image, languages or ["en", "de", "fr"])
    return "\n".join(r["text"] for r in results)


def ocr_qimage_detailed(
    image: QImage, languages: list[str] | None = None
) -> list[dict]:
    return _run_ocr(image, languages or ["en", "de", "fr"])


def set_languages(languages: list[str]) -> None:
    """Restart the worker with new languages on next call."""
    global _proc_languages
    _proc_languages = []
