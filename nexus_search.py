"""Nexus Search — thin launcher (backward-compatible entry point).

The actual implementation has been restructured into ``src/nexus/``.
Run this file directly or use ``python -m src.nexus`` for the same result.
"""

from src.nexus.app import main

if __name__ == "__main__":
    main()
else:
    # Support running without ``if __name__`` guard (e.g. ``python nexus_search.py``)
    main()
