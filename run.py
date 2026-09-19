#!/usr/bin/env python3
"""Start the metadata editor.

    python run.py                 browser, free port
    python run.py 8731            a specific port
    python run.py --window        a native application window
    python run.py --no-browser    start the server and open nothing

A packaged build opens its own window by default.
"""
import sys
from pathlib import Path

# Only meaningful from a checkout. A frozen app already has its modules.
if not getattr(sys, "frozen", False):
    ROOT = Path(__file__).resolve().parent
    sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from anonymizer.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
