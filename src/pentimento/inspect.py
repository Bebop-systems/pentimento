"""Read a file's metadata into a TagSet."""
from __future__ import annotations

from pathlib import Path

from .model import TagSet


def read_tags(engine, path: Path) -> TagSet:
    """Two passes: -n for machine values, plain for display values.

    The UI needs both: 47.62089 is what you edit, 47 deg 37' 15.20" N is
    what you read.
    """
    path = Path(path)
    machine = engine.read_json(path, "-n")[0]
    display = engine.read_json(path)[0]
    return TagSet.from_exiftool(path, machine, display)
