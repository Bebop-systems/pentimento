"""Path resolution, which changes shape inside a packaged app."""
import os
from pathlib import Path

import pytest

from anonymizer import paths
from anonymizer.__main__ import choose_mode


def test_source_checkout_resolves_beside_the_project():
    assert paths.resource_dir() == paths.PROJECT_ROOT
    assert paths.web_dir().is_dir()
    assert (paths.web_dir() / "index.html").is_file()


def test_output_lives_in_the_project_when_run_from_source():
    assert paths.default_output_dir() == paths.PROJECT_ROOT / "output"


def test_frozen_resources_come_from_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_dir() == tmp_path
    assert paths.web_dir() == tmp_path / "web"
    assert paths.vendor_dir() == tmp_path / "vendor"


def test_frozen_output_is_somewhere_writable(monkeypatch):
    """A packaged app cannot write beside its own executable."""
    monkeypatch.delenv("ANONYMIZER_OUTPUT", raising=False)
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    output = paths.default_output_dir()
    assert paths.PROJECT_ROOT not in output.parents
    assert Path.home() in output.parents or output.parent == Path.home()
    assert output.name == "Metadata Editor"


def test_output_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("ANONYMIZER_OUTPUT", str(tmp_path / "elsewhere"))
    assert paths.default_output_dir() == tmp_path / "elsewhere"


def test_find_exiftool_locates_the_vendored_binary():
    found = paths.find_exiftool()
    assert found is not None and found.is_file()


def test_find_exiftool_returns_none_when_absent(tmp_path):
    assert paths.find_exiftool(tmp_path / "nothing") is None


def test_find_exiftool_prefers_a_direct_hit(tmp_path):
    name = "exiftool.exe" if os.name == "nt" else "exiftool"
    (tmp_path / name).write_bytes(b"stub")
    nested = tmp_path / "deep" / "deeper"
    nested.mkdir(parents=True)
    (nested / name).write_bytes(b"stub")
    assert paths.find_exiftool(tmp_path) == tmp_path / name


@pytest.mark.parametrize("args,frozen,expected", [
    ([], False, "browser"),
    ([], True, "window"),
    (["--window"], False, "window"),
    (["--browser"], True, "browser"),
    (["--no-browser"], True, "headless"),
    (["8080", "--no-browser"], False, "headless"),
])
def test_launch_mode(monkeypatch, args, frozen, expected):
    monkeypatch.setattr(paths, "is_frozen", lambda: frozen)
    import anonymizer.__main__ as entry
    monkeypatch.setattr(entry, "is_frozen", lambda: frozen)
    assert choose_mode(args) == expected
