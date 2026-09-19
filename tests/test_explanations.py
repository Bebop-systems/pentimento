import pytest

from pentimento.explanations import CATEGORY_SUMMARY, explain
from pentimento.model import Tag
from pentimento.sensitivity import Category


@pytest.mark.parametrize("group,name", [
    ("GPS", "GPSLatitude"),
    ("GPS", "GPSSpeed"),
    ("IFD0", "Make"),
    ("ExifIFD", "SerialNumber"),
    ("ExifIFD", "DateTimeOriginal"),
    ("XMP-mwg-rs", "RegionName"),
    ("IFD0", "Software"),
    ("IFD1", "ThumbnailImage"),
    ("IFD0", "Orientation"),
])
def test_known_tags_have_both_sentences(group, name):
    explanation = explain(Tag(group, name, "x", "x"))
    assert explanation.what.endswith(".")
    assert explanation.reveals.endswith(".")
    assert len(explanation.what) > 20
    assert len(explanation.reveals) > 20


def test_unknown_tag_falls_back_to_its_category():
    explanation = explain(Tag("GPS", "GPSSomethingNew", 1, "1"))
    assert "location" in explanation.reveals.lower() or "location" in explanation.what.lower()


def test_makernote_tags_share_one_explanation():
    a = explain(Tag("Apple", "AEStable", 1, "1"))
    b = explain(Tag("Apple", "AFPerformance", 1, "1"))
    assert a == b
    assert "removable as a whole" in a.reveals


def test_glob_matches_gps_reference_fields():
    explanation = explain(Tag("GPS", "GPSLatitudeRef", "N", "North"))
    assert "hemisphere" in explanation.what


def test_every_category_has_a_summary():
    for category in Category:
        assert CATEGORY_SUMMARY[category]


def test_thumbnail_warning_is_explicit():
    """The pre-edit-frame risk is the point of the field being listed."""
    assert "ORIGINAL" in explain(Tag("IFD1", "ThumbnailImage", "x", "x")).reveals
