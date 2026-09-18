from scripts.fetch_exiftool import find_exiftool, EXIFTOOL_VERSION


def test_version_is_pinned():
    assert EXIFTOOL_VERSION == "13.59"


def test_find_exiftool_returns_none_when_vendor_empty(tmp_path, monkeypatch):
    import scripts.fetch_exiftool as fx
    monkeypatch.setattr(fx, "VENDOR_DIR", tmp_path / "nothing")
    assert find_exiftool() is None


def test_find_exiftool_locates_binary(tmp_path, monkeypatch):
    import scripts.fetch_exiftool as fx
    d = tmp_path / "exiftool-13.59_64"
    d.mkdir(parents=True)
    exe = d / "exiftool.exe"
    exe.write_bytes(b"stub")
    monkeypatch.setattr(fx, "VENDOR_DIR", tmp_path)
    assert find_exiftool() == exe
