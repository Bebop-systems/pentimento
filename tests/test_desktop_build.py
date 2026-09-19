"""The packaging configuration.

These do not run a build. They pin the decisions a build depends on, so a
change that would quietly produce a broken app fails here first.
"""
import importlib.util
import struct
from pathlib import Path

import pytest

from pentimento.paths import PROJECT_ROOT

DESKTOP = PROJECT_ROOT / "desktop"
SPEC = DESKTOP / "Pentimento.spec"


def test_spec_exists():
    assert SPEC.is_file()


def test_the_bundle_ships_exiftool_and_the_web_assets():
    """Without these the packaged app starts and then cannot do anything."""
    spec = SPEC.read_text(encoding="utf-8")
    assert '(str(ROOT / "web"), "web")' in spec
    assert '(str(ROOT / "vendor"), "vendor")' in spec


def test_the_build_is_one_folder_not_one_file():
    """ExifTool is 500-odd files; onefile would unpack them every launch."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "COLLECT(" in spec
    assert "exclude_binaries=True" in spec


def test_the_app_has_no_console_window():
    assert "console=False" in SPEC.read_text(encoding="utf-8")


def test_windows_webview_imports_are_declared():
    """pywebview reaches these through pythonnet, so PyInstaller cannot see
    them by static analysis and they have to be named."""
    spec = SPEC.read_text(encoding="utf-8")
    for needed in ("webview.platforms.winforms", "clr", "clr_loader"):
        assert needed in spec


def test_no_browser_is_bundled():
    """The window is drawn by an OS component, not a shipped Chromium."""
    spec = SPEC.read_text(encoding="utf-8")
    for absent in ("cefpython", "chromium", "electron"):
        assert absent not in spec.lower()


@pytest.mark.parametrize("name", ["icon.ico", "icon.icns", "icon.png"])
def test_icons_are_generated_and_valid(name):
    from desktop.make_icon import build_icns, build_ico, build_png

    builders = {"icon.ico": build_ico, "icon.icns": build_icns,
                "icon.png": build_png}
    path = DESKTOP / name
    if not path.is_file():
        builders[name](path)
    data = path.read_bytes()
    assert len(data) > 500

    if name == "icon.png":
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
    elif name == "icon.ico":
        reserved, kind, count = struct.unpack("<HHH", data[:6])
        assert (reserved, kind) == (0, 1) and count >= 5
    else:
        assert data[:4] == b"icns"
        assert struct.unpack(">I", data[4:8])[0] == len(data)


def test_icon_renders_deterministically():
    """A build should not produce a different binary from the same source."""
    from desktop.make_icon import render
    assert render(32) == render(32)


def test_build_check_reports_problems_as_actionable_strings():
    """What check() returns is testable anywhere; whether this particular
    machine can build is not a property of the code."""
    from desktop.build import check

    problems = check()
    assert isinstance(problems, list)
    assert all(isinstance(p, str) and p for p in problems)
    # Every problem has to say how to fix it, since it is read by someone
    # who just wants a build.
    assert all(("install" in p.lower() or "missing" in p.lower()
                or "run " in p.lower()) for p in problems), problems


@pytest.mark.skipif(
    importlib.util.find_spec("PyInstaller") is None,
    reason="build tooling not installed; see requirements-build.txt",
)
def test_a_build_machine_reports_ready():
    from desktop.build import check
    assert check() == [], "build tooling is installed but check() objects"
