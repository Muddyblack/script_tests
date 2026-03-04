"""OCR extraction — persistent subprocess to avoid Qt/torch DLL conflicts and model reloads."""

from __future__ import annotations

import atexit
import contextlib
import json
import math
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QImage

_WORKER = Path(__file__).parent / "ocr_worker.py"

_proc: subprocess.Popen | None = None
_proc_languages: list[str] = []
_proc_lock = threading.Lock()


def _bbox_stats(bbox: list[list[int]]) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(1.0, float(max_x - min_x))
    height = max(1.0, float(max_y - min_y))
    center_y = (float(min_y) + float(max_y)) / 2.0
    return float(min_x), center_y, width, height


def _results_to_text(results: list[dict]) -> str:
    if not results:
        return ""

    words: list[dict[str, float | str]] = []
    heights: list[float] = []

    for item in results:
        text = str(item.get("text", "")).strip()
        bbox = item.get("bbox")
        if not text or not isinstance(bbox, list) or len(bbox) < 4:
            continue
        min_x, center_y, width, height = _bbox_stats(bbox)
        heights.append(height)
        words.append(
            {
                "text": text,
                "x": min_x,
                "cy": center_y,
                "w": width,
                "h": height,
            }
        )

    if not words:
        return ""

    median_height = sorted(heights)[len(heights) // 2]
    line_tol = max(6.0, median_height * 0.55)

    words.sort(key=lambda item: (float(item["cy"]), float(item["x"])))
    lines: list[list[dict[str, float | str]]] = []

    for word in words:
        if not lines:
            lines.append([word])
            continue

        last_line = lines[-1]
        last_cy = sum(float(w["cy"]) for w in last_line) / len(last_line)
        if math.fabs(float(word["cy"]) - last_cy) <= line_tol:
            last_line.append(word)
        else:
            lines.append([word])

    text_lines: list[str] = []
    for line in lines:
        line.sort(key=lambda item: float(item["x"]))
        tokens = [str(item["text"]) for item in line if str(item["text"]).strip()]
        if not tokens:
            continue

        no_space_before = ".,;:!?%)]}»/"
        no_space_after = "([{«/"

        assembled = tokens[0]
        for token in tokens[1:]:
            prev = assembled[-1] if assembled else ""
            first = token[0]
            if first in no_space_before or prev in no_space_after:
                assembled += token
            else:
                assembled += f" {token}"

        text_lines.append(assembled.strip())

    return "\n".join(line for line in text_lines if line)


def _results_to_raw_text(results: list[dict]) -> str:
    return "\n".join(
        str(item.get("text", "")).strip()
        for item in results
        if str(item.get("text", "")).strip()
    )


def _average_confidence(results: list[dict]) -> float:
    if not results:
        return 0.0
    total = 0.0
    count = 0
    for item in results:
        try:
            total += float(item.get("confidence", 0.0))
            count += 1
        except (TypeError, ValueError):
            continue
    if count == 0:
        return 0.0
    return total / count


def _apply_code_confusion_fixes(text: str) -> str:
    if not text:
        return text

    fixed = text
    fixed = re.sub(r"\s*([/:._\\=@-])\s*", r"\1", fixed)
    fixed = re.sub(r"(?<=\d)[lI](?=\d)", "1", fixed)
    fixed = re.sub(r"(?<=\d)O(?=\d)", "0", fixed)
    fixed = fixed.replace("—", "-").replace("–", "-")
    fixed = re.sub(r"[ \t]+", " ", fixed)
    fixed = re.sub(r" *\n *", "\n", fixed)
    return fixed.strip()


def _format_results_text(
    results: list[dict],
    *,
    raw_output: bool,
    one_line_output: bool,
    code_fix: bool,
) -> str:
    text = _results_to_raw_text(results) if raw_output else _results_to_text(results)
    if code_fix:
        text = _apply_code_confusion_fixes(text)
    if one_line_output:
        text = " ".join(part for part in text.replace("\n", " ").split(" ") if part)
    return text.strip()


def _get_proc(languages: list[str]) -> subprocess.Popen:
    global _proc, _proc_languages

    with _proc_lock:
        return _get_proc_locked(languages)


def _get_proc_locked(languages: list[str]) -> subprocess.Popen:
    """Must be called with _proc_lock held."""
    global _proc, _proc_languages

    if _proc is not None and _proc.poll() is not None:
        _proc = None  # died, restart

    # Only restart the worker if it lacks one or more of the requested languages.
    # Removing a language never requires a restart — the loaded reader handles any
    # subset of its initialised languages (same model files on disk regardless).
    needs_restart = _proc is None or not set(languages).issubset(set(_proc_languages))

    if needs_restart:
        if _proc is not None:
            _proc.stdin.close()
            _proc.wait()
        # CREATE_NEW_PROCESS_GROUP isolates the child from the parent's
        # Ctrl+C signal so torch/easyocr imports can't be interrupted by the
        # user closing nexus while the model is loading.
        _extra: dict = {}
        if sys.platform == "win32":
            _extra["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        _proc = subprocess.Popen(
            [sys.executable, "-u", str(_WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,   # let worker's terminal output flow through to the console
            text=True,
            **_extra,
        )
        _proc.stdin.write(",".join(languages) + "\n")
        _proc.stdin.flush()
        # Wait for "ready" — or an error JSON if models are missing
        startup_line = _proc.stdout.readline().strip()
        if startup_line != "ready":
            try:
                data = json.loads(startup_line)
                if "message" in data:
                    raise RuntimeError(data["message"])
            except (json.JSONDecodeError, KeyError):
                pass
            raise RuntimeError(
                "OCR worker failed to start — check the console for details."
            )
        _proc_languages = languages

    return _proc


@atexit.register
def _shutdown():
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.stdin.close()
        _proc.wait()


def _run_ocr(
    image: QImage,
    languages: list[str],
    *,
    symbol_priority: bool = False,
) -> list[dict]:
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
        proc.stdin.write(
            json.dumps(
                {
                    "path": tmp_path,
                    "symbol_priority": symbol_priority,
                }
            )
            + "\n"
        )
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


def ocr_qimage(
    image: QImage,
    languages: list[str] | None = None,
    *,
    raw_output: bool = False,
    one_line_output: bool = False,
    code_fix: bool = False,
    symbol_priority: bool = False,
) -> str:
    results = _run_ocr(
        image,
        languages or ["en", "de"],
        symbol_priority=symbol_priority,
    )
    return _format_results_text(
        results,
        raw_output=raw_output,
        one_line_output=one_line_output,
        code_fix=code_fix,
    )


def ocr_qimage_with_meta(
    image: QImage,
    languages: list[str] | None = None,
    *,
    raw_output: bool = False,
    one_line_output: bool = False,
    code_fix: bool = False,
    symbol_priority: bool = False,
) -> dict[str, float | str]:
    results = _run_ocr(
        image,
        languages or ["en", "de"],
        symbol_priority=symbol_priority,
    )
    return {
        "text": _format_results_text(
            results,
            raw_output=raw_output,
            one_line_output=one_line_output,
            code_fix=code_fix,
        ),
        "confidence": round(_average_confidence(results), 4),
    }


def ocr_qimage_detailed(
    image: QImage,
    languages: list[str] | None = None,
    *,
    symbol_priority: bool = False,
) -> list[dict]:
    return _run_ocr(
        image,
        languages or ["en", "de"],
        symbol_priority=symbol_priority,
    )


def set_languages(languages: list[str]) -> None:
    """Restart the worker with new languages on next call."""
    global _proc_languages
    _proc_languages = []


def pre_warm(languages: list[str] | None = None) -> None:
    """Start the OCR worker process in the background so the model is ready before first use."""
    from . import _settings as S  # import here to avoid circular imports at module level

    _langs = languages if languages is not None else list(S.ocr_langs)

    def _warm():
        with contextlib.suppress(Exception):
            _get_proc(_langs)

    threading.Thread(target=_warm, daemon=True, name="ocr-prewarm").start()
