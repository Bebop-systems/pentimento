"""The whole pipeline against the real sample HEIC.

These are the tests that matter most: every bug worth fixing in this
project was found by running a real file through, not by unit tests.
"""
import pytest

from pentimento.apply import apply_plan
from pentimento.inspect import read_tags
from pentimento.linter import lint
from pentimento.payload import payload_digest
from pentimento.presets import build_plan
from pentimento.profiles import PROFILES

PRESETS_UNDER_TEST = [
    ("plausible", {}),
    ("reprofile", {"profile": "pixel-8"}),
    ("clean", {}),
    ("plausible", {"time_shift_days": 5}),
]


@pytest.fixture(params=PRESETS_UNDER_TEST, ids=lambda p: f"{p[0]}{p[1] or ''}")
def written(request, engine, sample_heic, tmp_path):
    preset, options = request.param
    tagset = read_tags(engine, sample_heic)
    output = tmp_path / f"out_{preset}.HEIC"
    report = apply_plan(
        engine, sample_heic, output, build_plan(tagset, preset, options)
    )
    return report, output, tagset


def test_every_preset_passes_all_four_gates(written, engine):
    report, _, _ = written
    assert report.ok, [f"{g.name}: {g.detail}" for g in report.failures]
    assert len(report.gates) == 4


def test_image_bitstream_survives_byte_identical(written, sample_heic):
    _, output, _ = written
    assert payload_digest(output) == payload_digest(sample_heic)


def test_original_is_never_modified(written, sample_heic):
    _, _, _ = written
    assert payload_digest(sample_heic) is not None
    tags = sample_heic.read_bytes()
    assert tags[4:8] == b"ftyp"
    assert len(tags) == 1957522


def test_location_is_gone(written, engine):
    _, output, _ = written
    after = read_tags(engine, output)
    assert not [k for k in after.keys() if k.startswith("GPS:")]
    assert not [k for k in after.keys() if k.startswith("Composite:GPS")]


def test_makernote_is_gone(written, engine):
    """61 Apple tags carrying scene analysis and focus telemetry."""
    _, output, _ = written
    after = read_tags(engine, output)
    assert not [k for k in after.keys() if k.startswith("Apple:")]


def test_output_still_opens_as_a_heic(written, engine):
    _, output, _ = written
    after = read_tags(engine, output)
    assert after.get("File:FileType").value == "HEIC"
    assert int(after.get("File:ImageWidth").value) == 4032
    assert int(after.get("File:ImageHeight").value) == 3024


def test_result_lints_without_warnings(written, engine):
    _, output, _ = written
    warnings = [f for f in lint(read_tags(engine, output)) if f.severity == "warning"]
    assert warnings == [], [f.message for f in warnings]


def test_plausible_keeps_a_coherent_camera_identity(engine, sample_heic, tmp_path):
    tagset = read_tags(engine, sample_heic)
    output = tmp_path / "plausible.HEIC"
    apply_plan(engine, sample_heic, output, build_plan(tagset, "plausible", {}))
    after = read_tags(engine, output)
    assert after.by_name("Make").value == "Apple"
    assert after.by_name("Model").value == "iPhone 13 Pro Max"
    assert after.by_name("DateTimeOriginal") is not None


def test_clean_strips_the_camera_identity_too(engine, sample_heic, tmp_path):
    tagset = read_tags(engine, sample_heic)
    output = tmp_path / "clean.HEIC"
    apply_plan(engine, sample_heic, output, build_plan(tagset, "clean", {}))
    after = read_tags(engine, output)
    assert after.by_name("Make") is None
    assert after.by_name("Model") is None
    assert after.by_name("DateTimeOriginal") is None
    # But it still renders correctly.
    assert after.by_name("Orientation").value == 6


@pytest.mark.parametrize("profile_key", sorted(PROFILES))
def test_each_camera_profile_writes_a_self_consistent_identity(
    profile_key, engine, sample_heic, tmp_path
):
    tagset = read_tags(engine, sample_heic)
    output = tmp_path / f"{profile_key}.HEIC"
    report = apply_plan(
        engine, sample_heic, output,
        build_plan(tagset, "reprofile", {"profile": profile_key}),
    )
    assert report.ok, [f"{g.name}: {g.detail}" for g in report.failures]
    after = read_tags(engine, output)
    profile = PROFILES[profile_key]
    assert after.by_name("Make").value == profile.make
    assert after.by_name("Model").value == profile.model
    assert [f for f in lint(after) if f.severity == "warning"] == []


def test_a_failed_gate_leaves_no_output_behind(engine, sample_heic, tmp_path):
    """Changing Orientation breaks rendering, so nothing may be handed over."""
    from pentimento.model import EditOp, EditPlan

    output = tmp_path / "broken.HEIC"
    report = apply_plan(
        engine, sample_heic, output, EditPlan([EditOp("EXIF:Orientation", "1")])
    )
    assert not report.ok
    assert not output.exists()
