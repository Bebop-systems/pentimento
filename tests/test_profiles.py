"""Profiles, including the deliberately silly ones.

A novelty profile is absurd about which camera it claims and rigorous about
everything else: its numeric fields have to stay real numbers or ExifTool
cannot write them and the gates cannot pass.
"""
import re

import pytest

from pentimento.profiles import CREDIBLE_KEYS, NOVELTY_KEYS, PROFILES

NUMERIC = ("focal_length", "f_number")


def test_every_profile_is_in_exactly_one_group():
    assert set(CREDIBLE_KEYS) | set(NOVELTY_KEYS) == set(PROFILES)
    assert not set(CREDIBLE_KEYS) & set(NOVELTY_KEYS)


def test_the_requested_novelties_exist():
    for key in ("gameboy-camera", "toaster", "dream"):
        assert key in PROFILES
        assert PROFILES[key].novelty


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_numeric_fields_are_actually_numeric(key):
    """The comedy belongs in the text fields; optics stay arithmetic."""
    profile = PROFILES[key]
    for field in NUMERIC:
        value = getattr(profile, field)
        assert re.fullmatch(r"\d+(\.\d+)?", value), f"{key}.{field} = {value!r}"
        assert float(value) > 0


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_every_profile_has_a_complete_identity(key):
    profile = PROFILES[key]
    for field in ("label", "make", "model", "lens_model", "lens_make", "software"):
        assert getattr(profile, field), f"{key} is missing {field}"


@pytest.mark.parametrize("key", NOVELTY_KEYS)
def test_novelty_profiles_explain_themselves(key):
    """The note carries the joke and, where there is one, the real fact."""
    profile = PROFILES[key]
    assert profile.novelty is True
    assert len(profile.note) > 40
    assert profile.note.endswith(".")


@pytest.mark.parametrize("key", CREDIBLE_KEYS)
def test_credible_profiles_are_not_marked_novelty(key):
    assert PROFILES[key].novelty is False


def _range_from(text: str, pattern: str) -> tuple[float, float] | None:
    """The low and high of a quoted figure, which may be a single value.

    Zoom lenses genuinely quote ranges - 26-110mm, f/7-f/9.5 - so a
    profile's own number has to fall inside its description rather than
    equal the first figure in it.
    """
    found = [float(m) for m in re.findall(pattern, text)]
    return (min(found), max(found)) if found else None


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_f_number_agrees_with_the_lens_description(key):
    """A lens contradicting its own aperture is the exact inconsistency the
    linter hunts, so the source data must not contain one."""
    profile = PROFILES[key]
    quoted = _range_from(profile.lens_model, r"f/(\d+(?:\.\d+)?)")
    if quoted is None:
        return
    low, high = quoted
    assert low <= float(profile.f_number) <= high, (
        f"{key}: FNumber {profile.f_number} is outside {profile.lens_model!r}"
    )


# There is deliberately no matching focal-length check. "mm" in a lens
# description does not reliably mean focal length: DJI writes the 35mm
# equivalent (24mm) while FocalLength holds the true 12.29mm, exactly as a
# real Mavic file does, and the pinhole's 0.3mm is its aperture diameter.
# A test that had to special-case those would stop meaning anything.
# "f/N", by contrast, is unambiguous, which is why the check above stands.
