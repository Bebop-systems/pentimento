import pytest

from anonymizer.apply import apply_plan
from anonymizer.inspect import read_tags
from anonymizer.model import EditOp, EditPlan
from anonymizer.payload import payload_digest


@pytest.fixture
def jpeg_with_gps(engine, make_jpeg):
    src = make_jpeg("with_gps.jpg")
    engine.write(src, src, [
        "-EXIF:Model=iPhone 15 Pro",
        "-EXIF:Make=Apple",
        "-GPS:GPSLatitude=47.62089",
        "-GPS:GPSLatitudeRef=N",
        "-GPS:GPSLongitude=122.34901",
        "-GPS:GPSLongitudeRef=W",
        "-EXIF:Orientation=1",
    ])
    return src


def test_apply_removes_gps_and_passes_all_gates(engine, jpeg_with_gps, tmp_path):
    out = tmp_path / "out.jpg"
    report = apply_plan(engine, jpeg_with_gps, out, EditPlan([EditOp("GPS:all", None)]))
    assert report.ok, [f"{g.name}: {g.detail}" for g in report.failures]
    assert {g.name for g in report.gates} == {
        "structural", "rendering", "payload", "regression"
    }
    after = read_tags(engine, out)
    assert not [k for k in after.keys() if k.startswith("GPS:")]


def test_apply_preserves_image_payload(engine, jpeg_with_gps, tmp_path):
    out = tmp_path / "out.jpg"
    before = payload_digest(jpeg_with_gps)
    apply_plan(engine, jpeg_with_gps, out, EditPlan([EditOp("GPS:all", None)]))
    assert payload_digest(out) == before


def test_apply_never_modifies_input(engine, jpeg_with_gps, tmp_path):
    original = jpeg_with_gps.read_bytes()
    apply_plan(engine, jpeg_with_gps, tmp_path / "o.jpg",
               EditPlan([EditOp("EXIF:Model", "Pixel 9")]))
    assert jpeg_with_gps.read_bytes() == original


def test_apply_sets_value(engine, jpeg_with_gps, tmp_path):
    out = tmp_path / "out.jpg"
    apply_plan(engine, jpeg_with_gps, out, EditPlan([EditOp("EXIF:Model", "Pixel 9")]))
    assert read_tags(engine, out).get("IFD0:Model").value == "Pixel 9"


def test_report_counts_removals(engine, jpeg_with_gps, tmp_path):
    out = tmp_path / "out.jpg"
    report = apply_plan(engine, jpeg_with_gps, out, EditPlan([EditOp("GPS:all", None)]))
    assert report.removed >= 4


def test_regression_gate_catches_surviving_tag(
    engine, jpeg_with_gps, tmp_path, monkeypatch
):
    """A plan that claims to delete a tag which survives must fail G4."""
    real_write = engine.write

    def sneaky_write(src, dst, args):
        return real_write(src, dst, [a for a in args if not a.startswith("-GPS")])

    monkeypatch.setattr(engine, "write", sneaky_write)
    out = tmp_path / "out.jpg"
    report = apply_plan(engine, jpeg_with_gps, out, EditPlan([EditOp("GPS:all", None)]))
    assert not report.ok
    assert any(g.name == "regression" and not g.ok for g in report.gates)
    assert not out.exists(), "a failed write must not leave an output behind"


def test_rendering_gate_catches_orientation_change(engine, jpeg_with_gps, tmp_path):
    """Changing Orientation alters how the file displays, so G2 must fail."""
    out = tmp_path / "out.jpg"
    report = apply_plan(
        engine, jpeg_with_gps, out, EditPlan([EditOp("EXIF:Orientation", "8")])
    )
    assert not report.ok
    assert any(g.name == "rendering" and not g.ok for g in report.gates)


def test_gate_results_carry_plain_language_meaning(engine, jpeg_with_gps, tmp_path):
    out = tmp_path / "out.jpg"
    report = apply_plan(engine, jpeg_with_gps, out, EditPlan([EditOp("GPS:all", None)]))
    assert all(g.meaning for g in report.gates)
