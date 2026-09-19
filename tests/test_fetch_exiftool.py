"""Fetching ExifTool.

The archive differs by platform: Windows gets the standalone build with
its own Perl and an .exe, everything else gets the plain distribution,
which is a Perl script named `exiftool` with no extension. These tests
have to follow that rather than assume a .exe.
"""
import os

from scripts.fetch_exiftool import (
    EXIFTOOL_VERSION, download_url, find_exiftool,
)

BINARY_NAME = "exiftool.exe" if os.name == "nt" else "exiftool"


def test_version_is_pinned():
    assert EXIFTOOL_VERSION == "13.59"


def test_the_download_matches_this_platform():
    url = download_url()
    if os.name == "nt":
        assert url.endswith(f"exiftool-{EXIFTOOL_VERSION}_64.zip/download")
    else:
        assert url.endswith(f"Image-ExifTool-{EXIFTOOL_VERSION}.tar.gz/download")


def test_find_exiftool_returns_none_when_vendor_empty(tmp_path, monkeypatch):
    import scripts.fetch_exiftool as fx
    monkeypatch.setattr(fx, "VENDOR_DIR", tmp_path / "nothing")
    assert find_exiftool() is None


def test_find_exiftool_locates_binary(tmp_path, monkeypatch):
    """The extracted folder is named differently on each platform, so the
    search walks rather than guessing a path."""
    import scripts.fetch_exiftool as fx

    folder = tmp_path / (
        f"exiftool-{EXIFTOOL_VERSION}_64" if os.name == "nt"
        else f"Image-ExifTool-{EXIFTOOL_VERSION}"
    )
    folder.mkdir(parents=True)
    binary = folder / BINARY_NAME
    binary.write_bytes(b"stub")

    monkeypatch.setattr(fx, "VENDOR_DIR", tmp_path)
    assert find_exiftool() == binary
