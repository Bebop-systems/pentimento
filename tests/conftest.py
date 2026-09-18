"""Shared fixtures.

The JPEG builder produces a real, decodable 1x1 baseline file so tests
exercise genuine container parsing rather than a stub.
"""
import pytest

from anonymizer.engine import ExifToolEngine
from scripts.fetch_exiftool import find_exiftool

MINIMAL_JPEG = bytes.fromhex(
    "ffd8"
    "ffe000104a46494600010100000100010000"
    "ffdb004300" + "08" * 64 +
    "ffc0000b08000100010101110000"
    "ffc400140000010000000000000000000000000000000000"
    "ffc4001410010000000000000000000000000000000000"
    "ffda0008010100003f00d2cf20"
    "ffd9"
)


@pytest.fixture(scope="session")
def exiftool_path():
    path = find_exiftool()
    if path is None:
        pytest.skip("exiftool not vendored; run python scripts/fetch_exiftool.py")
    return path


@pytest.fixture(scope="session")
def engine(exiftool_path):
    with ExifToolEngine(exiftool_path) as e:
        yield e


@pytest.fixture
def make_jpeg(tmp_path):
    def _make(name="in.jpg"):
        path = tmp_path / name
        path.write_bytes(MINIMAL_JPEG)
        return path
    return _make
