"""Allow running as ``python -m src.archiver``.

Launches the combined File Tools window (FILE OPS + ARCHIVER tabs),
opening directly on the ARCHIVER tab.
"""

from src.file_ops.file_ops import main

if __name__ == "__main__":
    main()
