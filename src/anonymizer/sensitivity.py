"""Which tags identify the operator, their device, or their subject."""
from __future__ import annotations

import fnmatch
from enum import StrEnum

from .model import PROTECTED_GROUPS, Tag, TagSet


class Category(StrEnum):
    LOCATION = "location"
    DEVICE = "device"
    TIME = "time"
    CONTENT = "content"
    SOFTWARE = "software"
    EMBEDDED = "embedded"
    BENIGN = "benign"


RISK_ORDER = (
    Category.LOCATION, Category.DEVICE, Category.CONTENT,
    Category.TIME, Category.SOFTWARE, Category.EMBEDDED, Category.BENIGN,
)

# Tags that affect how the image renders. Never sensitive, and preserved
# even by the most aggressive preset.
RENDERING_CRITICAL = frozenset({
    "Orientation", "ColorSpace", "ICC_Profile", "ProfileDescription",
    "ExifImageWidth", "ExifImageHeight", "ImageWidth", "ImageHeight",
    "Rotation", "BitsPerSample", "SamplesPerPixel", "PhotometricInterpretation",
    "YCbCrPositioning", "YCbCrSubSampling", "ComponentsConfiguration",
    "XResolution", "YResolution", "ResolutionUnit", "InteropIndex",
    "Gamma", "PrimaryChromaticities", "WhitePoint", "TransferFunction",
    "ExifVersion", "FlashpixVersion", "Compression", "EncodingProcess",
})

_EXACT: dict[str, Category] = {}


def _register(category: Category, *names: str) -> None:
    for name in names:
        _EXACT[name] = category


_register(
    Category.LOCATION,
    "GPSLatitude", "GPSLongitude", "GPSAltitude", "GPSLatitudeRef",
    "GPSLongitudeRef", "GPSAltitudeRef", "GPSPosition", "GPSCoordinates",
    "GPSHPositioningError", "GPSDestLatitude", "GPSDestLongitude",
    "GPSImgDirection", "GPSImgDirectionRef", "GPSSpeed", "GPSSpeedRef",
    "GPSTrack", "GPSTrackRef", "GPSDestBearing", "GPSDestBearingRef",
    "GPSAreaInformation", "GPSMapDatum", "GPSProcessingMethod", "GPSStatus",
    "LocationCreatedCity", "LocationCreatedCountryName",
    "LocationCreatedSublocation", "LocationCreatedProvinceState",
    "LocationShownCity", "LocationShownCountryName",
    "Country", "Province-State", "City", "Sub-location", "CountryCode",
    "LocationName", "SubjectLocation", "LocationTaken",
)
_register(
    Category.DEVICE,
    "SerialNumber", "BodySerialNumber", "LensSerialNumber",
    "InternalSerialNumber", "CameraSerialNumber", "OwnerName",
    "CameraOwnerName", "Artist", "Creator", "By-line", "By-lineTitle",
    "HostComputer", "CameraID", "ImageUniqueID", "Copyright", "Rights",
    "CreatorWorkEmail", "CreatorWorkURL", "Credit", "Source", "Contact",
)
_register(
    Category.TIME,
    "DateTimeOriginal", "CreateDate", "ModifyDate", "DateCreated",
    "OffsetTime", "OffsetTimeOriginal", "OffsetTimeDigitized",
    "SubSecTime", "SubSecTimeOriginal", "SubSecTimeDigitized",
    "SubSecCreateDate", "SubSecDateTimeOriginal", "SubSecModifyDate",
    "GPSDateStamp", "GPSTimeStamp", "GPSDateTime", "TimeZoneOffset",
    "DigitalCreationDate", "DigitalCreationTime", "MediaCreateDate",
    "MediaModifyDate", "TrackCreateDate", "TrackModifyDate", "TimeCreated",
)
_register(
    Category.CONTENT,
    "RegionName", "RegionType", "RegionAreaX", "RegionAreaY", "RegionInfo",
    "RegionPersonDisplayName", "Keywords", "Subject", "Caption-Abstract",
    "Description", "Title", "ObjectName", "SpecialInstructions",
    "UserComment", "ImageDescription", "Rating", "RatingPercent", "Label",
    "PersonInImage", "SceneCaptureType", "Headline", "Category",
)
_register(
    Category.SOFTWARE,
    "Software", "ProcessingSoftware", "CreatorTool", "HistorySoftwareAgent",
    "HistoryAction", "HistoryWhen", "HistoryChanged", "HistoryInstanceID",
    "DocumentID", "InstanceID", "OriginalDocumentID", "DerivedFromInstanceID",
    "DerivedFromDocumentID", "ApplicationRecordVersion", "OriginatingProgram",
    "ProgramVersion", "Encoder", "WritingApp", "XMPToolkit",
)
_register(
    Category.EMBEDDED,
    "ThumbnailImage", "PreviewImage", "OtherImage", "JpgFromRaw",
    "ThumbnailTIFF", "PhotoshopThumbnail", "PreviewPICT", "EmbeddedImage",
    "ThumbnailOffset", "ThumbnailLength", "PreviewImageStart",
    "PreviewImageLength", "OtherImageStart", "OtherImageLength",
)

# Checked in order after an exact miss.
_GLOBS: tuple[tuple[str, Category], ...] = (
    ("GPS*", Category.LOCATION),
    ("*SerialNumber*", Category.DEVICE),
    ("History*", Category.SOFTWARE),
    ("Region*", Category.CONTENT),
    ("Thumbnail*", Category.EMBEDDED),
    ("Preview*", Category.EMBEDDED),
    ("OffsetTime*", Category.TIME),
    ("SubSecTime*", Category.TIME),
    ("*DateTime*", Category.TIME),
)

# Group-level fallback. MakerNotes are vendor blobs holding scene analysis,
# face detection and sometimes location, so they default to CONTENT.
_GROUP_FALLBACK: dict[str, Category] = {
    "GPS": Category.LOCATION,
    "Apple": Category.CONTENT,
    "Canon": Category.CONTENT,
    "Nikon": Category.CONTENT,
    "Sony": Category.CONTENT,
    "Panasonic": Category.CONTENT,
    "Olympus": Category.CONTENT,
    "MakerNotes": Category.CONTENT,
    "XMP-mwg-rs": Category.CONTENT,
    "XMP-xmpMM": Category.SOFTWARE,
}


def classify(tag: Tag) -> Category:
    # Colour-management groups carry a ProfileDateTime that would otherwise
    # match the *DateTime* glob; deleting it would damage the ICC profile.
    if tag.group in PROTECTED_GROUPS:
        return Category.BENIGN
    if tag.name in RENDERING_CRITICAL:
        return Category.BENIGN
    exact = _EXACT.get(tag.name)
    if exact is not None:
        return exact
    for pattern, category in _GLOBS:
        if fnmatch.fnmatch(tag.name, pattern):
            return category
    return _GROUP_FALLBACK.get(tag.group, Category.BENIGN)


def categorize(tagset: TagSet) -> dict[Category, list[Tag]]:
    out: dict[Category, list[Tag]] = {c: [] for c in Category}
    for tag in tagset.tags.values():
        out[classify(tag)].append(tag)
    for tags in out.values():
        tags.sort(key=lambda t: t.key)
    return out
