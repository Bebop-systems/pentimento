from pathlib import Path

from anonymizer.model import EditOp, EditPlan, Tag, TagSet


def test_tag_key_joins_group_and_name():
    assert Tag("EXIF", "Model", "iPhone", "iPhone").key == "EXIF:Model"


def test_composite_and_file_groups_are_not_editable():
    assert not Tag("Composite", "GPSPosition", "x", "x").editable
    assert not Tag("File", "ImageWidth", 1, "1").editable
    assert not Tag("ICC-header", "ProfileDateTime", "x", "x").editable
    assert Tag("GPS", "GPSLatitude", 1.0, "1").editable


def test_tagset_from_exiftool_merges_machine_and_display():
    machine = {"SourceFile": "a.jpg", "GPS:GPSLatitude": 47.62089}
    display = {"SourceFile": "a.jpg", "GPS:GPSLatitude": "47 deg 37' 15.20\" N"}
    ts = TagSet.from_exiftool(Path("a.jpg"), machine, display)
    tag = ts.get("GPS:GPSLatitude")
    assert tag.value == 47.62089
    assert tag.display == "47 deg 37' 15.20\" N"
    assert tag.group == "GPS"


def test_tagset_from_exiftool_skips_sourcefile():
    ts = TagSet.from_exiftool(Path("a.jpg"), {"SourceFile": "a.jpg"}, {})
    assert ts.keys() == set()


def test_by_name_prefers_stored_tag_over_composite():
    m = {"Composite:GPSAltitude": "312.1 m", "GPS:GPSAltitude": 312.17}
    ts = TagSet.from_exiftool(Path("a.jpg"), m, m)
    assert ts.by_name("GPSAltitude").group == "GPS"


def test_editplan_to_args_renders_set_and_delete():
    plan = EditPlan([EditOp("EXIF:Model", "X"), EditOp("GPS:all", None)])
    assert plan.to_args() == ["-EXIF:Model=X", "-GPS:all="]


def test_editplan_raw_args_override_rendered_args():
    plan = EditPlan([EditOp("EXIF:Model", "X")], raw_args=["-all=", "-tagsfromfile", "@"])
    assert plan.to_args() == ["-all=", "-tagsfromfile", "@"]


def test_editplan_deletions_lists_only_deletes():
    plan = EditPlan([EditOp("EXIF:Model", "X"), EditOp("GPS:all", None)])
    assert plan.deletions() == ["GPS:all"]


def test_editplan_merged_lets_later_ops_win():
    a = EditPlan([EditOp("EXIF:Model", "A")])
    b = EditPlan([EditOp("EXIF:Model", "B")])
    assert a.merged(b).to_args() == ["-EXIF:Model=B"]


def test_with_plan_produces_pending_state():
    m = {"EXIF:Model": "iPhone", "GPS:GPSLatitude": 47.0}
    ts = TagSet.from_exiftool(Path("a.jpg"), m, m)
    pending = ts.with_plan(
        EditPlan([EditOp("EXIF:Model", "Pixel"), EditOp("GPS:all", None)])
    )
    assert pending.get("EXIF:Model").value == "Pixel"
    assert pending.get("GPS:GPSLatitude") is None
    assert ts.get("EXIF:Model").value == "iPhone"


def test_with_plan_all_keeps_protected_groups():
    m = {"EXIF:Model": "iPhone", "ICC-header:ProfileClass": "Display"}
    ts = TagSet.from_exiftool(Path("a.jpg"), m, m)
    pending = ts.with_plan(EditPlan([EditOp("all", None)]))
    assert pending.get("EXIF:Model") is None
    assert pending.get("ICC-header:ProfileClass") is not None
