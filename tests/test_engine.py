import pytest

from anonymizer.engine import ExifToolError


def test_version(engine):
    assert engine.execute("-ver").stdout.strip() == "13.59"


def test_sequential_commands_do_not_interleave(engine):
    assert engine.execute("-ver").stdout.strip() == "13.59"
    assert engine.execute("-ver").stdout.strip() == "13.59"


def test_read_json_returns_tags(engine, make_jpeg, tmp_path):
    src = make_jpeg()
    out = tmp_path / "out.jpg"
    engine.write(src, out, ["-EXIF:Model=TestCam"])
    assert engine.read_json(out)[0]["IFD0:Model"] == "TestCam"


def test_write_does_not_touch_source(engine, make_jpeg, tmp_path):
    src = make_jpeg()
    before = src.read_bytes()
    engine.write(src, tmp_path / "dst.jpg", ["-EXIF:Model=Other"])
    assert src.read_bytes() == before


def test_value_containing_option_syntax_is_data_not_instruction(
    engine, make_jpeg, tmp_path
):
    src = make_jpeg()
    dst = tmp_path / "d.jpg"
    engine.write(src, dst, ["-EXIF:Model=-delete_original!"])
    assert engine.read_json(dst)[0]["IFD0:Model"] == "-delete_original!"


def test_newline_in_argument_is_rejected(engine):
    with pytest.raises(ExifToolError, match="newline"):
        engine.execute("-EXIF:Model=a\n-delete_original!")


def test_error_surfaces(engine, tmp_path):
    with pytest.raises(ExifToolError):
        engine.read_json(tmp_path / "does-not-exist.jpg")
