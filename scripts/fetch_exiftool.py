"""Fetch the pinned ExifTool build into vendor/.

ExifTool's downloads are hosted on SourceForge. The GitHub repo publishes
tags but no release assets, and exiftool.org links out rather than serving
the archive itself, so neither works as a source.

Windows gets the standalone build, which carries its own Perl. Everything
else gets the plain distribution, which is a Perl script plus its library
and runs on the system Perl that macOS and Linux already ship.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent.parent / "src")]

from pentimento.paths import (  # noqa: E402
    PROJECT_ROOT, VENDOR_NAME, find_exiftool as _find,
)

EXIFTOOL_VERSION = "13.59"
VENDOR_DIR = PROJECT_ROOT / VENDOR_NAME

_BASE = "https://sourceforge.net/projects/exiftool/files"
WINDOWS_URL = f"{_BASE}/exiftool-{EXIFTOOL_VERSION}_64.zip/download"
GENERIC_URL = f"{_BASE}/Image-ExifTool-{EXIFTOOL_VERSION}.tar.gz/download"


def download_url() -> str:
    return WINDOWS_URL if os.name == "nt" else GENERIC_URL


def find_exiftool() -> Path | None:
    """Kept for callers and tests that import it from here."""
    return _find(VENDOR_DIR)


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "pentimento-setup"})
    print(f"Downloading ExifTool {EXIFTOOL_VERSION} ...", file=sys.stderr)
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


# Directories in the generic distribution that are not needed to run
# ExifTool. `t/` is its own test suite, and it is not merely dead weight:
# t/images holds deliberately malformed files, including a Mach-O with no
# load commands. PyInstaller recognises the magic number, tries to process
# it as a real binary, and fails the entire macOS build.
_PRUNE = ("t", "html")


def _prune(root: Path) -> int:
    removed = 0
    for name in _PRUNE:
        target = root / name
        if target.is_dir():
            removed += sum(1 for _ in target.rglob("*") if _.is_file())
            shutil.rmtree(target, ignore_errors=True)
    return removed


def download() -> Path:
    """Download and extract ExifTool. Returns the binary path."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    blob = _fetch(download_url())

    if blob[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            archive.extractall(VENDOR_DIR)
    elif blob[:2] == b"\x1f\x8b":
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
            # filter="data" refuses absolute paths and traversal, which is
            # the documented safe extraction mode from Python 3.12 on.
            archive.extractall(VENDOR_DIR, filter="data")
        for extracted in VENDOR_DIR.glob(f"Image-ExifTool-{EXIFTOOL_VERSION}"):
            script = extracted / "exiftool"
            if script.is_file():
                script.chmod(0o755)
            _prune(extracted)
    else:
        raise RuntimeError(
            f"Expected an archive, got {len(blob)} bytes starting {blob[:16]!r}"
        )

    # The Windows standalone ships as exiftool(-k).exe, which pauses for a
    # keypress on exit. Renaming disables that.
    for k_exe in VENDOR_DIR.rglob("exiftool(-k).exe"):
        k_exe.rename(k_exe.with_name("exiftool.exe"))

    binary = find_exiftool()
    if binary is None:
        raise RuntimeError("Extraction succeeded but no binary was found")
    if os.name != "nt":
        binary.chmod(0o755)
    return binary


def ensure_exiftool() -> Path:
    """Return the vendored binary, downloading it if absent."""
    existing = find_exiftool()
    return existing if existing is not None else download()


def clean() -> None:
    shutil.rmtree(VENDOR_DIR, ignore_errors=True)


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
    print(ensure_exiftool())
