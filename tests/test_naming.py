"""Output filenames.

A filename is metadata. These tests pin two promises: the default name is
stable rather than piling up numbered copies, and a pattern is never
allowed to escape the output folder.
"""
from pathlib import Path

import pytest

from anonymizer.naming import (
    DEFAULT_COLLISION, DEFAULT_PATTERN, Naming, NamingError,
    build_values, render, safe_filename,
)


@pytest.fixture
def values():
    return build_values(Path("IMG_0942.HEIC"), "reprofile", "pixel-8")


def test_defaults_do_not_number(values, tmp_path):
    naming = Naming()
    assert naming.pattern == DEFAULT_PATTERN
    assert naming.on_collision == DEFAULT_COLLISION
    first = naming.resolve(tmp_path, values)
    first.write_bytes(b"x")
    assert naming.resolve(tmp_path, values) == first


def test_numbering_is_available_as_a_choice(values, tmp_path):
    naming = Naming(DEFAULT_PATTERN, "number")
    first = naming.resolve(tmp_path, values)
    first.write_bytes(b"x")
    second = naming.resolve(tmp_path, values)
    assert second != first
    assert second.name == "IMG_0942_clean_2.HEIC"


def test_timestamp_mode_is_available(values, tmp_path):
    naming = Naming(DEFAULT_PATTERN, "timestamp")
    first = naming.resolve(tmp_path, values)
    first.write_bytes(b"x")
    assert naming.resolve(tmp_path, values) != first


def test_a_sequenced_pattern_numbers_itself(values, tmp_path):
    naming = Naming("GBCAM_{n:03}{ext}")
    assert naming.sequenced
    names = []
    for _ in range(3):
        path = naming.resolve(tmp_path, values)
        path.write_bytes(b"x")
        names.append(path.name)
    assert names == ["GBCAM_001.HEIC", "GBCAM_002.HEIC", "GBCAM_003.HEIC"]


def test_sequenced_patterns_ignore_the_collision_mode(values, tmp_path):
    """{n} already guarantees a free name, so overwrite cannot apply."""
    naming = Naming("IMG_{n:04}{ext}", "overwrite")
    first = naming.resolve(tmp_path, values)
    first.write_bytes(b"x")
    assert naming.resolve(tmp_path, values).name == "IMG_0002.HEIC"


@pytest.mark.parametrize("token,expected", [
    ("{stem}", "IMG_0942"),
    ("{ext}", ".HEIC"),
    ("{preset}", "reprofile"),
    ("{profile}", "pixel-8"),
])
def test_tokens_render(values, token, expected):
    assert render(token, values) == expected


def test_format_specs_work(values):
    assert render("{n:04}", {**values, "n": 7}) == "0007"


def test_unknown_token_is_rejected_with_help(values):
    with pytest.raises(NamingError, match="Unknown token"):
        render("{nope}", values)
    with pytest.raises(NamingError, match="stem"):
        render("{nope}", values)


def test_unbalanced_braces_are_rejected(values):
    with pytest.raises(NamingError, match="Unbalanced"):
        render("{stem", values)


def test_empty_pattern_is_rejected(values):
    with pytest.raises(NamingError, match="empty"):
        Naming("   ").preview(values)


def test_unknown_collision_mode_is_rejected():
    with pytest.raises(NamingError, match="collision"):
        Naming(DEFAULT_PATTERN, "explode")


@pytest.mark.parametrize("hostile", [
    "../../escape{ext}",
    "sub/dir/file{ext}",
    r"back\slash{ext}",
    "colon:name{ext}",
    "{stem}/../../..{ext}",
])
def test_a_pattern_cannot_escape_the_output_folder(values, tmp_path, hostile):
    """The guarantee is containment, not the absence of dots in a name.

    `_.._escape.HEIC` is a perfectly safe filename; what must never happen
    is a path that resolves outside the output folder.
    """
    path = Naming(hostile).resolve(tmp_path, values)
    assert path.resolve().parent == tmp_path.resolve()
    assert not {"/", "\\"} & set(path.name)
    assert path.name not in ("", ".", "..")


def test_windows_reserved_names_are_defused(values):
    assert safe_filename("CON.HEIC") != "CON.HEIC"
    assert safe_filename("nul.jpg").lower() != "nul.jpg"


def test_an_empty_render_still_produces_a_file(values):
    assert safe_filename("", ".HEIC") == "cleaned.HEIC"


def test_names_stay_a_sane_length(values):
    assert len(safe_filename("x" * 500 + ".HEIC")) <= 180
