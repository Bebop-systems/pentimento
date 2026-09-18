"""Fetch the pinned ExifTool build into vendor/.

ExifTool's Windows builds are hosted on SourceForge. The GitHub repo
publishes tags but no release assets, and exiftool.org links out rather
than serving the zip itself, so neither works as a download source.
"""
from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

EXIFTOOL_VERSION = "13.59"
DOWNLOAD_URL = (
    "https://sourceforge.net/projects/exiftool/files/"
    f"exiftool-{EXIFTOOL_VERSION}_64.zip/download"
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = PROJECT_ROOT / "vendor"


def find_exiftool() -> Path | None:
    """Return the vendored exiftool binary, or None if not yet fetched."""
    if not VENDOR_DIR.exists():
        return None
    for name in ("exiftool.exe", "exiftool(-k).exe", "exiftool"):
        for candidate in VENDOR_DIR.rglob(name):
            if candidate.is_file():
                return candidate
    return None


def download() -> Path:
    """Download and extract ExifTool. Returns the binary path."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        DOWNLOAD_URL, headers={"User-Agent": "anonymizer-setup"}
    )
    print(f"Downloading ExifTool {EXIFTOOL_VERSION} ...", file=sys.stderr)
    with urllib.request.urlopen(req, timeout=180) as resp:
        blob = resp.read()
    if not blob.startswith(b"PK\x03\x04"):
        raise RuntimeError(
            f"Expected a zip, got {len(blob)} bytes starting {blob[:16]!r}"
        )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        zf.extractall(VENDOR_DIR)

    # The standalone build ships as exiftool(-k).exe, which pauses for a
    # keypress on exit. Renaming disables that.
    for k_exe in VENDOR_DIR.rglob("exiftool(-k).exe"):
        k_exe.rename(k_exe.with_name("exiftool.exe"))

    exe = find_exiftool()
    if exe is None:
        raise RuntimeError("Extraction succeeded but no binary was found")
    os.chmod(exe, 0o755)
    return exe


def ensure_exiftool() -> Path:
    """Return the vendored binary, downloading it if absent."""
    existing = find_exiftool()
    if existing is not None:
        return existing
    return download()


if __name__ == "__main__":
    print(ensure_exiftool())
