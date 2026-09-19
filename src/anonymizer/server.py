"""Local single-user web server.

Binds loopback only. Nothing is uploaded anywhere: files live in a
per-session temp directory that is removed when the process exits.
"""
from __future__ import annotations

import atexit
import io
import mimetypes
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file
from werkzeug.utils import secure_filename

from .apply import apply_plan
from .engine import ExifToolEngine
from .explanations import CATEGORY_SUMMARY, explain
from .inspect import read_tags
from .linter import lint
from .model import EditPlan, TagSet
from .paths import default_output_dir, web_dir
from .naming import (
    COLLISION_MODES, DEFAULT_COLLISION, DEFAULT_PATTERN, TOKENS,
    Naming, NamingError, build_values,
)
from .payload import container_of
from .presets import PRESETS, build_plan, plan_from_edits
from .profiles import CREDIBLE_KEYS, NOVELTY_KEYS, PROFILES
from .sensitivity import RISK_ORDER, Category, classify

# Resolved through paths so a packaged app finds its own files and writes
# somewhere it is actually allowed to.
WEB_DIR = web_dir()

# Verified output is written here as well as offered as a download. A browser
# download can land somewhere the operator cannot find, or be swallowed
# entirely by a security policy; a path on disk they can read off the screen
# always works.
OUTPUT_DIR = default_output_dir()

# A browser will send whatever Host a malicious page names. Restricting it
# to loopback stops DNS rebinding from reaching this server through a tab
# the operator already has open.
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


@dataclass
class Session:
    id: str
    directory: Path
    source: Path
    tagset: TagSet
    output: Path | None = None
    gates: list = field(default_factory=list)


class SessionStore:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="anonymizer-"))
        self.sessions: dict[str, Session] = {}
        atexit.register(self.cleanup)

    def create(self, filename: str, data) -> Session:
        session_id = uuid.uuid4().hex
        directory = self.root / session_id
        directory.mkdir(parents=True)
        safe = secure_filename(filename) or "upload.bin"
        source = directory / safe
        try:
            data.save(source)
        finally:
            # Werkzeug spools large uploads to a temp file and does not close
            # it for us; leaving it open leaks a handle per upload.
            data.close()
        return Session(id=session_id, directory=directory, source=source, tagset=None)

    def register(self, session: Session) -> None:
        self.sessions[session.id] = session

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _serve_asset(filename: str):
    """Serve a file from web/ out of memory.

    Flask's send_from_directory hands back an open file handle that is not
    released until the response is collected. These assets are a few
    kilobytes, so reading them is simpler than tracking the handle.
    """
    target = (WEB_DIR / filename).resolve()
    if not target.is_file() or WEB_DIR.resolve() not in target.parents:
        return jsonify({"error": "Not found"}), 404
    mimetype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return Response(target.read_bytes(), mimetype=mimetype)


# Categories whose values are worth hiding until the operator asks. Showing
# your own coordinates unprompted defeats the point during a screen share.
_SEALED_CATEGORIES = {Category.LOCATION, Category.DEVICE, Category.CONTENT}


def _tag_payload(tagset: TagSet) -> list[dict]:
    rows = []
    for tag in tagset.tags.values():
        category = classify(tag)
        explanation = explain(tag)
        rows.append({
            "key": tag.key,
            "group": tag.group,
            "name": tag.name,
            "value": "" if tag.value is None else str(tag.value),
            "display": tag.display,
            "category": str(category),
            "editable": tag.editable,
            "what": explanation.what,
            "reveals": explanation.reveals,
            "sealed": category in _SEALED_CATEGORIES and bool(tag.display),
        })
    order = {c: i for i, c in enumerate(RISK_ORDER)}
    rows.sort(key=lambda r: (order.get(Category(r["category"]), 9), r["key"]))
    return rows


def _category_payload(tagset: TagSet) -> list[dict]:
    """Counts and a one-line summary per category, for the overview cards."""
    counts: dict[Category, int] = {}
    for tag in tagset.tags.values():
        category = classify(tag)
        counts[category] = counts.get(category, 0) + 1
    return [
        {
            "key": str(category),
            "count": counts[category],
            "summary": CATEGORY_SUMMARY[category],
        }
        for category in RISK_ORDER
        if counts.get(category)
    ]


def _findings_payload(tagset: TagSet) -> list[dict]:
    return [
        {"rule": f.rule, "severity": f.severity, "message": f.message}
        for f in lint(tagset)
    ]


def _diff_payload(before: TagSet, after: TagSet) -> list[dict]:
    rows = []

    # A MakerNote scrub removes dozens of vendor tags at once. Listing each
    # one buries the handful of changes the operator actually chose, so
    # large same-group removals collapse into a single line.
    removed = [before.tags[k] for k in sorted(before.keys() - after.keys())
               if before.tags[k].editable]
    by_group: dict[str, list] = {}
    for tag in removed:
        by_group.setdefault(tag.group, []).append(tag)

    for group, tags in by_group.items():
        if len(tags) > 5:
            rows.append({
                "key": f"{group}: {len(tags)} tags",
                "kind": "removed",
                "before": ", ".join(t.name for t in tags[:4]) + ", ...",
                "after": "",
            })
        else:
            for tag in tags:
                rows.append({"key": tag.key, "kind": "removed",
                             "before": tag.display, "after": ""})
    for key in sorted(before.keys() & after.keys()):
        b, a = before.tags[key], after.tags[key]
        if str(b.value) != str(a.value):
            rows.append({"key": key, "kind": "changed",
                         "before": b.display, "after": a.display})
    for key in sorted(after.keys() - before.keys()):
        rows.append({"key": key, "kind": "added", "before": "",
                     "after": after.tags[key].display})
    return rows


def _naming(body: dict) -> Naming:
    return Naming(
        pattern=(body.get("pattern") or DEFAULT_PATTERN).strip(),
        on_collision=body.get("on_collision") or DEFAULT_COLLISION,
    )


def _naming_values(session: Session, body: dict) -> dict:
    return build_values(
        session.source,
        body.get("preset") or "manual",
        body.get("profile") or "",
    )


def _build(session: Session, body: dict) -> EditPlan:
    preset = body.get("preset") or "manual"
    options = {
        "profile": body.get("profile"),
        "time_shift_days": body.get("time_shift_days") or 0,
    }
    plan = build_plan(session.tagset, preset, options)
    edits = body.get("edits") or {}
    if edits:
        plan = plan.merged(plan_from_edits(edits))
    return plan


def create_app(
    engine: ExifToolEngine | None = None,
    output_dir: Path | None = None,
) -> Flask:
    app = Flask(__name__, static_folder=None)
    store = SessionStore()
    app.config["STORE"] = store
    app.config["ENGINE"] = engine
    # Injectable so the test suite never writes into the operator's real
    # output folder.
    app.config["OUTPUT_DIR"] = Path(output_dir) if output_dir else OUTPUT_DIR

    def get_engine() -> ExifToolEngine:
        current = app.config.get("ENGINE")
        if current is None:
            from .paths import find_exiftool
            binary = find_exiftool()
            if binary is None:
                # Only a source checkout may reach out to the network; a
                # packaged app ships with its own copy or has a real fault.
                from scripts.fetch_exiftool import ensure_exiftool
                binary = ensure_exiftool()
            current = ExifToolEngine(binary).start()
            app.config["ENGINE"] = current
        return current

    @app.before_request
    def enforce_loopback():
        host = (request.host or "").rsplit(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            return jsonify({"error": f"Refusing request for host {host!r}"}), 403

    @app.get("/")
    def index():
        return _serve_asset("index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename):
        return _serve_asset(filename)

    @app.get("/api/presets")
    def presets():
        return jsonify({
            "presets": PRESETS,
            "profiles": {
                key: {
                    "label": profile.label,
                    "novelty": profile.novelty,
                    "note": profile.note,
                }
                for key, profile in PROFILES.items()
            },
            "credible": list(CREDIBLE_KEYS),
            "novelty": list(NOVELTY_KEYS),
            "patterns": {k: p.filename_pattern for k, p in PROFILES.items()},
            "tokens": TOKENS,
            "collision_modes": COLLISION_MODES,
            "default_pattern": DEFAULT_PATTERN,
            "default_collision": DEFAULT_COLLISION,
        })

    @app.post("/api/upload")
    def upload():
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return jsonify({"error": "No file was provided"}), 400
        session = store.create(uploaded.filename, uploaded)
        try:
            session.tagset = read_tags(get_engine(), session.source)
        except Exception as exc:
            shutil.rmtree(session.directory, ignore_errors=True)
            return jsonify({"error": f"Could not read that file: {exc}"}), 400

        # ExifTool happily reports File: tags for a text file. Requiring a
        # picture or video MIME type keeps the editor honest about what it
        # can actually verify.
        mime = session.tagset.get("File:MIMEType")
        kind = str(mime.value) if mime else ""
        if not kind.startswith(("image/", "video/")):
            shutil.rmtree(session.directory, ignore_errors=True)
            return jsonify({
                "error": f"That is a {kind or 'file of unknown type'}, "
                         "not a photo or video."
            }), 400
        store.register(session)
        return jsonify({
            "session": session.id,
            "filename": session.source.name,
            "container": container_of(session.source),
            "size": session.source.stat().st_size,
            "tags": _tag_payload(session.tagset),
            "categories": _category_payload(session.tagset),
            "findings": _findings_payload(session.tagset),
        })

    def _session_or_404(body):
        session = store.sessions.get((body or {}).get("session", ""))
        if session is None:
            return None, (jsonify({"error": "Unknown session"}), 404)
        return session, None

    @app.post("/api/preview")
    def preview():
        body = request.get_json(silent=True) or {}
        session, error = _session_or_404(body)
        if error:
            return error
        try:
            plan = _build(session, body)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        pending = session.tagset.with_plan(plan)

        naming, name, naming_error = _naming(body), "", ""
        try:
            name = naming.preview(_naming_values(session, body))
        except NamingError as exc:
            naming_error = str(exc)

        # Lint the file as it will exist, named as it will be named. A
        # Pixel photo still called IMG_0942 contradicts itself, and that
        # warning should clear once the name follows the camera.
        judged = replace(pending, path=Path(name)) if name else pending

        return jsonify({
            "tags": _tag_payload(pending),
            "categories": _category_payload(pending),
            "findings": _findings_payload(judged),
            "diff": _diff_payload(session.tagset, pending),
            "args": plan.to_args(),
            "output_name": name,
            "naming_error": naming_error,
        })

    @app.post("/api/apply")
    def apply_route():
        body = request.get_json(silent=True) or {}
        session, error = _session_or_404(body)
        if error:
            return error
        try:
            plan = _build(session, body)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        out_dir = app.config["OUTPUT_DIR"]
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            output = _naming(body).resolve(out_dir, _naming_values(session, body))
        except NamingError as exc:
            return jsonify({"error": str(exc)}), 400
        try:
            report = apply_plan(get_engine(), session.source, output, plan)
        except Exception as exc:
            return jsonify({"error": f"Write failed: {exc}"}), 500

        session.output = report.output_path if report.ok else None
        gates = [
            {"name": g.name, "ok": g.ok, "detail": g.detail, "meaning": g.meaning}
            for g in report.gates
        ]
        return jsonify({
            "ok": report.ok,
            "gates": gates,
            "removed": report.removed,
            "changed": report.changed,
            "download": f"/api/download/{session.id}" if report.ok else None,
            "saved_path": str(output) if report.ok else None,
            "saved_name": output.name if report.ok else None,
        })

    @app.get("/api/download/<session_id>")
    def download(session_id):
        session = store.sessions.get(session_id)
        if session is None or session.output is None or not session.output.exists():
            return jsonify({"error": "Nothing to download"}), 404
        # Served from memory rather than by path: send_file would leave the
        # handle open until the response is garbage collected.
        return send_file(
            io.BytesIO(session.output.read_bytes()),
            as_attachment=True,
            download_name=session.output.name,
            mimetype="application/octet-stream",
        )

    return app
