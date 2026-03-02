"""Persistent OCR worker — kept alive between calls, reads jobs from stdin."""

import itertools
import json
import sys
import threading
from pathlib import Path

# ── Terminal spinner ───────────────────────────────────────────────────────────

def _start_spinner(msg: str) -> threading.Event:
    """Start a braille spinner on stderr; returns a stop-event to kill it."""
    stop = threading.Event()

    def _spin():
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        for frame in itertools.cycle(frames):
            if stop.is_set():
                break
            sys.stderr.write(f"\r  {frame}  {msg}   ")
            sys.stderr.flush()
            stop.wait(0.08)
        # Clear the spinner line
        sys.stderr.write("\r" + " " * (len(msg) + 10) + "\r")
        sys.stderr.flush()

    t = threading.Thread(target=_spin, daemon=True, name="ocr-spinner")
    t.start()
    return stop


def get_model_dir() -> Path:
    # Store models inside the project so they travel with the repo
    project_root = Path(__file__).parent.parent.parent
    return project_root / "models" / "easyocr"


def get_existing_models(model_dir: Path) -> set:
    if not model_dir.exists():
        return set()
    return {f.name for f in model_dir.iterdir()}



def _avg_confidence(results) -> float:
    if not results:
        return 0.0
    total = 0.0
    for _, _, conf in results:
        total += float(conf)
    return total / len(results)


def _punct_count(results) -> int:
    punct = ".,:;/\\-_@#[]{}()=+!?%&*"
    count = 0
    for _, text, _ in results:
        for ch in str(text):
            if ch in punct:
                count += 1
    return count


def _score_results(results, *, prefer_symbols: bool) -> float:
    if not results:
        return 0.0
    score = _avg_confidence(results)
    if prefer_symbols:
        score += min(0.20, _punct_count(results) * 0.01)
    return score


def main():
    # First line: languages (comma-separated)
    languages_line = sys.stdin.readline().strip()
    languages = (
        [lang.strip() for lang in languages_line.split(",")]
        if languages_line
        else ["en", "de"]
    )

    model_dir = get_model_dir()
    project_root = Path(__file__).parent.parent.parent

    sys.stderr.write(f"  🔁  Loading OCR models ({', '.join(sorted(get_existing_models(model_dir)))})…\n")
    sys.stderr.flush()
    spinner_stop = _start_spinner("Loading model weights")

    import warnings

    import easyocr

    model_dir.mkdir(parents=True, exist_ok=True)

    # Suppress noisy-but-harmless third-party warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*pin_memory.*", category=UserWarning)
        warnings.filterwarnings("ignore", message=".*overflow.*", category=RuntimeWarning)
        import os as _os
        _devnull = open(_os.devnull, "w")
        import sys as _sys
        _old_stderr = _sys.stderr
        _sys.stderr = _devnull
        try:
            reader = easyocr.Reader(
                languages,
                gpu=False,
                model_storage_directory=str(model_dir),
                download_enabled=False,   # never download — fail loudly instead
            )
        except Exception as exc:
            rel_dir = (
                model_dir.relative_to(project_root)
                if model_dir.is_relative_to(project_root)
                else model_dir
            )
            _sys.stderr = _old_stderr
            _devnull.close()
            spinner_stop.set()
            # EasyOCR raises RuntimeError / FileNotFoundError for missing models
            msg = (
                f"Failed to load OCR model: {exc}\n\n"
                f"Make sure all required .pth files are in  {rel_dir}\n"
                "See  https://github.com/JaidedAI/EasyOCR  for model downloads."
            )
            sys.stderr.write(f"\n  ❌  {msg}\n\n")
            sys.stderr.flush()
            sys.stdout.write(json.dumps({"error": "missing_models", "message": msg}) + "\n")
            sys.stdout.flush()
            sys.exit(1)
        finally:
            _sys.stderr = _old_stderr
            _devnull.close()

    spinner_stop.set()
    sys.stderr.write("  ✅  Ready.\n")
    sys.stderr.flush()

    sys.stdout.write("ready\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            job = json.loads(line)
            image_path = job.get("path", "")
            width_ths = job.get("width_ths", 0.7)
            contrast_ths = job.get("contrast_ths", 0.1)
            adjust_contrast = job.get("adjust_contrast", 0.0)
            text_threshold = job.get("text_threshold", 0.7)
            low_text = job.get("low_text", 0.4)
            min_size = job.get("min_size", 3)
            paragraph = job.get("paragraph", False)
            batch_size = job.get("batch_size", 1)
            symbol_priority = bool(job.get("symbol_priority", False))
        except (json.JSONDecodeError, AttributeError):
            image_path = line
            width_ths = 0.7
            contrast_ths = 0.1
            adjust_contrast = 0.0
            text_threshold = 0.7
            low_text = 0.4
            min_size = 3
            paragraph = False
            batch_size = 1
            symbol_priority = False

        if not image_path:
            continue

        if symbol_priority:
            contrast_ths = min(contrast_ths, 0.05)
            text_threshold = min(text_threshold, 0.62)
            low_text = min(low_text, 0.25)
            min_size = min(min_size, 1)

        try:
            import warnings as _w
            _w.filterwarnings("ignore", message=".*pin_memory.*", category=UserWarning)
            _w.filterwarnings("ignore", message=".*overflow.*", category=RuntimeWarning)

            def _read(
                adjust_value: float,
                decoder: str,
                beam_width: int | None = None,
                image=image_path,
                width=width_ths,
                contrast=contrast_ths,
                text_ths=text_threshold,
                low=low_text,
                min_sz=min_size,
                para=paragraph,
                batch=batch_size,
            ):
                kwargs = {
                    "image": image,
                    "width_ths": width,
                    "contrast_ths": contrast,
                    "adjust_contrast": adjust_value,
                    "text_threshold": text_ths,
                    "low_text": low,
                    "min_size": min_sz,
                    "paragraph": para,
                    "batch_size": batch,
                    "decoder": decoder,
                }
                if beam_width is not None:
                    kwargs["beamWidth"] = beam_width
                return reader.readtext(
                    **kwargs,
                )

            results = _read(adjust_contrast, "greedy")

            # Fast path first; fallback for difficult low-contrast captures.
            if not results and adjust_contrast <= 0:
                results = _read(0.5, "greedy")

            if not results and symbol_priority:
                results = _read(max(adjust_contrast, 0.5), "beamsearch", beam_width=7)

            # Accuracy fallback for difficult captures (symbols/special chars).
            if results:
                avg_conf = _avg_confidence(results)
                conf_threshold = 0.76 if symbol_priority else 0.62
                if avg_conf < conf_threshold:
                    beam_width = 7 if symbol_priority else 5
                    beam_adjust = max(adjust_contrast, 0.35) if symbol_priority else adjust_contrast
                    beam_results = _read(beam_adjust, "beamsearch", beam_width=beam_width)
                    if beam_results:
                        current_score = _score_results(
                            results,
                            prefer_symbols=symbol_priority,
                        )
                        beam_score = _score_results(
                            beam_results,
                            prefer_symbols=symbol_priority,
                        )
                        if beam_score > current_score:
                            results = beam_results

            output = []
            for bbox, text, conf in results:
                if not text.strip():
                    continue
                clean_bbox = [[int(pt[0]), int(pt[1])] for pt in bbox]
                output.append(
                    {
                        "text": text,
                        "confidence": round(float(conf), 4),
                        "bbox": clean_bbox,
                    }
                )
            sys.stdout.write(json.dumps({"results": output}) + "\n")
        except Exception as e:
            sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
