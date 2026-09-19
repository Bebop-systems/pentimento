import pytest

from pentimento.model import Tag
from pentimento.sensitivity import RENDERING_CRITICAL, Category, classify


@pytest.mark.parametrize("group,name,expected", [
    ("GPS", "GPSLatitude", Category.LOCATION),
    ("GPS", "GPSAltitude", Category.LOCATION),
    ("GPS", "GPSDestBearing", Category.LOCATION),
    ("QuickTime", "GPSCoordinates", Category.LOCATION),
    ("XMP-iptcExt", "LocationCreatedCity", Category.LOCATION),
    ("ExifIFD", "SerialNumber", Category.DEVICE),
    ("ExifIFD", "BodySerialNumber", Category.DEVICE),
    ("ExifIFD", "OwnerName", Category.DEVICE),
    ("IFD0", "Artist", Category.DEVICE),
    ("ExifIFD", "DateTimeOriginal", Category.TIME),
    ("ExifIFD", "OffsetTimeOriginal", Category.TIME),
    ("ExifIFD", "SubSecTimeOriginal", Category.TIME),
    ("GPS", "GPSDateStamp", Category.TIME),
    ("XMP-mwg-rs", "RegionName", Category.CONTENT),
    ("IPTC", "Keywords", Category.CONTENT),
    ("IFD0", "Software", Category.SOFTWARE),
    ("XMP-xmpMM", "InstanceID", Category.SOFTWARE),
    ("IFD1", "ThumbnailImage", Category.EMBEDDED),
    ("ExifIFD", "PreviewImage", Category.EMBEDDED),
    ("IFD0", "Orientation", Category.BENIGN),
    ("ExifIFD", "ColorSpace", Category.BENIGN),
])
def test_classification(group, name, expected):
    assert classify(Tag(group, name, "x", "x")) == expected


def test_makernotes_group_is_content_by_default():
    assert classify(Tag("Apple", "SceneFlags", 1, "1")) == Category.CONTENT


def test_icc_profile_datetime_is_not_treated_as_time():
    """ProfileDateTime matches the *DateTime* glob, but deleting it would
    damage the colour profile."""
    assert classify(Tag("ICC-header", "ProfileDateTime", "x", "x")) == Category.BENIGN


def test_rendering_critical_never_classified_sensitive():
    for name in RENDERING_CRITICAL:
        assert classify(Tag("ExifIFD", name, "x", "x")) == Category.BENIGN
