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


def test_numeric_values_round_trip_without_print_conversion(engine, make_jpeg, tmp_path):
    """Regression: without -n, ExifTool coerces 1 and 8 both to 3, silently."""
    src = make_jpeg()
    for value in ("1", "8"):
        dst = tmp_path / f"o{value}.jpg"
        engine.write(src, dst, [f"-EXIF:Orientation={value}"])
        assert engine.read_json(dst, "-n")[0]["IFD0:Orientation"] == int(value)


def test_concurrent_commands_do_not_interleave(exiftool_path):
    """Flask serves requests on threads and they share one ExifTool process.

    Without a lock the commands interleave on a single stdin and each thread
    reads whichever sentinel arrives first, which hangs the server. This
    fails with a deadlock or a wrong answer if the lock is removed.
    """
    import concurrent.futures

    from anonymizer.engine import ExifToolEngine

    with ExifToolEngine(exiftool_path) as engine:
        def ask(_):
            return engine.execute("-ver").stdout.strip()

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(ask, range(40)))

    assert results == ["13.59"] * 40


def test_concurrent_reads_return_their_own_file(exiftool_path, tmp_path):
    """Each thread must get its own file's metadata, not another's."""
    import concurrent.futures

    from anonymizer.engine import ExifToolEngine
    from tests.conftest import MINIMAL_JPEG

    with ExifToolEngine(exiftool_path) as engine:
        paths = []
        for index in range(12):
            path = tmp_path / f"cam{index}.jpg"
            path.write_bytes(MINIMAL_JPEG)
            engine.write(path, path, [f"-EXIF:Model=CAM{index}"])
            paths.append((index, path))

        def read(item):
            index, path = item
            return index, engine.read_json(path)[0]["IFD0:Model"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = dict(pool.map(read, paths))

    assert results == {index: f"CAM{index}" for index in range(12)}


def test_engine_restarts_after_the_process_is_killed(exiftool_path):
    """A dead ExifTool must not break every later request."""
    from anonymizer.engine import ExifToolEngine

    with ExifToolEngine(exiftool_path) as engine:
        assert engine.execute("-ver").stdout.strip() == "13.59"

        engine._proc.kill()
        engine._proc.wait(timeout=5)

        assert engine.execute("-ver").stdout.strip() == "13.59"
        assert engine.restarts == 1
