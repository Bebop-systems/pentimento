"""Preset -> EditPlan. Pure functions of a TagSet; no I/O.

Because a preset never touches a file, every one of them is testable
against a synthetic TagSet.
"""
from __future__ import annotations

from .model import MAKERNOTE_GROUPS, EditOp, EditPlan, TagSet
from .profiles import PROFILES
from .sensitivity import Category, classify

PRESETS: dict[str, str] = {
    "manual": "Change nothing automatically. You decide every field.",
    "plausible": (
        "Keep a coherent camera identity; drop location, serials, faces, "
        "captions and embedded thumbnails, as a device with location "
        "services off would present."
    ),
    "reprofile": (
        "Everything Plausible does, then adopt a different, internally "
        "consistent camera identity."
    ),
    "clean": (
        "Remove every tag that is not needed to render the image. "
        "Maximally private, and visibly scrubbed."
    ),
}

# Restored from the original after a wholesale -all=, because losing these
# changes how the file renders.
KEEP_ON_CLEAN: tuple[str, ...] = (
    "-Orientation",
    "-ColorSpace",
    "-ICC_Profile",
    "-ExifImageWidth",
    "-ExifImageHeight",
    "-XResolution",
    "-YResolution",
    "-ResolutionUnit",
)

# Categories each preset strips wholesale.
_STRIP: dict[str, tuple[Category, ...]] = {
    "plausible": (
        Category.LOCATION, Category.CONTENT,
        Category.SOFTWARE, Category.EMBEDDED,
    ),
    "reprofile": (
        Category.LOCATION, Category.CONTENT,
        Category.SOFTWARE, Category.EMBEDDED,
    ),
}

# Device-identity tags worth keeping for coherence. Make and Model are what
# make a file look like an ordinary photo; serials are what identify a
# specific unit, and those always go.
_KEEP_DEVICE_NAMES = frozenset({"Make", "Model", "LensMake", "LensModel", "LensInfo"})


def build_plan(tagset: TagSet, preset: str, options: dict | None = None) -> EditPlan:
    options = options or {}
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}")
    if preset == "manual":
        return EditPlan()
    if preset == "clean":
        return clean_plan(tagset)

    ops: list[EditOp] = [EditOp("GPS:all", None)]
    strip = _STRIP[preset]

    # Reprofile re-sets these by name. ExifTool reports them under family-1
    # groups (IFD0:Software) while assignments target family-0 (EXIF:Software),
    # so a deletion and its re-assignment look like different keys and both
    # survive a merge. Excluding them from deletion keeps the two consistent.
    respawned: frozenset[str] = frozenset()
    if preset == "reprofile":
        profile_ops = reprofile_ops(options.get("profile") or "iphone-15-pro")
        respawned = frozenset(op.key.partition(":")[2] for op in profile_ops)

    for tag in tagset.editable_tags():
        if tag.name in respawned:
            continue
        # A MakerNote block is writable only as a whole; deleting its
        # sub-tags individually is silently ignored by ExifTool.
        if tag.group in MAKERNOTE_GROUPS:
            ops.append(EditOp("MakerNotes:all", None))
            continue
        category = classify(tag)
        if category in strip:
            ops.append(EditOp(tag.key, None))
        elif category is Category.DEVICE and tag.name not in _KEEP_DEVICE_NAMES:
            ops.append(EditOp(tag.key, None))

    if preset == "reprofile":
        ops += profile_ops

    shift = int(options.get("time_shift_days") or 0)
    if shift:
        # AllDates moves DateTimeOriginal, CreateDate and ModifyDate as one
        # unit, so their relative ordering survives the shift. ExifTool's
        # shift value is Y:M:D h:m:s - days are the THIRD field, and putting
        # them first silently shifts by years instead.
        sign = "+" if shift > 0 else "-"
        ops.append(EditOp(f"AllDates{sign}", f"0:0:{abs(shift)} 0"))

    return EditPlan(ops).merged(EditPlan())


def clean_plan(tagset: TagSet) -> EditPlan:
    """`-all=` then restore the rendering-critical tags from the original.

    ExifTool spells this as an argument sequence rather than a set of tag
    assignments, which is what EditPlan.raw_args is for.

    The ops list enumerates the tags actually expected to disappear rather
    than a blanket `all`, because the restore step deliberately brings some
    back and the regression gate has to know which.
    """
    doomed = [
        EditOp(tag.key, None)
        for tag in tagset.editable_tags()
        if classify(tag) is not Category.BENIGN
    ]
    return EditPlan(
        ops=doomed,
        raw_args=["-all=", "-tagsfromfile", "@", *KEEP_ON_CLEAN],
    )


def reprofile_ops(profile_key: str) -> list[EditOp]:
    profile = PROFILES.get(profile_key)
    if profile is None:
        raise ValueError(f"Unknown profile: {profile_key}")
    return [
        EditOp("EXIF:Make", profile.make),
        EditOp("EXIF:Model", profile.model),
        EditOp("EXIF:LensModel", profile.lens_model),
        EditOp("EXIF:LensMake", profile.lens_make),
        EditOp("EXIF:FocalLength", profile.focal_length),
        EditOp("EXIF:FNumber", profile.f_number),
        EditOp("EXIF:Software", profile.software),
    ]


def plan_from_edits(edits: dict[str, str | None]) -> EditPlan:
    """Turn explicit per-field GUI edits into a plan.

    A value of None means delete; anything else is an assignment.
    """
    return EditPlan([EditOp(key, value) for key, value in edits.items()])
