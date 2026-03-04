"""Nexus Search — thin launcher."""

import multiprocessing
import sys

multiprocessing.freeze_support()

# When frozen, the exe re-invokes itself to run subprocesses (e.g. OCR worker).
# Detect that here before any Qt/heavy imports happen.
if "--ocr-worker" in sys.argv:
    from src.img_to_text.ocr_worker import main as _ocr_main
    _ocr_main()
    sys.exit(0)

if __name__ == "__main__":
    from src.nexus.app import main
    main()
