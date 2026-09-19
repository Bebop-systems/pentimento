from pathlib import Path

from pentimento.linter import lint
from pentimento.model import TagSet


def _ts(name="a.heic", **kw):
    m = {k.replace("__", ":"): v for k, v in kw.items()}
    return TagSet.from_exiftool(Path(name), m, m)


def _rules(tagset):
    return {f.rule for f in lint(tagset)}


def test_coherent_file_produces_no_findings():
    ts = _ts(
        name="IMG_1.HEIC",
        IFD0__Make="Apple", IFD0__Model="iPhone 15 Pro",
        IFD0__Software="17.5.1",
        ExifIFD__LensModel="iPhone 15 Pro back triple camera 6.765mm f/1.78",
        ExifIFD__DateTimeOriginal="2026:09:14 14:23:07",
    )
    assert lint(ts) == []


def test_partial_gps_detected():
    assert "partial_gps" in _rules(_ts(GPS__GPSLatitude=47.6))


def test_gps_residue_after_coordinate_removal_detected():
    assert "partial_gps" in _rules(_ts(GPS__GPSAltitude=30.0))


def test_complete_gps_produces_no_partial_finding():
    ts = _ts(GPS__GPSLatitude=47.6, GPS__GPSLatitudeRef="N",
             GPS__GPSLongitude=122.3, GPS__GPSLongitudeRef="W")
    assert "partial_gps" not in _rules(ts)


def test_orphan_makernote_detected():
    assert "orphan_makernote" in _rules(_ts(IFD0__Make="Google", Apple__SceneFlags=1))


def test_matching_makernote_produces_no_finding():
    assert "orphan_makernote" not in _rules(_ts(IFD0__Make="Apple", Apple__SceneFlags=1))


def test_filename_mismatch_detected():
    assert "filename_mismatch" in _rules(_ts(name="IMG_0942.HEIC", IFD0__Make="Canon"))


def test_filename_match_produces_no_finding():
    assert "filename_mismatch" not in _rules(_ts(name="IMG_0942.HEIC", IFD0__Make="Apple"))


def test_round_timestamp_detected():
    ts = _ts(ExifIFD__DateTimeOriginal="2026:09:14 12:00:00", IFD0__Make="Apple")
    assert "round_timestamp" in _rules(ts)


def test_round_timestamp_with_subseconds_is_accepted():
    ts = _ts(ExifIFD__DateTimeOriginal="2026:09:14 12:00:00",
             ExifIFD__SubSecTimeOriginal="431")
    assert "round_timestamp" not in _rules(ts)


def test_time_ordering_violation_detected():
    ts = _ts(ExifIFD__DateTimeOriginal="2026:09:14 12:00:01",
             IFD0__ModifyDate="2020:01:01 00:00:00")
    assert "time_ordering" in _rules(ts)


def test_serial_residue_detected():
    assert "serial_residue" in _rules(_ts(ExifIFD__InternalSerialNumber="ABC123456"))


def test_model_software_mismatch_detected():
    """iOS 9 never ran on an iPhone 15 Pro."""
    ts = _ts(IFD0__Make="Apple", IFD0__Model="iPhone 15 Pro", IFD0__Software="9.3.5")
    assert "model_software" in _rules(ts)


def test_plausible_ios_version_accepted():
    ts = _ts(IFD0__Make="Apple", IFD0__Model="iPhone 15 Pro", IFD0__Software="17.5.1")
    assert "model_software" not in _rules(ts)


def test_model_lens_mismatch_detected():
    ts = _ts(IFD0__Model="iPhone 15 Pro",
             ExifIFD__LensModel="iPhone 8 back camera 3.99mm f/1.8")
    assert "model_lens" in _rules(ts)


def test_model_lens_match_accepted():
    ts = _ts(IFD0__Model="iPhone 13 Pro Max",
             ExifIFD__LensModel="iPhone 13 Pro Max back triple camera 9mm f/2.8")
    assert "model_lens" not in _rules(ts)


def test_dimension_coherence_detected():
    assert "dimension_coherence" in _rules(
        _ts(ExifIFD__ExifImageWidth=4032, File__ImageWidth=1024)
    )


def test_matching_dimensions_accepted():
    assert "dimension_coherence" not in _rules(
        _ts(ExifIFD__ExifImageWidth=4032, File__ImageWidth=4032)
    )


def test_utc_math_mismatch_detected():
    ts = _ts(
        Composite__GPSDateTime="2026:09:18 22:58:13",
        ExifIFD__DateTimeOriginal="2026:09:18 18:58:14",
        ExifIFD__OffsetTimeOriginal="+09:00",
    )
    assert "utc_math" in _rules(ts)


def test_utc_math_consistent_accepted():
    ts = _ts(
        Composite__GPSDateTime="2026:09:18 22:58:13",
        ExifIFD__DateTimeOriginal="2026:09:18 18:58:14",
        ExifIFD__OffsetTimeOriginal="-04:00",
    )
    assert "utc_math" not in _rules(ts)


def test_warnings_sort_before_notes():
    ts = _ts(name="IMG_1.HEIC", IFD0__Make="Canon", GPS__GPSLatitude=1.0)
    severities = [f.severity for f in lint(ts)]
    assert severities == sorted(severities, key=lambda s: s != "warning")


def test_reprofiling_to_another_vendor_flags_the_filename():
    """An IMG_*.HEIC claiming Google is the tell the linter exists to catch."""
    from pentimento.model import EditOp, EditPlan
    m = {"IFD0:Make": "Apple", "IFD0:Model": "iPhone 13 Pro Max"}
    ts = TagSet.from_exiftool(Path("IMG_0942.HEIC"), m, m)
    pending = ts.with_plan(EditPlan([
        EditOp("EXIF:Make", "Google"), EditOp("EXIF:Model", "Pixel 8"),
    ]))
    assert "filename_mismatch" in _rules(pending)
