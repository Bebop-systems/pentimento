from pathlib import Path

import pytest

from pentimento.model import TagSet
from pentimento.presets import PRESETS, build_plan, plan_from_edits
from pentimento.profiles import PROFILES


def _ts(name="a.heic", **kw):
    m = {k.replace("__", ":"): v for k, v in kw.items()}
    return TagSet.from_exiftool(Path(name), m, m)


def test_presets_are_registered():
    assert set(PRESETS) == {"clean", "plausible", "reprofile", "manual"}


def test_unknown_preset_rejected():
    with pytest.raises(ValueError, match="Unknown preset"):
        build_plan(_ts(), "nope", {})


def test_manual_produces_empty_plan():
    assert build_plan(_ts(EXIF__Model="iPhone"), "manual", {}).to_args() == []


def test_clean_deletes_all_then_restores_rendering_tags():
    args = build_plan(_ts(EXIF__Model="iPhone"), "clean", {}).to_args()
    assert args[0] == "-all="
    assert "-tagsfromfile" in args and "@" in args
    assert "-Orientation" in args
    assert "-ICC_Profile" in args


def test_plausible_removes_gps_entirely():
    ts = _ts(GPS__GPSLatitude=47.6, GPS__GPSLatitudeRef="N", EXIF__Model="iPhone 15 Pro")
    assert "-GPS:all=" in build_plan(ts, "plausible", {}).to_args()


def test_plausible_keeps_camera_identity():
    ts = _ts(IFD0__Make="Apple", IFD0__Model="iPhone 15 Pro", GPS__GPSLatitude=47.6)
    pending = ts.with_plan(build_plan(ts, "plausible", {}))
    assert pending.get("IFD0:Model").value == "iPhone 15 Pro"
    assert pending.get("IFD0:Make").value == "Apple"


def test_plausible_removes_serials_and_faces():
    ts = _ts(ExifIFD__SerialNumber="F2LW1", **{"XMP-mwg-rs__RegionName": "Alice"})
    deleted = set(build_plan(ts, "plausible", {}).deletions())
    assert "ExifIFD:SerialNumber" in deleted
    assert "XMP-mwg-rs:RegionName" in deleted


def test_plausible_removes_embedded_thumbnails():
    ts = _ts(IFD1__ThumbnailImage="(binary)")
    assert "IFD1:ThumbnailImage" in build_plan(ts, "plausible", {}).deletions()


def test_plausible_never_targets_derived_tags():
    """Composite tags are computed, so deleting them is meaningless."""
    ts = _ts(Composite__GPSPosition="36 N, 83 W", File__FileType="HEIC")
    assert build_plan(ts, "plausible", {}).deletions() == ["GPS:all"]


def test_plausible_leaves_colour_profile_alone():
    ts = _ts(**{"ICC-header__ProfileDateTime": "2022:01:01 00:00:00"})
    assert "ICC-header:ProfileDateTime" not in build_plan(ts, "plausible", {}).deletions()


def test_reprofile_rewrites_identity_consistently():
    ts = _ts(IFD0__Make="Apple", IFD0__Model="iPhone 15 Pro")
    plan = build_plan(ts, "reprofile", {"profile": "pixel-8"})
    assigned = plan.assignments()
    p = PROFILES["pixel-8"]
    assert assigned["EXIF:Make"] == p.make
    assert assigned["EXIF:Model"] == p.model
    assert assigned["EXIF:LensModel"] == p.lens_model
    assert assigned["EXIF:Software"] == p.software


def test_reprofile_rejects_unknown_profile():
    with pytest.raises(ValueError, match="Unknown profile"):
        build_plan(_ts(), "reprofile", {"profile": "nonexistent"})


def test_time_shift_moves_all_dates_as_one_unit():
    ts = _ts(
        ExifIFD__DateTimeOriginal="2026:09:14 10:00:00",
        ExifIFD__CreateDate="2026:09:14 10:00:00",
        IFD0__ModifyDate="2026:09:14 10:30:00",
    )
    plan = build_plan(ts, "plausible", {"time_shift_days": 3})
    assert "-AllDates+=0:0:3 0" in plan.to_args()
    pending = ts.with_plan(plan)
    assert pending.get("ExifIFD:DateTimeOriginal").value == "2026:09:17 10:00:00"
    # Relative ordering survives the shift.
    assert pending.get("IFD0:ModifyDate").value == "2026:09:17 10:30:00"


def test_negative_time_shift():
    ts = _ts(ExifIFD__DateTimeOriginal="2026:09:14 10:00:00")
    plan = build_plan(ts, "plausible", {"time_shift_days": -2})
    assert "-AllDates-=0:0:2 0" in plan.to_args()
    assert ts.with_plan(plan).get("ExifIFD:DateTimeOriginal").value == "2026:09:12 10:00:00"


def test_plan_from_edits_handles_set_and_delete():
    plan = plan_from_edits({"IFD0:Model": "Pixel 8", "GPS:GPSLatitude": None})
    assert plan.assignments() == {"IFD0:Model": "Pixel 8"}
    assert plan.deletions() == ["GPS:GPSLatitude"]


def test_time_shift_days_are_days_not_years(engine, sample_heic, tmp_path):
    """ExifTool shift values are Y:M:D, so days must land in the third field.

    A real write is the only thing that catches this: the preview and the
    plan agreed with each other while both were wrong.
    """
    from pentimento.apply import apply_plan
    from pentimento.inspect import read_tags

    ts = read_tags(engine, sample_heic)
    before = str(ts.by_name("DateTimeOriginal").value)
    out = tmp_path / "shifted.HEIC"
    apply_plan(engine, sample_heic, out,
               build_plan(ts, "plausible", {"time_shift_days": 5}))
    after = str(read_tags(engine, out).by_name("DateTimeOriginal").value)
    assert before[:4] == after[:4], f"year changed: {before} -> {after}"
    assert int(after[8:10]) - int(before[8:10]) == 5
