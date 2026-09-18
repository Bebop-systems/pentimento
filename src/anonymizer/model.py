"""Plain data structures. No I/O, no ExifTool knowledge."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# Groups ExifTool reports that are derived or filesystem-level rather than
# stored in the file's metadata. Deleting a Composite tag is meaningless -
# it is computed from other tags - so these are never edit targets.
DERIVED_GROUPS = frozenset({"Composite", "ExifTool", "File", "System"})

# Colour-management groups. Editing these changes how the image renders.
PROTECTED_GROUPS = frozenset({
    "ICC-header", "ICC_Profile", "ICC-view", "ICC-meas", "ICC-chrm",
})

UNEDITABLE_GROUPS = DERIVED_GROUPS | PROTECTED_GROUPS

# ExifTool reports MakerNote tags under a family-1 vendor group (Apple,
# Canon, ...), but the block is only writable as a whole, under the
# family-0 group MakerNotes. Deleting the sub-tags one by one silently
# does nothing, so a plan has to collapse them into MakerNotes:all.
MAKERNOTE_GROUPS = frozenset({
    "Apple", "Canon", "Casio", "DJI", "FLIR", "FujiFilm", "GE", "GoPro",
    "HP", "JVC", "Kodak", "Leica", "Minolta", "Motorola", "Nikon",
    "Olympus", "Panasonic", "Pentax", "PhaseOne", "Reconyx", "Ricoh",
    "Samsung", "Sanyo", "Sigma", "Sony", "MakerNotes", "MakerUnknown",
})


def groups_covered_by(key: str) -> frozenset[str] | None:
    """Which family-1 groups a `Group:all` deletion actually removes.

    Returns None when the key is not a group-wide deletion.
    """
    group, _, name = key.partition(":")
    if name.lower() != "all":
        return None
    if group.lower() == "makernotes":
        return MAKERNOTE_GROUPS
    return frozenset({group})


# Tags that ExifTool's AllDates shortcut moves as a unit.
_ALL_DATES = ("DateTimeOriginal", "CreateDate", "ModifyDate")


def _apply_shift(tags: dict[str, "Tag"], op: "EditOp") -> dict[str, "Tag"]:
    """Model an ExifTool date shift (`-AllDates+=3:0:0 0`) in a pending state.

    Shifting every date by the same amount is what keeps them coherent, so
    the preview has to show the shifted values rather than the originals.
    """
    from datetime import datetime, timedelta

    target = op.key.rstrip("+-")
    sign = 1 if op.key.endswith("+") else -1
    # ExifTool shift values are Y:M:D h:m:s, so days are the third field.
    try:
        days = int(str(op.value).split(" ")[0].split(":")[2])
    except (ValueError, AttributeError, IndexError):
        return tags
    names = _ALL_DATES if target == "AllDates" else (target.partition(":")[2] or target,)

    shifted = dict(tags)
    for key, tag in tags.items():
        if tag.name not in names:
            continue
        try:
            dt = datetime.strptime(str(tag.value)[:19], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
        moved = (dt + timedelta(days=sign * days)).strftime("%Y:%m:%d %H:%M:%S")
        shifted[key] = replace(tag, value=moved, display=moved)
    return shifted


@dataclass(frozen=True)
class Tag:
    group: str
    name: str
    value: Any
    display: str

    @property
    def key(self) -> str:
        return f"{self.group}:{self.name}"

    @property
    def editable(self) -> bool:
        return self.group not in UNEDITABLE_GROUPS


@dataclass(frozen=True)
class EditOp:
    key: str
    value: str | None  # None means delete

    @property
    def is_delete(self) -> bool:
        return self.value is None


@dataclass(frozen=True)
class EditPlan:
    """A set of tag edits, optionally with a raw ExifTool argument override.

    `raw_args` exists because a few ExifTool idioms are argument sequences
    rather than tag assignments - notably `-tagsfromfile @`, which restores
    named tags from the original file after a wholesale `-all=`.
    """
    ops: tuple[EditOp, ...] = ()
    raw_args: tuple[str, ...] = ()

    def __init__(self, ops=(), raw_args=()):
        object.__setattr__(self, "ops", tuple(ops))
        object.__setattr__(self, "raw_args", tuple(raw_args))

    def deletions(self) -> list[str]:
        return [op.key for op in self.ops if op.is_delete]

    def assignments(self) -> dict[str, str]:
        return {op.key: op.value for op in self.ops if not op.is_delete}

    def to_args(self) -> list[str]:
        if self.raw_args:
            return list(self.raw_args)
        return [
            f"-{op.key}=" + ("" if op.is_delete else str(op.value))
            for op in self.ops
        ]

    def merged(self, other: "EditPlan") -> "EditPlan":
        """Combine two plans; ops in `other` override matching keys."""
        by_key: dict[str, EditOp] = {}
        for op in (*self.ops, *other.ops):
            by_key[op.key] = op
        return EditPlan(tuple(by_key.values()), other.raw_args or self.raw_args)

    def __bool__(self) -> bool:
        return bool(self.ops or self.raw_args)


@dataclass(frozen=True)
class TagSet:
    path: Path
    tags: dict[str, Tag] = field(default_factory=dict)

    @classmethod
    def from_exiftool(cls, path: Path, machine: dict, display: dict) -> "TagSet":
        tags: dict[str, Tag] = {}
        for key, value in machine.items():
            if key == "SourceFile" or ":" not in key:
                continue
            group, _, name = key.partition(":")
            shown = display.get(key, value)
            tags[key] = Tag(group, name, value, str(shown))
        return cls(path=Path(path), tags=tags)

    def get(self, key: str) -> Tag | None:
        return self.tags.get(key)

    def keys(self) -> set[str]:
        return set(self.tags)

    def by_name(self, name: str) -> Tag | None:
        """First stored tag matching a bare name, ignoring group.

        Derived groups are searched last, so a real stored value wins over
        the Composite tag computed from it.
        """
        fallback = None
        for tag in self.tags.values():
            if tag.name != name:
                continue
            if tag.group in DERIVED_GROUPS:
                fallback = fallback or tag
            else:
                return tag
        return fallback

    def editable_tags(self) -> list[Tag]:
        return [t for t in self.tags.values() if t.editable]

    def with_plan(self, plan: EditPlan) -> "TagSet":
        """The state this TagSet would have after `plan` applies.

        `Group:all` deletes every tag in that group; bare `all` deletes
        everything that is not protected.
        """
        tags = dict(self.tags)
        for op in plan.ops:
            if op.key.endswith(("+", "-")) and not op.is_delete:
                tags = _apply_shift(tags, op)
                continue
            group, _, name = op.key.partition(":")
            if op.is_delete:
                covered = groups_covered_by(op.key)
                if op.key.lower() == "all":
                    tags = {
                        k: t for k, t in tags.items()
                        if t.group in UNEDITABLE_GROUPS
                    }
                elif covered is not None:
                    tags = {k: t for k, t in tags.items() if t.group not in covered}
                else:
                    tags.pop(op.key, None)
            else:
                existing = tags.get(op.key)
                if existing is None:
                    tags[op.key] = Tag(group or "EXIF", name or group,
                                       op.value, str(op.value))
                else:
                    tags[op.key] = replace(
                        existing, value=op.value, display=str(op.value)
                    )
        return TagSet(path=self.path, tags=tags)
