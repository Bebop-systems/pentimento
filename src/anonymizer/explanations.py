"""Plain-English meaning for metadata fields.

Two sentences per field: what it is, and what someone inspecting the file
learns from it. A tag list is only useful if you know what the tags mean,
and almost nobody does.

Unknown tags fall back to a category-level explanation rather than showing
nothing, so every row in the interface says something.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from .model import Tag
from .sensitivity import Category, classify


@dataclass(frozen=True)
class Explanation:
    what: str
    reveals: str


# Fields the operator is most likely to care about, in their own words.
_EXACT: dict[str, Explanation] = {
    # --- location -----------------------------------------------------
    "GPSLatitude": Explanation(
        "The exact latitude where the shutter fired.",
        "With longitude this places you within a few metres. On a map it "
        "names the building, which is often a home, a workplace or a school.",
    ),
    "GPSLongitude": Explanation(
        "The exact longitude where the shutter fired.",
        "With latitude this places you within a few metres of the spot you "
        "were standing on.",
    ),
    "GPSAltitude": Explanation(
        "Height above sea level at the moment of capture.",
        "Narrows a location to a floor in a building, and can confirm or "
        "rule out a claimed place by comparing it against known terrain.",
    ),
    "GPSHPositioningError": Explanation(
        "How accurate the phone believed its own fix was, in metres.",
        "A small number means a confident outdoor lock; a large one suggests "
        "indoors or an assisted fix. It tells an inspector how much to trust "
        "the coordinates.",
    ),
    "GPSImgDirection": Explanation(
        "The compass direction the camera was pointing.",
        "With coordinates this reconstructs your exact vantage point and "
        "what you were looking at.",
    ),
    "GPSDestBearing": Explanation(
        "The compass bearing the device recorded alongside the shot.",
        "Another angle on which way you were facing when you took it.",
    ),
    "GPSSpeed": Explanation(
        "How fast the camera was moving.",
        "Separates a photo taken standing still from one taken out of a "
        "moving car, bus or train.",
    ),
    "GPSDateStamp": Explanation(
        "The date according to the GPS satellites, always in UTC.",
        "An independent clock. If it disagrees with the local timestamp, "
        "the file has been edited.",
    ),
    "GPSTimeStamp": Explanation(
        "The time according to the GPS satellites, always in UTC.",
        "Checked against the local time and timezone offset. The three have "
        "to reconcile, and a careless edit makes them disagree.",
    ),
    "GPSPosition": Explanation(
        "Latitude and longitude combined into one readable coordinate.",
        "Computed from the stored values, so it disappears when they do.",
    ),

    # --- device identity ----------------------------------------------
    "Make": Explanation(
        "The manufacturer of the camera.",
        "The first thing any inspector reads. It has to agree with the "
        "model, the lens and the MakerNote, or the file looks edited.",
    ),
    "Model": Explanation(
        "The camera or phone model.",
        "Narrows you to owners of one device. Combined with a serial "
        "number it identifies a specific unit rather than a product line.",
    ),
    "SerialNumber": Explanation(
        "A unique number identifying this exact camera body.",
        "Links every photo that camera ever took to each other. If the "
        "camera was registered, insured or bought with a card, it links "
        "them to you by name.",
    ),
    "BodySerialNumber": Explanation(
        "A unique number identifying this exact camera body.",
        "The single most identifying field in a photo. It ties together "
        "every image from the same device, across accounts and years.",
    ),
    "LensSerialNumber": Explanation(
        "A unique number identifying this exact lens.",
        "Identifies your equipment even if the body is changed, and "
        "survives in photos where the body serial was removed.",
    ),
    "OwnerName": Explanation(
        "A name stored in the camera's settings.",
        "Usually the owner's real name, typed in once during setup and "
        "then forgotten about for years.",
    ),
    "Artist": Explanation(
        "A name the camera or editing software stamped into the file.",
        "Frequently a real name. Photo software often fills it from your "
        "account without telling you.",
    ),
    "Copyright": Explanation(
        "A copyright line stored in the file.",
        "Normally contains a real name or business name, and sometimes "
        "contact details.",
    ),
    "HostComputer": Explanation(
        "The device that processed the file.",
        "On Apple devices this names the phone or Mac. It is routinely "
        "missed when Make and Model are cleaned, and gives the same answer.",
    ),
    "ImageUniqueID": Explanation(
        "A unique identifier the camera assigned to this image.",
        "Lets two copies of a photo be matched even after renaming, "
        "resizing or re-uploading.",
    ),

    # --- time ---------------------------------------------------------
    "DateTimeOriginal": Explanation(
        "When the shutter fired, in the camera's local time.",
        "Places you somewhere at a specific minute. Combined with location "
        "across several photos it becomes a movement history.",
    ),
    "CreateDate": Explanation(
        "When this file was created.",
        "Normally identical to the capture time. A gap between them "
        "suggests the file was exported or converted.",
    ),
    "ModifyDate": Explanation(
        "When the file was last written.",
        "If it is later than the capture time the file has been edited. "
        "If it is earlier, something has been tampered with clumsily.",
    ),
    "OffsetTime": Explanation(
        "The timezone the camera clock was set to.",
        "Reveals roughly what part of the world you were in, even after "
        "the coordinates are gone.",
    ),
    "OffsetTimeOriginal": Explanation(
        "The timezone in effect when the photo was taken.",
        "Survives a location scrub and still narrows you to a band of the "
        "globe. It also has to reconcile with the GPS clock.",
    ),
    "SubSecTimeOriginal": Explanation(
        "Fractions of a second within the capture timestamp.",
        "A quiet authenticity signal: most cameras write it, and most "
        "hand-typed timestamps do not have one.",
    ),

    # --- content ------------------------------------------------------
    "RegionName": Explanation(
        "The name of a person your photo software recognised in the frame.",
        "This is a real name, written into the file, usually a friend or "
        "family member who never agreed to be tagged.",
    ),
    "RegionInfo": Explanation(
        "Face regions your photo software detected, with names attached.",
        "Holds both where each face is in the picture and who the software "
        "believes it is.",
    ),
    "PersonInImage": Explanation(
        "Names of people recorded as appearing in the photo.",
        "Identifies other people, not just you.",
    ),
    "Keywords": Explanation(
        "Tags you or your software attached to the photo.",
        "Free text is the least predictable leak in a file, because it can "
        "contain anything you once typed.",
    ),
    "UserComment": Explanation(
        "A free-text note stored in the file.",
        "Whatever was typed there, carried along invisibly.",
    ),
    "ImageDescription": Explanation(
        "A caption stored in the file.",
        "Often auto-filled by editing software with a filename or path "
        "that reveals your folder structure or username.",
    ),
    "Caption-Abstract": Explanation(
        "A caption field used by publishing software.",
        "Can hold notes intended for an editor rather than the public.",
    ),

    # --- software -----------------------------------------------------
    "Software": Explanation(
        "The operating system or app version that wrote the file.",
        "Narrows your device and how up to date it is. It also has to be a "
        "version that actually existed for the claimed model.",
    ),
    "ProcessingSoftware": Explanation(
        "The program that last processed the image.",
        "Shows the file has been through an editor, and which one.",
    ),
    "DocumentID": Explanation(
        "An identifier that follows this image across edits.",
        "Links a published file back to the original and to every other "
        "export from the same editing session.",
    ),
    "InstanceID": Explanation(
        "An identifier for this particular saved version.",
        "Ties separate uploads together as versions of one document.",
    ),
    "HistorySoftwareAgent": Explanation(
        "An entry in the edit log your software kept inside the file.",
        "The history can list every tool used and every save, sometimes "
        "with timestamps and a username.",
    ),
    "XMPToolkit": Explanation(
        "The library version that wrote the XMP metadata block.",
        "Expected on any camera file. Its absence is more unusual than its "
        "presence, so this tool leaves it alone.",
    ),

    # --- embedded images ----------------------------------------------
    "ThumbnailImage": Explanation(
        "A small copy of the picture stored inside the file.",
        "Frequently the ORIGINAL frame from before you cropped or redacted "
        "anything. Viewers show the large image while the thumbnail still "
        "holds what you thought you removed.",
    ),
    "PreviewImage": Explanation(
        "A medium-sized copy of the picture stored inside the file.",
        "Same risk as the thumbnail, at higher resolution: it can preserve "
        "detail the visible image no longer has.",
    ),

    # --- benign but worth explaining ----------------------------------
    "Orientation": Explanation(
        "Which way up the image should be displayed.",
        "Harmless. Removing it turns your photo sideways, so this tool "
        "always keeps it.",
    ),
    "ColorSpace": Explanation(
        "How the colour values should be interpreted.",
        "Harmless. Removing it makes colours shift, so it is always kept.",
    ),
    "ICC_Profile": Explanation(
        "A colour profile describing how to render the image accurately.",
        "Harmless. Removing it changes how the photo looks on screen.",
    ),
    "HDRGainMapVersion": Explanation(
        "Data telling HDR displays how much to brighten parts of the image.",
        "This is picture data rather than metadata. Removing it changes how "
        "the photo renders, so it is kept.",
    ),
    "ExifImageWidth": Explanation(
        "The image width as recorded in the metadata.",
        "Harmless by itself, but if it disagrees with the real pixel width "
        "the file has been altered carelessly.",
    ),
    "ExifImageHeight": Explanation(
        "The image height as recorded in the metadata.",
        "Harmless by itself, but it has to match the real pixel height.",
    ),
    "FNumber": Explanation(
        "The aperture the lens was set to.",
        "Mostly harmless, but it has to be a value the claimed camera can "
        "actually produce.",
    ),
    "FocalLength": Explanation(
        "The focal length of the lens, in millimetres.",
        "Has to match the optics of the claimed model. A phone that "
        "reports a focal length its camera does not have is a giveaway.",
    ),
    "ExposureTime": Explanation(
        "How long the shutter stayed open.",
        "Ordinary exposure data. Useful to an inspector only for judging "
        "whether the settings are plausible together.",
    ),
    "ISO": Explanation(
        "The sensor's sensitivity setting.",
        "Ordinary exposure data, and a rough hint about the lighting.",
    ),
    "LensModel": Explanation(
        "Which lens took the photograph.",
        "On a phone this is fixed by the model, so the two must agree. A "
        "mismatch is one of the easiest edits to spot.",
    ),
    "LensMake": Explanation(
        "Who made the lens.",
        "Has to agree with the camera manufacturer.",
    ),
    "FileModifyDate": Explanation(
        "When your filesystem last wrote this file.",
        "Comes from your disk rather than from inside the photo. It changes "
        "when you copy the file and is not carried when you upload it.",
    ),
    "FileType": Explanation(
        "The file format.",
        "Not sensitive. Shown so you can confirm the output kept the same "
        "format as the input.",
    ),
}

# Matched in order when no exact entry exists.
_GLOBS: tuple[tuple[str, Explanation], ...] = (
    ("GPS*Ref", Explanation(
        "Which hemisphere or direction the neighbouring GPS value refers to.",
        "Meaningless alone, but a coordinate left without its reference is "
        "a state no camera produces, and marks the file as edited.",
    )),
    ("GPS*", Explanation(
        "A supporting value recorded by the phone's location hardware.",
        "Part of the location record. Leaving any of it behind after "
        "removing the coordinates is itself a signal.",
    )),
    ("*SerialNumber*", Explanation(
        "A unique number identifying a specific piece of hardware.",
        "Ties every photo from that device together, and often to you.",
    )),
    ("SubSecTime*", Explanation(
        "Fractions of a second within a timestamp.",
        "A small authenticity signal that hand-edited times usually lack.",
    )),
    ("OffsetTime*", Explanation(
        "The timezone the camera clock was set to.",
        "Narrows where in the world you were, even without coordinates.",
    )),
    ("History*", Explanation(
        "An entry in the edit history stored inside the file.",
        "The history can name every tool and every save.",
    )),
    ("Region*", Explanation(
        "Face-detection data, including names where your software knew them.",
        "Identifies other people in your photo.",
    )),
    ("Thumbnail*", Explanation(
        "Data describing the small preview copy stored inside the file.",
        "The preview is often the frame from before you edited the photo.",
    )),
    ("Preview*", Explanation(
        "Data describing a preview copy stored inside the file.",
        "The preview can retain detail the visible image no longer has.",
    )),
)

# What a whole vendor MakerNote block amounts to.
_MAKERNOTE = Explanation(
    "One value from the camera maker's private block: scene analysis, "
    "focus and exposure telemetry, and sometimes motion or location hints.",
    "Undocumented and rarely inspected, which is exactly why it survives "
    "most scrubbing. It can hold more about the moment of capture than "
    "every visible tag combined, and it is only removable as a whole.",
)

_BY_CATEGORY: dict[Category, Explanation] = {
    Category.LOCATION: Explanation(
        "A value describing where the photo was taken.",
        "Contributes to pinpointing the place.",
    ),
    Category.DEVICE: Explanation(
        "A value identifying the camera or its owner.",
        "Helps narrow the file down to one device or one person.",
    ),
    Category.TIME: Explanation(
        "A value describing when the photo was taken.",
        "Places you somewhere at a particular moment.",
    ),
    Category.CONTENT: Explanation(
        "A value describing what is in the photo.",
        "Can name people or describe the subject in your own words.",
    ),
    Category.SOFTWARE: Explanation(
        "A value describing what created or edited the file.",
        "Shows the file's editing history and the tools involved.",
    ),
    Category.EMBEDDED: Explanation(
        "A copy of the image stored inside the file.",
        "May still show what a crop or redaction removed.",
    ),
    Category.BENIGN: Explanation(
        "A technical value describing how to decode or display the image.",
        "Not identifying. Removing it risks changing how the photo looks.",
    ),
}

CATEGORY_SUMMARY: dict[Category, str] = {
    Category.LOCATION: "Where you were standing.",
    Category.DEVICE: "Which camera, and whose.",
    Category.TIME: "When you were there.",
    Category.CONTENT: "What is in the picture, including people's names.",
    Category.SOFTWARE: "What has edited the file.",
    Category.EMBEDDED: "Older copies of the picture hidden inside it.",
    Category.BENIGN: "How to decode and display the image.",
}


def explain(tag: Tag) -> Explanation:
    from .model import MAKERNOTE_GROUPS

    exact = _EXACT.get(tag.name)
    if exact is not None:
        return exact
    if tag.group in MAKERNOTE_GROUPS:
        return _MAKERNOTE
    for pattern, explanation in _GLOBS:
        if fnmatch.fnmatch(tag.name, pattern):
            return explanation
    return _BY_CATEGORY[classify(tag)]
