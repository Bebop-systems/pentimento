import io

import pytest
from werkzeug.test import EnvironBuilder

from anonymizer.server import create_app


@pytest.fixture
def client(engine, tmp_path):
    # Output goes to a temp folder: the suite must never write into the
    # operator's real output/ directory.
    app = create_app(engine, output_dir=tmp_path / "out")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _upload(client, path):
    """Post a file, closing the body stream the test client leaves open.

    EnvironBuilder spools any multipart body over ~500KB to a tempfile and
    never closes it. That is the test client's doing, not the app's, but
    the suite runs with warnings as errors so the handle has to be closed
    here rather than the gate weakened.
    """
    builder = EnvironBuilder(
        method="POST",
        path="/api/upload",
        data={"file": (io.BytesIO(path.read_bytes()), path.name)},
        content_type="multipart/form-data",
    )
    environ = builder.get_environ()
    try:
        return client.open(environ)
    finally:
        stream = environ.get("wsgi.input")
        if hasattr(stream, "close"):
            stream.close()
        builder.close()


def test_index_served(client):
    assert client.get("/").status_code == 200


def test_presets_listed(client):
    data = client.get("/api/presets").get_json()
    assert set(data["presets"]) == {"clean", "plausible", "reprofile", "manual"}
    assert "pixel-8" in data["profiles"]


def test_upload_requires_file(client):
    assert client.post("/api/upload", data={}).status_code == 400


def test_upload_rejects_non_image(client, tmp_path):
    junk = tmp_path / "notes.txt"
    junk.write_bytes(b"this is not an image")
    assert _upload(client, junk).status_code == 400


def test_unknown_session_rejected(client):
    r = client.post("/api/preview", json={"session": "nope", "preset": "manual"})
    assert r.status_code == 404


def test_foreign_host_header_rejected(client):
    assert client.get("/", headers={"Host": "evil.example.com"}).status_code == 403


def test_loopback_host_allowed(client):
    assert client.get("/", headers={"Host": "127.0.0.1:5000"}).status_code == 200


def test_upload_returns_categorised_tags(client, sample_heic):
    data = _upload(client, sample_heic).get_json()
    assert data["container"] == "isobmff"
    categories = {t["category"] for t in data["tags"]}
    assert "location" in categories
    # Highest-risk rows sort first so the dangerous ones are visible at once.
    assert data["tags"][0]["category"] == "location"


def test_preview_reports_removals_without_writing(client, sample_heic):
    session = _upload(client, sample_heic).get_json()["session"]
    data = client.post("/api/preview", json={
        "session": session, "preset": "plausible"
    }).get_json()
    assert not [t for t in data["tags"] if t["category"] == "location"]
    assert any(d["kind"] == "removed" for d in data["diff"])


def test_preview_rejects_unknown_preset(client, sample_heic):
    session = _upload(client, sample_heic).get_json()["session"]
    r = client.post("/api/preview", json={"session": session, "preset": "bogus"})
    assert r.status_code == 400


def test_apply_passes_all_gates_and_offers_download(client, sample_heic):
    session = _upload(client, sample_heic).get_json()["session"]
    result = client.post("/api/apply", json={
        "session": session, "preset": "plausible"
    }).get_json()
    assert result["ok"], result["gates"]
    assert {g["name"] for g in result["gates"]} == {
        "structural", "rendering", "payload", "regression"
    }
    assert all(g["meaning"] for g in result["gates"])
    download = client.get(result["download"])
    assert download.status_code == 200
    assert download.data[:4] == sample_heic.read_bytes()[:4]


def test_download_before_apply_is_404(client, sample_heic):
    session = _upload(client, sample_heic).get_json()["session"]
    assert client.get(f"/api/download/{session}").status_code == 404


def test_manual_edits_are_applied(client, sample_heic):
    session = _upload(client, sample_heic).get_json()["session"]
    data = client.post("/api/preview", json={
        "session": session, "preset": "manual",
        "edits": {"EXIF:Model": "Pixel 8"},
    }).get_json()
    # The edit names EXIF:Model but resolves onto the tag ExifTool actually
    # reports, IFD0:Model, exactly as the write will.
    assert any(d["key"] == "IFD0:Model" and d["after"] == "Pixel 8"
               and d["kind"] == "changed" for d in data["diff"])


def test_reprofile_swaps_identity(client, sample_heic):
    session = _upload(client, sample_heic).get_json()["session"]
    data = client.post("/api/preview", json={
        "session": session, "preset": "reprofile", "profile": "pixel-8",
    }).get_json()
    assert any(d["after"] == "Pixel 8" for d in data["diff"])


def test_apply_then_changing_preset_does_not_reuse_stale_output(client, sample_heic):
    """A second apply must overwrite the first, not serve the earlier file."""
    session = _upload(client, sample_heic).get_json()["session"]
    first = client.post("/api/apply", json={
        "session": session, "preset": "plausible"
    }).get_json()
    assert first["ok"]
    before = client.get(first["download"]).data

    second = client.post("/api/apply", json={
        "session": session, "preset": "reprofile", "profile": "pixel-8",
    }).get_json()
    assert second["ok"]
    after = client.get(second["download"]).data
    assert before != after, "download still serves the superseded output"


def test_tags_carry_plain_english_explanations(client, sample_heic):
    data = _upload(client, sample_heic).get_json()
    assert all(t["what"] and t["reveals"] for t in data["tags"])
    gps = next(t for t in data["tags"] if t["name"] == "GPSLatitude")
    assert "latitude" in gps["what"].lower()


def test_sensitive_values_are_sealed_by_default(client, sample_heic):
    data = _upload(client, sample_heic).get_json()
    gps = next(t for t in data["tags"] if t["name"] == "GPSLatitude")
    assert gps["sealed"] is True
    technical = next(t for t in data["tags"] if t["category"] == "benign")
    assert technical["sealed"] is False


def test_categories_summarise_the_file(client, sample_heic):
    data = _upload(client, sample_heic).get_json()
    by_key = {c["key"]: c for c in data["categories"]}
    assert by_key["location"]["count"] > 0
    assert by_key["location"]["summary"]
    # Riskiest first, so the overview leads with what matters.
    assert data["categories"][0]["key"] == "location"


def test_apply_saves_to_a_findable_path(client, sample_heic):
    session = _upload(client, sample_heic).get_json()["session"]
    result = client.post("/api/apply", json={
        "session": session, "preset": "plausible"
    }).get_json()
    assert result["ok"]
    from pathlib import Path
    saved = Path(result["saved_path"])
    assert saved.is_file()
    assert saved.stat().st_size > 0
    assert result["saved_name"].endswith(".HEIC")


def test_repeated_writes_do_not_overwrite_each_other(client, sample_heic):
    from pathlib import Path
    session = _upload(client, sample_heic).get_json()["session"]
    paths = []
    for _ in range(2):
        result = client.post("/api/apply", json={
            "session": session, "preset": "plausible"
        }).get_json()
        paths.append(Path(result["saved_path"]))
    assert paths[0] != paths[1]
    assert all(p.is_file() for p in paths)


def test_presets_endpoint_groups_credible_and_novelty_profiles(client):
    data = client.get("/api/presets").get_json()
    assert "pixel-8" in data["credible"]
    assert "gameboy-camera" in data["novelty"]
    assert set(data["credible"]) & set(data["novelty"]) == set()
    assert data["profiles"]["gameboy-camera"]["novelty"] is True
    assert data["profiles"]["pixel-8"]["novelty"] is False
    assert data["profiles"]["toaster"]["note"]


def test_novelty_reprofile_writes_and_verifies(client, sample_heic):
    session = _upload(client, sample_heic).get_json()["session"]
    result = client.post("/api/apply", json={
        "session": session, "preset": "reprofile", "profile": "gameboy-camera",
    }).get_json()
    assert result["ok"], result["gates"]
    assert all(g["ok"] for g in result["gates"])


def test_novelty_identity_is_flagged_as_inconsistent(client, sample_heic):
    """Claiming a Game Boy took an IMG_*.HEIC should be reported, not hidden."""
    session = _upload(client, sample_heic).get_json()["session"]
    data = client.post("/api/preview", json={
        "session": session, "preset": "reprofile", "profile": "gameboy-camera",
    }).get_json()
    rules = {f["rule"] for f in data["findings"]}
    assert "filename_mismatch" in rules
