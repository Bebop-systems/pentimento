"""One version, stated once.

`pentimento/version.py` is the only place a version is written by hand.
Two build inputs cannot read Python and so are generated from it, and
`pyproject.toml` derives it through a setuptools attribute.

The risk is drift: someone bumps the source and forgets to regenerate, so
a release ships an installer and a binary claiming the previous version.
These tests regenerate into a temporary place and compare, which fails
loudly the moment that happens.
"""
import re
import subprocess
import sys
from pathlib import Path

from pentimento.version import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_is_semantic():
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", __version__)


def test_pyproject_derives_rather_than_repeats():
    """A literal version in pyproject would be a fourth thing to forget."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in text
    assert 'attr = "pentimento.version.__version__"' in text
    assert not re.search(r'^version = "\d', text, re.MULTILINE)


def test_installer_include_is_current():
    include = (ROOT / "desktop" / "version.iss").read_text(encoding="utf-8")
    declared = re.search(r'#define AppVersion\s+"([^"]+)"', include).group(1)
    assert declared == __version__, (
        "desktop/version.iss is stale - run python scripts/set_version.py --regenerate"
    )


def test_installer_reads_the_include_rather_than_hardcoding():
    text = (ROOT / "desktop" / "installer.iss").read_text(encoding="utf-8")
    assert '#include "version.iss"' in text
    assert not re.search(r'#define AppVersion\s+"\d', text)


def test_windows_version_resource_is_current():
    resource = (ROOT / "desktop" / "version_info.txt").read_text(encoding="utf-8")
    assert f'StringStruct("FileVersion", "{__version__}")' in resource, (
        "desktop/version_info.txt is stale - run "
        "python scripts/set_version.py --regenerate"
    )
    assert f'StringStruct("ProductVersion", "{__version__}")' in resource


def test_regenerating_changes_nothing(tmp_path):
    """The committed generated files must match what a build would produce.

    Regenerated into a temporary directory on purpose. An earlier version
    of this test wrote over the real files, which quietly repaired the
    drift it was supposed to report.
    """
    sys.path[:0] = [str(ROOT), str(ROOT / "src")]
    from scripts.set_version import regenerate

    regenerate(__version__, into=tmp_path)

    for name in ("version.iss", "version_info.txt"):
        committed = (ROOT / "desktop" / name).read_text(encoding="utf-8")
        expected = (tmp_path / name).read_text(encoding="utf-8")
        assert committed == expected, (
            f"desktop/{name} is out of date - run "
            f"python scripts/set_version.py --regenerate"
        )


def test_changelog_documents_this_version():
    """A release nobody wrote down is a release nobody can audit."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"[{__version__}]" in changelog


def test_the_imported_version_matches_the_file_on_disk():
    """Guards a trap this project actually fell into.

    CPython invalidates a .pyc by source mtime *and size*. Editing
    "0.9.9" to "0.1.0" changes neither - same five bytes, same second -
    so the stale bytecode was reused and the build stamped a version that
    appeared nowhere in the source. Comparing the parsed file against the
    imported value catches that in one assertion.
    """
    source = (ROOT / "src" / "pentimento" / "version.py").read_text(encoding="utf-8")
    on_disk = re.search(r'^__version__ = "([^"]+)"', source, re.MULTILINE).group(1)
    assert on_disk == __version__, (
        f"version.py says {on_disk} but imports as {__version__}: stale "
        f"bytecode. Delete __pycache__ directories."
    )
