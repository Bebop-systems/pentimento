#!/usr/bin/env python3
"""Start the metadata editor.

    python run.py                 pick a free port, open a browser
    python run.py 8731            use a specific port
    python run.py --no-browser    do not open a browser
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from anonymizer.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
