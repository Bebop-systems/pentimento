from pathlib import Path

from pentimento.inspect import read_tags


class FakeEngine:
    def __init__(self):
        self.calls = []

    def read_json(self, path, *extra):
        self.calls.append(extra)
        if "-n" in extra:
            return [{"SourceFile": str(path), "GPS:GPSLatitude": 47.62089}]
        return [{"SourceFile": str(path), "GPS:GPSLatitude": "47 deg N"}]


def test_read_tags_issues_both_passes():
    engine = FakeEngine()
    read_tags(engine, Path("a.jpg"))
    assert ("-n",) in engine.calls
    assert () in engine.calls


def test_read_tags_merges_passes():
    tag = read_tags(FakeEngine(), Path("a.jpg")).get("GPS:GPSLatitude")
    assert tag.value == 47.62089
    assert tag.display == "47 deg N"


def test_read_tags_on_real_file(engine, make_jpeg):
    ts = read_tags(engine, make_jpeg())
    assert ts.get("File:FileType").value == "JPEG"
