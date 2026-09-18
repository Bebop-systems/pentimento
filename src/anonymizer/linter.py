"""Detect contradictions in a file's metadata.

A file whose metadata contradicts itself is more conspicuous than one that
was never edited at all. These rules look for the specific inconsistencies
a careless edit leaves behind.

Each rule is an independent function returning zero or more Findings, so
adding one requires no change to a dispatcher.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .model import TagSet

_VENDOR_GROUPS = {
    "Apple": "apple", "Canon": "canon", "Nikon": "nikon",
    "Sony": "sony", "Panasonic": "panasonic", "Olympus": "olympus",
    "FujiFilm": "fujifilm", "Pentax": "pentax", "Samsung": "samsung",
}

# Earliest iOS major version each iPhone generation shipped with.
_MODEL_MIN_IOS = {
    "iPhone 17": 26, "iPhone 16": 18, "iPhone 15": 17, "iPhone 14": 16,
    "iPhone 13": 15, "iPhone 12": 14, "iPhone 11": 13,
    "iPhone XS": 12, "iPhone XR": 12, "iPhone X": 11, "iPhone 8": 11,
}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str  # "warning" | "note"
    message: str


def _value(tagset: TagSet, name: str):
    tag = tagset.by_name(name)
    return None if tag is None else tag.value


def _parse_dt(value) -> datetime | None:
    if value in (None, ""):
        return None
    text = re.split(r"[+\-]\d{2}:\d{2}$", str(value).strip())[0].strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y:%m:%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def rule_partial_gps(ts: TagSet) -> list[Finding]:
    names = {k.split(":", 1)[1] for k in ts.keys() if k.startswith("GPS:")}
    if not names:
        return []
    out = []
    for coord in ("GPSLatitude", "GPSLongitude"):
        if coord in names and f"{coord}Ref" not in names:
            out.append(Finding(
                "partial_gps", "warning",
                f"{coord} is present but {coord}Ref is missing, "
                "which is not a state a camera produces",
            ))
    coords = {"GPSLatitude", "GPSLongitude"} & names
    residue = names - {"GPSLatitude", "GPSLongitude", "GPSLatitudeRef", "GPSLongitudeRef"}
    if not coords and residue:
        out.append(Finding(
            "partial_gps", "warning",
            "Coordinates were removed but GPS residue remains: "
            + ", ".join(sorted(residue)),
        ))
    return out


def rule_orphan_makernote(ts: TagSet) -> list[Finding]:
    make = _value(ts, "Make")
    if make is None:
        return []
    make_text = str(make).lower()
    out = []
    for group, vendor in _VENDOR_GROUPS.items():
        if any(k.startswith(f"{group}:") for k in ts.keys()) and vendor not in make_text:
            out.append(Finding(
                "orphan_makernote", "warning",
                f"A {group} MakerNote is present but Make says {make!r}",
            ))
    return out


def rule_filename_mismatch(ts: TagSet) -> list[Finding]:
    name = ts.path.name.upper()
    make = _value(ts, "Make")
    if make is None:
        return []
    make_text = str(make).lower()
    for pattern, vendor in (
        (r"^IMG_\d+\.(HEIC|JPG|JPEG|PNG|MOV)$", "apple"),
        (r"^DSC_?\d+", "nikon"),
        (r"^PXL_\d+", "google"),
    ):
        if re.match(pattern, name) and vendor not in make_text:
            return [Finding(
                "filename_mismatch", "note",
                f"The filename {ts.path.name!r} suggests {vendor} "
                f"but Make says {make!r}",
            )]
    return []


def rule_round_timestamp(ts: TagSet) -> list[Finding]:
    value = _value(ts, "DateTimeOriginal")
    if value is None:
        return []
    if re.search(r"\b(00|12):00:00(\b|$)", str(value)):
        if ts.by_name("SubSecTimeOriginal") is None:
            return [Finding(
                "round_timestamp", "note",
                f"{value!r} is suspiciously round and carries no subseconds, "
                "which reads as hand-typed",
            )]
    return []


def rule_time_ordering(ts: TagSet) -> list[Finding]:
    original = _parse_dt(_value(ts, "DateTimeOriginal"))
    modified = _parse_dt(_value(ts, "ModifyDate"))
    if original and modified and modified < original:
        return [Finding(
            "time_ordering", "warning",
            f"ModifyDate ({modified:%Y-%m-%d %H:%M:%S}) precedes "
            f"DateTimeOriginal ({original:%Y-%m-%d %H:%M:%S})",
        )]
    return []


def rule_serial_residue(ts: TagSet) -> list[Finding]:
    out = []
    for tag in ts.tags.values():
        if not tag.editable:
            continue
        if "serial" in tag.name.lower() and tag.value not in (None, "", 0):
            out.append(Finding(
                "serial_residue", "warning",
                f"{tag.key} still carries {tag.display!r}",
            ))
    return out


def rule_model_software(ts: TagSet) -> list[Finding]:
    model = _value(ts, "Model")
    software = _value(ts, "Software")
    if model is None or software is None:
        return []
    match = re.match(r"^(\d+)", str(software).strip())
    if not match:
        return []
    major = int(match.group(1))
    for prefix, minimum in _MODEL_MIN_IOS.items():
        if str(model).startswith(prefix) and major < minimum:
            return [Finding(
                "model_software", "warning",
                f"{model} shipped with iOS {minimum} or later, "
                f"but Software says {software!r}",
            )]
    return []


def rule_model_lens(ts: TagSet) -> list[Finding]:
    model = _value(ts, "Model")
    lens = _value(ts, "LensModel")
    if model is None or lens is None:
        return []
    lens_text, model_text = str(lens), str(model)
    if not model_text.startswith("iPhone") or "iPhone" not in lens_text:
        return []
    head = re.split(r"\s+(back|front)\b", lens_text)[0].strip()
    if head and head != model_text:
        return [Finding(
            "model_lens", "warning",
            f"LensModel describes a {head!r} but Model says {model_text!r}",
        )]
    return []


def rule_dimension_coherence(ts: TagSet) -> list[Finding]:
    out = []
    for exif_name, real_name in (
        ("ExifImageWidth", "ImageWidth"), ("ExifImageHeight", "ImageHeight")
    ):
        exif_tag = ts.by_name(exif_name)
        real_tag = ts.get(f"File:{real_name}")
        if exif_tag is None or real_tag is None:
            continue
        try:
            if int(exif_tag.value) != int(real_tag.value):
                out.append(Finding(
                    "dimension_coherence", "warning",
                    f"{exif_name} ({exif_tag.value}) disagrees with the "
                    f"actual {real_name} ({real_tag.value})",
                ))
        except (TypeError, ValueError):
            continue
    return out


def rule_utc_math(ts: TagSet) -> list[Finding]:
    gps_dt = _parse_dt(_value(ts, "GPSDateTime"))
    local = _parse_dt(_value(ts, "DateTimeOriginal"))
    offset = _value(ts, "OffsetTimeOriginal")
    if not (gps_dt and local and offset):
        return []
    match = re.match(r"([+-])(\d{2}):(\d{2})", str(offset))
    if not match:
        return []
    sign = 1 if match.group(1) == "+" else -1
    delta = sign * (int(match.group(2)) * 3600 + int(match.group(3)) * 60)
    if abs((local.timestamp() - delta) - gps_dt.timestamp()) > 300:
        return [Finding(
            "utc_math", "warning",
            f"GPSDateTime, DateTimeOriginal and OffsetTimeOriginal "
            f"({offset}) do not reconcile as the same moment",
        )]
    return []


RULES = (
    rule_partial_gps,
    rule_orphan_makernote,
    rule_filename_mismatch,
    rule_round_timestamp,
    rule_time_ordering,
    rule_serial_residue,
    rule_model_software,
    rule_model_lens,
    rule_dimension_coherence,
    rule_utc_math,
)


def lint(tagset: TagSet) -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        try:
            findings.extend(rule(tagset))
        except Exception:
            # A rule must never break the pipeline.
            continue
    findings.sort(key=lambda f: (f.severity != "warning", f.rule))
    return findings
