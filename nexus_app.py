"""Nexus Search — thin launcher."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from src.nexus.app import main
    main()
