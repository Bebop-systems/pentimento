"""Profiles, including the deliberately silly ones.

A novelty profile is absurd about which camera it claims and rigorous about
everything else: its numeric fields have to stay real numbers or ExifTool
cannot write them and the gates cannot pass.
"""
import re

import pytest

from anonymizer.profiles import CREDIBLE_KEYS, NOVELTY_KEYS, PROFILES

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


def test_lens_text_mentions_its_own_f_number():
    """A lens description contradicting its own FNumber is the exact
    inconsistency the linter hunts, so the source data must not contain one."""
    for key, profile in PROFILES.items():
        match = re.search(r"f/(\d+(?:\.\d+)?)", profile.lens_model)
        if match:
            assert float(match.group(1)) == float(profile.f_number), key
