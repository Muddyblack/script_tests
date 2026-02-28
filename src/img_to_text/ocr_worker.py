"""Persistent OCR worker — kept alive between calls, reads jobs from stdin."""

import json
import sys
from pathlib import Path


def get_model_dir() -> Path:
    return Path.home() / ".EasyOCR" / "model"


def get_existing_models(model_dir: Path) -> set:
    if not model_dir.exists():
        return set()
    return {f.name for f in model_dir.iterdir()}


def main():
    # First line: languages (comma-separated)
    languages_line = sys.stdin.readline().strip()
    languages = (
        [lang.strip() for lang in languages_line.split(",")]
        if languages_line
        else ["en", "de", "fr"]
    )

    model_dir = get_model_dir()
    models_before = get_existing_models(model_dir)

    if not models_before:
        sys.stderr.write(
            "⬇️  Downloading OCR models for the first time — this may take a minute.\n"
            "    They'll be cached locally and never downloaded again.\n"
        )
        sys.stderr.flush()

    import easyocr

    # Drop recog_network — default is fine and avoids the invalid argument error
    reader = easyocr.Reader(languages, gpu=False)

    models_after = get_existing_models(model_dir)
    new_models = models_after - models_before
    if new_models:
        sys.stderr.write(f"✅  Models ready ({', '.join(sorted(new_models))}).\n")
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
            adjust_contrast = job.get("adjust_contrast", 0.5)
            text_threshold = job.get("text_threshold", 0.7)
            low_text = job.get("low_text", 0.4)
            min_size = job.get("min_size", 10)
            paragraph = job.get("paragraph", False)
            batch_size = job.get("batch_size", 1)
        except (json.JSONDecodeError, AttributeError):
            image_path = line
            width_ths = 0.7
            contrast_ths = 0.1
            adjust_contrast = 0.5
            text_threshold = 0.7
            low_text = 0.4
            min_size = 10
            paragraph = False
            batch_size = 1

        if not image_path:
            continue

        try:
            results = reader.readtext(
                image_path,
                width_ths=width_ths,
                contrast_ths=contrast_ths,
                adjust_contrast=adjust_contrast,
                text_threshold=text_threshold,
                low_text=low_text,
                min_size=min_size,
                paragraph=paragraph,
                batch_size=batch_size,
                decoder="beamsearch",
                beamWidth=10,
            )

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
