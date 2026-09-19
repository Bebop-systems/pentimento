> **Historical note.** These documents were written while the project
> was called `anonymizer`. The package was renamed to `pentimento`
> before the first public release; paths below reflect the old name.

# Photo Metadata Anonymizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web app that inspects a photo or video's metadata, lets the operator edit or remove any of it under coherence checks, and writes a new file whose image bitstream is provably unchanged.

**Architecture:** A persistent ExifTool subprocess is the only I/O boundary. Everything above it — tag classification, presets, the linter — operates on plain dataclasses, so the logic is testable without spawning a process or touching a real file. Writes go to a temp copy and pass four verification gates before the operator is offered a download.

**Tech Stack:** Python 3.14, Flask, vendored ExifTool 13.59 (Windows x64 standalone), vanilla JS with no build step, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-metadata-anonymizer-design.md`

## Global Constraints

- Python 3.14; standard library plus Flask and pytest only. No Pillow, no pillow-heif, no piexif.
- ExifTool version pinned to **13.59**, source `https://sourceforge.net/projects/exiftool/files/exiftool-13.59_64.zip/download`. GitHub publishes tags but no release assets; `exiftool.org/*.zip` returns 404. SourceForge is the only working source.
- `vendor/` is gitignored. No binaries enter git history.
- The input file is never modified. Every write targets a new path.
- ExifTool arguments are passed via args-file/stay_open lines, never via shell string interpolation.
- The server binds `127.0.0.1` only, on a random port.
- Every commit message ends with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/fetch_exiftool.py` | First-run download and extraction of ExifTool into `vendor/` |
| `src/anonymizer/engine.py` | Persistent ExifTool process; the only module that spawns anything |
| `src/anonymizer/model.py` | `Tag`, `TagSet`, `EditOp`, `EditPlan` dataclasses — no I/O |
| `src/anonymizer/inspect.py` | Dual-pass read, merge into a `TagSet` |
| `src/anonymizer/sensitivity.py` | Tag → risk category table |
| `src/anonymizer/payload.py` | Container-aware image-bitstream digest |
| `src/anonymizer/apply.py` | Write plus four-gate verification |
| `src/anonymizer/profiles.py` | Coherent camera identities |
| `src/anonymizer/presets.py` | `TagSet -> EditPlan`, pure |
| `src/anonymizer/linter.py` | Consistency rules over a pending `TagSet` |
| `src/anonymizer/server.py` | Flask routes, session handling |
| `web/index.html`, `web/app.js`, `web/style.css` | Single-page UI |

---

### Task 1: Vendor ExifTool

**Files:**
- Create: `scripts/fetch_exiftool.py`
- Create: `src/anonymizer/__init__.py`
- Test: `tests/test_fetch_exiftool.py`

**Interfaces:**
- Produces: `find_exiftool() -> Path | None`, `ensure_exiftool() -> Path`, `VENDOR_DIR: Path`, `EXIFTOOL_VERSION: str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch_exiftool.py
import pytest
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch_exiftool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/fetch_exiftool.py
"""Fetch the pinned ExifTool build into vendor/.

ExifTool's Windows builds are hosted on SourceForge. The GitHub repo
publishes tags but no release assets, and exiftool.org links out rather
than serving the zip itself, so neither is usable as a download source.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

EXIFTOOL_VERSION = "13.59"
DOWNLOAD_URL = (
    "https://sourceforge.net/projects/exiftool/files/"
    f"exiftool-{EXIFTOOL_VERSION}_64.zip/download"
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = PROJECT_ROOT / "vendor"


def find_exiftool() -> Path | None:
    """Return the vendored exiftool binary, or None if not yet fetched."""
    if not VENDOR_DIR.exists():
        return None
    for name in ("exiftool.exe", "exiftool(-k).exe", "exiftool"):
        for candidate in VENDOR_DIR.rglob(name):
            if candidate.is_file():
                return candidate
    return None


def download() -> Path:
    """Download and extract ExifTool. Returns the binary path."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        DOWNLOAD_URL, headers={"User-Agent": "anonymizer-setup"}
    )
    print(f"Downloading ExifTool {EXIFTOOL_VERSION} ...", file=sys.stderr)
    with urllib.request.urlopen(req, timeout=180) as resp:
        blob = resp.read()
    if not blob.startswith(b"PK\x03\x04"):
        raise RuntimeError(
            f"Expected a zip, got {len(blob)} bytes starting {blob[:16]!r}"
        )
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        zf.extractall(VENDOR_DIR)

    # The standalone build ships as exiftool(-k).exe, which pauses for a
    # keypress on exit. Renaming to exiftool.exe disables that behaviour.
    for k_exe in VENDOR_DIR.rglob("exiftool(-k).exe"):
        k_exe.rename(k_exe.with_name("exiftool.exe"))

    exe = find_exiftool()
    if exe is None:
        raise RuntimeError("Extraction succeeded but no binary was found")
    os.chmod(exe, 0o755)
    return exe


def ensure_exiftool() -> Path:
    """Return the vendored binary, downloading it if absent."""
    existing = find_exiftool()
    if existing is not None:
        return existing
    return download()


if __name__ == "__main__":
    path = ensure_exiftool()
    print(path)
```

Also create an empty `src/anonymizer/__init__.py` and a `tests/__init__.py`, plus `scripts/__init__.py` so the test import resolves. Add `pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = . src
filterwarnings = error
```

- [ ] **Step 4: Run tests and the real fetch**

Run: `python -m pytest tests/test_fetch_exiftool.py -v`
Expected: PASS

Run: `python scripts/fetch_exiftool.py && "$(python scripts/fetch_exiftool.py)" -ver`
Expected: prints `13.59`

- [ ] **Step 5: Commit**

```bash
git add scripts/ src/anonymizer/__init__.py tests/ pytest.ini
git commit -m "feat: vendor pinned ExifTool 13.59"
```

---

### Task 2: ExifTool engine

**Files:**
- Create: `src/anonymizer/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `find_exiftool()` from Task 1
- Produces: `ExifToolEngine` with `.execute(*args) -> ExifToolResult`, `.read_json(path, *extra) -> list[dict]`, `.write(src, dst, arg_lines) -> None`; `ExifToolResult(stdout: str, stderr: str)`; context-manager protocol

**Why stay_open:** ExifTool is Perl; each cold start costs roughly 200 ms. One long-lived process makes per-request cost negligible. The protocol is: write argument lines to stdin, terminate with `-execute{N}`, read stdout until the line `{ready{N}}`. A matching `-echo4` sentinel does the same for stderr, so errors are attributable to the specific command that produced them.

**Deadlock note:** stdout is drained before stderr. Reversing that order can hang, because a large JSON payload fills the stdout pipe buffer while the reader is blocked on stderr.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine.py
import json
import pytest
from anonymizer.engine import ExifToolEngine, ExifToolError
from scripts.fetch_exiftool import find_exiftool

pytestmark = pytest.mark.skipif(find_exiftool() is None, reason="exiftool not vendored")

@pytest.fixture(scope="module")
def engine():
    with ExifToolEngine(find_exiftool()) as e:
        yield e

def test_version(engine):
    assert engine.execute("-ver").stdout.strip() == "13.59"

def test_sequential_commands_do_not_interleave(engine):
    # Each execute must consume exactly its own output.
    a = engine.execute("-ver").stdout.strip()
    b = engine.execute("-ver").stdout.strip()
    assert a == b == "13.59"

def test_read_json_returns_tags(engine, tmp_path):
    f = tmp_path / "t.jpg"
    engine.execute("-o", str(f), "-n", str(f))  # no-op; file made below
    # Build a real JPEG via exiftool's own test pattern instead:
    src = tmp_path / "made.jpg"
    _make_jpeg(src)
    engine.write(src, tmp_path / "out.jpg", ["-EXIF:Model=TestCam"])
    data = engine.read_json(tmp_path / "out.jpg")
    assert data[0]["EXIF:Model"] == "TestCam"

def test_write_does_not_touch_source(engine, tmp_path):
    src = tmp_path / "src.jpg"
    _make_jpeg(src)
    before = src.read_bytes()
    engine.write(src, tmp_path / "dst.jpg", ["-EXIF:Model=Other"])
    assert src.read_bytes() == before

def test_value_containing_option_syntax_is_data_not_instruction(engine, tmp_path):
    src = tmp_path / "s.jpg"
    _make_jpeg(src)
    dst = tmp_path / "d.jpg"
    engine.write(src, dst, ["-EXIF:Model=-delete_original!"])
    data = engine.read_json(dst)
    assert data[0]["EXIF:Model"] == "-delete_original!"

def test_error_surfaces(engine, tmp_path):
    with pytest.raises(ExifToolError):
        engine.read_json(tmp_path / "does-not-exist.jpg")

def _make_jpeg(path):
    """Minimal valid baseline JPEG: 1x1 grey."""
    path.write_bytes(bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300"
        + "08" * 64
        + "ffc2000b080001000101011100ffc4001400010000000000000000000000000000000"
        + "3ffda0008010100000001d2cf20ffd9"
    ))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'anonymizer.engine'`

- [ ] **Step 3: Write the implementation**

```python
# src/anonymizer/engine.py
"""Persistent ExifTool process.

This is the only module permitted to spawn a subprocess. Everything above
it works on dataclasses, which keeps the rest of the codebase testable
without ExifTool present.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ExifToolError(RuntimeError):
    """ExifTool reported an error for a specific command."""


@dataclass(frozen=True)
class ExifToolResult:
    stdout: str
    stderr: str

    @property
    def errors(self) -> list[str]:
        return [
            line
            for line in self.stderr.splitlines()
            if line.strip().lower().startswith("error")
        ]

    @property
    def warnings(self) -> list[str]:
        return [
            line
            for line in self.stderr.splitlines()
            if line.strip().lower().startswith("warning")
        ]


class ExifToolEngine:
    def __init__(self, exiftool_path: Path):
        self.exiftool_path = Path(exiftool_path)
        self._proc: subprocess.Popen | None = None
        self._seq = 0

    def start(self) -> "ExifToolEngine":
        if self._proc is not None:
            return self
        self._proc = subprocess.Popen(
            [str(self.exiftool_path), "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        return self

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.stdin.write("-stay_open\nFalse\n")
            self._proc.stdin.flush()
            self._proc.wait(timeout=10)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self._proc.kill()
        finally:
            self._proc = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    def _read_until(self, stream, sentinel: str) -> str:
        chunks: list[str] = []
        while True:
            line = stream.readline()
            if line == "":
                raise ExifToolError("ExifTool exited unexpectedly")
            if line.rstrip("\r\n") == sentinel:
                return "".join(chunks)
            chunks.append(line)

    def execute(self, *args: str) -> ExifToolResult:
        """Run one ExifTool command. Each arg becomes its own line.

        Because arguments are newline-delimited rather than shell-parsed,
        a tag value that looks like an option is still just a value.
        """
        if self._proc is None:
            self.start()
        self._seq += 1
        seq = self._seq
        lines = [*args, "-echo4", f"{{readyerr{seq}}}", f"-execute{seq}"]
        for line in lines:
            if "\n" in line or "\r" in line:
                raise ExifToolError(f"Argument contains a newline: {line!r}")
        self._proc.stdin.write("\n".join(lines) + "\n")
        self._proc.stdin.flush()
        # Drain stdout first: a large JSON payload can fill the pipe buffer
        # and deadlock if we block on stderr while stdout is unread.
        stdout = self._read_until(self._proc.stdout, f"{{ready{seq}}}")
        stderr = self._read_until(self._proc.stderr, f"{{readyerr{seq}}}")
        return ExifToolResult(stdout, stderr)

    def read_json(self, path: Path, *extra: str) -> list[dict]:
        result = self.execute("-j", "-G1", "-a", "-u", "-struct", *extra, str(path))
        if result.errors:
            raise ExifToolError("; ".join(result.errors))
        text = result.stdout.strip()
        if not text:
            raise ExifToolError(f"No metadata returned for {path}")
        return json.loads(text)

    def write(self, src: Path, dst: Path, arg_lines: list[str]) -> ExifToolResult:
        """Copy src to dst applying arg_lines. src is never modified."""
        import shutil

        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        result = self.execute(*arg_lines, "-overwrite_original", str(dst))
        if result.errors:
            raise ExifToolError("; ".join(result.errors))
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/engine.py tests/test_engine.py
git commit -m "feat: add persistent ExifTool engine with args-file safety"
```

---

### Task 3: Tag model

**Files:**
- Create: `src/anonymizer/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces: `Tag(group, name, value, display)` with `.key`; `TagSet(path, tags: dict[str, Tag])` with `.get(key)`, `.keys()`, `.with_plan(plan) -> TagSet`, `.from_exiftool(path, machine, display) -> TagSet`; `EditOp(key, value: str | None)` with `.is_delete`; `EditPlan(ops)` with `.deletions()`, `.to_args()`, `.merged(other)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model.py
from pathlib import Path
from anonymizer.model import Tag, TagSet, EditOp, EditPlan

def test_tag_key_joins_group_and_name():
    assert Tag("EXIF", "Model", "iPhone", "iPhone").key == "EXIF:Model"

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

def test_editplan_to_args_renders_set_and_delete():
    plan = EditPlan([EditOp("EXIF:Model", "X"), EditOp("GPS:all", None)])
    assert plan.to_args() == ["-EXIF:Model=X", "-GPS:all="]

def test_editplan_deletions_lists_only_deletes():
    plan = EditPlan([EditOp("EXIF:Model", "X"), EditOp("GPS:all", None)])
    assert plan.deletions() == ["GPS:all"]

def test_editplan_merged_lets_later_ops_win():
    a = EditPlan([EditOp("EXIF:Model", "A")])
    b = EditPlan([EditOp("EXIF:Model", "B")])
    assert a.merged(b).to_args() == ["-EXIF:Model=B"]

def test_with_plan_produces_pending_state():
    ts = TagSet.from_exiftool(
        Path("a.jpg"),
        {"EXIF:Model": "iPhone", "GPS:GPSLatitude": 47.0},
        {"EXIF:Model": "iPhone", "GPS:GPSLatitude": "47"},
    )
    pending = ts.with_plan(EditPlan([EditOp("EXIF:Model", "Pixel"), EditOp("GPS:all", None)]))
    assert pending.get("EXIF:Model").value == "Pixel"
    assert pending.get("GPS:GPSLatitude") is None
    # original is unchanged
    assert ts.get("EXIF:Model").value == "iPhone"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'anonymizer.model'`

- [ ] **Step 3: Write the implementation**

```python
# src/anonymizer/model.py
"""Plain data structures. No I/O, no ExifTool knowledge."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# Groups ExifTool reports that describe the file rather than its metadata.
_FILE_GROUPS = {"File", "ExifTool", "Composite"}


@dataclass(frozen=True)
class Tag:
    group: str
    name: str
    value: Any
    display: str

    @property
    def key(self) -> str:
        return f"{self.group}:{self.name}"


@dataclass(frozen=True)
class EditOp:
    key: str
    value: str | None  # None means delete

    @property
    def is_delete(self) -> bool:
        return self.value is None


@dataclass(frozen=True)
class EditPlan:
    ops: tuple[EditOp, ...] = ()

    def __init__(self, ops=()):
        object.__setattr__(self, "ops", tuple(ops))

    def deletions(self) -> list[str]:
        return [op.key for op in self.ops if op.is_delete]

    def to_args(self) -> list[str]:
        return [f"-{op.key}=" + ("" if op.is_delete else str(op.value)) for op in self.ops]

    def merged(self, other: "EditPlan") -> "EditPlan":
        """Combine two plans; ops in `other` override matching keys."""
        by_key: dict[str, EditOp] = {}
        for op in (*self.ops, *other.ops):
            by_key[op.key] = op
        return EditPlan(tuple(by_key.values()))

    def __bool__(self) -> bool:
        return bool(self.ops)


@dataclass(frozen=True)
class TagSet:
    path: Path
    tags: dict[str, Tag] = field(default_factory=dict)

    @classmethod
    def from_exiftool(cls, path: Path, machine: dict, display: dict) -> "TagSet":
        tags: dict[str, Tag] = {}
        for key, value in machine.items():
            if key == "SourceFile" or ":" not in key:
                continue
            group, _, name = key.partition(":")
            shown = display.get(key, value)
            tags[key] = Tag(group, name, value, str(shown))
        return cls(path=path, tags=tags)

    def get(self, key: str) -> Tag | None:
        return self.tags.get(key)

    def keys(self) -> set[str]:
        return set(self.tags)

    def by_name(self, name: str) -> Tag | None:
        """First tag matching a bare name, ignoring group."""
        for tag in self.tags.values():
            if tag.name == name:
                return tag
        return None

    def with_plan(self, plan: EditPlan) -> "TagSet":
        """Return the state this TagSet would have after `plan` applies.

        `Group:all` deletes every tag in that group; `all` deletes everything.
        """
        tags = dict(self.tags)
        for op in plan.ops:
            group, _, name = op.key.partition(":")
            if op.is_delete:
                if op.key in ("all", "All"):
                    tags.clear()
                elif name.lower() == "all":
                    for key in [k for k in tags if k.split(":")[0] == group]:
                        del tags[key]
                else:
                    tags.pop(op.key, None)
            else:
                existing = tags.get(op.key)
                tags[op.key] = Tag(group, name, op.value, str(op.value)) if existing is None \
                    else replace(existing, value=op.value, display=str(op.value))
        return TagSet(path=self.path, tags=tags)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/model.py tests/test_model.py
git commit -m "feat: add Tag, TagSet and EditPlan data model"
```

---

### Task 4: Inspection

**Files:**
- Create: `src/anonymizer/inspect.py`
- Test: `tests/test_inspect.py`

**Interfaces:**
- Consumes: `ExifToolEngine`, `TagSet`
- Produces: `read_tags(engine, path) -> TagSet`

The dual pass exists so the UI can show a machine value for editing and a
human value for reading. `-n` disables ExifTool's print conversion.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inspect.py
from pathlib import Path
from anonymizer.inspect import read_tags

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
    ts = read_tags(engine, Path("a.jpg"))
    assert ("-n",) in engine.calls
    assert () in engine.calls

def test_read_tags_merges_passes():
    ts = read_tags(FakeEngine(), Path("a.jpg"))
    tag = ts.get("GPS:GPSLatitude")
    assert tag.value == 47.62089
    assert tag.display == "47 deg N"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_inspect.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/anonymizer/inspect.py
"""Read a file's metadata into a TagSet."""
from __future__ import annotations

from pathlib import Path

from .model import TagSet


def read_tags(engine, path: Path) -> TagSet:
    """Two passes: -n for machine values, plain for display values."""
    path = Path(path)
    machine = engine.read_json(path, "-n")[0]
    display = engine.read_json(path)[0]
    return TagSet.from_exiftool(path, machine, display)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_inspect.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/inspect.py tests/test_inspect.py
git commit -m "feat: add dual-pass metadata inspection"
```

---

### Task 5: Sensitivity classification

**Files:**
- Create: `src/anonymizer/sensitivity.py`
- Test: `tests/test_sensitivity.py`

**Interfaces:**
- Produces: `Category` (StrEnum: `LOCATION`, `DEVICE`, `TIME`, `CONTENT`, `SOFTWARE`, `EMBEDDED`, `BENIGN`), `classify(tag: Tag) -> Category`, `categorize(tagset) -> dict[Category, list[Tag]]`, `RENDERING_CRITICAL: frozenset[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sensitivity.py
import pytest
from anonymizer.model import Tag
from anonymizer.sensitivity import Category, classify, RENDERING_CRITICAL

@pytest.mark.parametrize("group,name,expected", [
    ("GPS", "GPSLatitude", Category.LOCATION),
    ("GPS", "GPSAltitude", Category.LOCATION),
    ("QuickTime", "GPSCoordinates", Category.LOCATION),
    ("XMP-iptcExt", "LocationCreatedCity", Category.LOCATION),
    ("EXIF", "SerialNumber", Category.DEVICE),
    ("EXIF", "BodySerialNumber", Category.DEVICE),
    ("EXIF", "OwnerName", Category.DEVICE),
    ("IFD0", "Artist", Category.DEVICE),
    ("EXIF", "DateTimeOriginal", Category.TIME),
    ("EXIF", "OffsetTimeOriginal", Category.TIME),
    ("EXIF", "SubSecTimeOriginal", Category.TIME),
    ("XMP-mwg-rs", "RegionName", Category.CONTENT),
    ("IPTC", "Keywords", Category.CONTENT),
    ("IFD0", "Software", Category.SOFTWARE),
    ("XMP-xmpMM", "InstanceID", Category.SOFTWARE),
    ("IFD1", "ThumbnailImage", Category.EMBEDDED),
    ("EXIF", "PreviewImage", Category.EMBEDDED),
    ("IFD0", "Orientation", Category.BENIGN),
    ("EXIF", "ColorSpace", Category.BENIGN),
])
def test_classification(group, name, expected):
    assert classify(Tag(group, name, "x", "x")) == expected

def test_makernotes_group_is_content_by_default():
    assert classify(Tag("Apple", "SceneFlags", 1, "1")) == Category.CONTENT

def test_rendering_critical_never_classified_sensitive():
    for name in RENDERING_CRITICAL:
        assert classify(Tag("EXIF", name, "x", "x")) == Category.BENIGN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sensitivity.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Classification is a data table keyed by exact name, with a glob fallback and a
group fallback. Adding a tag is a one-line change.

```python
# src/anonymizer/sensitivity.py
"""Which tags identify the operator, their device, or their subject."""
from __future__ import annotations

import fnmatch
from enum import StrEnum

from .model import Tag, TagSet


class Category(StrEnum):
    LOCATION = "location"
    DEVICE = "device"
    TIME = "time"
    CONTENT = "content"
    SOFTWARE = "software"
    EMBEDDED = "embedded"
    BENIGN = "benign"


# Tags that affect how the image renders. Never treated as sensitive, and
# preserved even by the most aggressive preset.
RENDERING_CRITICAL = frozenset({
    "Orientation", "ColorSpace", "ICC_Profile", "ProfileDescription",
    "ExifImageWidth", "ExifImageHeight", "ImageWidth", "ImageHeight",
    "Rotation", "BitsPerSample", "SamplesPerPixel", "PhotometricInterpretation",
    "YCbCrPositioning", "YCbCrSubSampling", "ComponentsConfiguration",
    "XResolution", "YResolution", "ResolutionUnit", "InteropIndex",
    "Gamma", "PrimaryChromaticities", "WhitePoint", "TransferFunction",
})

_EXACT: dict[str, Category] = {}


def _register(category: Category, *names: str) -> None:
    for name in names:
        _EXACT[name] = category


_register(
    Category.LOCATION,
    "GPSLatitude", "GPSLongitude", "GPSAltitude", "GPSLatitudeRef",
    "GPSLongitudeRef", "GPSAltitudeRef", "GPSPosition", "GPSCoordinates",
    "GPSHPositioningError", "GPSDestLatitude", "GPSDestLongitude",
    "GPSImgDirection", "GPSImgDirectionRef", "GPSSpeed", "GPSTrack",
    "GPSAreaInformation", "GPSMapDatum", "GPSProcessingMethod",
    "LocationCreatedCity", "LocationCreatedCountryName", "LocationCreatedSublocation",
    "LocationCreatedProvinceState", "LocationShownCity", "LocationShownCountryName",
    "Country", "Province-State", "City", "Sub-location", "CountryCode",
    "LocationName", "SubjectLocation",
)
_register(
    Category.DEVICE,
    "SerialNumber", "BodySerialNumber", "LensSerialNumber", "InternalSerialNumber",
    "CameraSerialNumber", "OwnerName", "CameraOwnerName", "Artist", "Creator",
    "By-line", "HostComputer", "CameraID", "ImageUniqueID", "LensID",
    "Copyright", "Rights", "CreatorWorkEmail", "CreatorWorkURL", "Credit",
)
_register(
    Category.TIME,
    "DateTimeOriginal", "CreateDate", "ModifyDate", "DateCreated",
    "OffsetTime", "OffsetTimeOriginal", "OffsetTimeDigitized",
    "SubSecTime", "SubSecTimeOriginal", "SubSecTimeDigitized",
    "SubSecCreateDate", "SubSecDateTimeOriginal", "SubSecModifyDate",
    "GPSDateStamp", "GPSTimeStamp", "GPSDateTime", "TimeZoneOffset",
    "DigitalCreationDate", "DigitalCreationTime", "MediaCreateDate",
    "MediaModifyDate", "TrackCreateDate", "TrackModifyDate",
)
_register(
    Category.CONTENT,
    "RegionName", "RegionType", "RegionAreaX", "RegionAreaY", "RegionInfo",
    "Keywords", "Subject", "Caption-Abstract", "Description", "Title",
    "ObjectName", "SpecialInstructions", "UserComment", "ImageDescription",
    "Rating", "RatingPercent", "Label", "PersonInImage", "SceneCaptureType",
)
_register(
    Category.SOFTWARE,
    "Software", "ProcessingSoftware", "CreatorTool", "HistorySoftwareAgent",
    "HistoryAction", "HistoryWhen", "HistoryChanged", "HistoryInstanceID",
    "DocumentID", "InstanceID", "OriginalDocumentID", "DerivedFromInstanceID",
    "DerivedFromDocumentID", "ApplicationRecordVersion", "OriginatingProgram",
    "ProgramVersion", "Encoder", "WritingApp",
)
_register(
    Category.EMBEDDED,
    "ThumbnailImage", "PreviewImage", "OtherImage", "JpgFromRaw",
    "ThumbnailTIFF", "PhotoshopThumbnail", "PreviewPICT", "EmbeddedImage",
)

# Checked in order after an exact miss.
_GLOBS: tuple[tuple[str, Category], ...] = (
    ("GPS*", Category.LOCATION),
    ("*SerialNumber*", Category.DEVICE),
    ("History*", Category.SOFTWARE),
    ("Region*", Category.CONTENT),
    ("Thumbnail*", Category.EMBEDDED),
    ("Preview*", Category.EMBEDDED),
    ("*DateTime*", Category.TIME),
    ("OffsetTime*", Category.TIME),
    ("SubSecTime*", Category.TIME),
)

# Group-level fallback. MakerNotes are vendor blobs holding scene analysis,
# face detection and sometimes location, so they default to CONTENT.
_GROUP_FALLBACK: dict[str, Category] = {
    "GPS": Category.LOCATION,
    "Apple": Category.CONTENT,
    "Canon": Category.CONTENT,
    "Nikon": Category.CONTENT,
    "Sony": Category.CONTENT,
    "MakerNotes": Category.CONTENT,
    "XMP-mwg-rs": Category.CONTENT,
    "XMP-xmpMM": Category.SOFTWARE,
}


def classify(tag: Tag) -> Category:
    if tag.name in RENDERING_CRITICAL:
        return Category.BENIGN
    exact = _EXACT.get(tag.name)
    if exact is not None:
        return exact
    for pattern, category in _GLOBS:
        if fnmatch.fnmatch(tag.name, pattern):
            return category
    return _GROUP_FALLBACK.get(tag.group, Category.BENIGN)


def categorize(tagset: TagSet) -> dict[Category, list[Tag]]:
    out: dict[Category, list[Tag]] = {c: [] for c in Category}
    for tag in tagset.tags.values():
        out[classify(tag)].append(tag)
    for tags in out.values():
        tags.sort(key=lambda t: t.key)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sensitivity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/sensitivity.py tests/test_sensitivity.py
git commit -m "feat: add tag sensitivity classification"
```

---

### Task 6: Payload digest

**Files:**
- Create: `src/anonymizer/payload.py`
- Test: `tests/test_payload.py`

**Interfaces:**
- Produces: `payload_digest(path) -> str | None`, `container_of(path) -> str`

This is gate G3. It isolates the image bitstream from the metadata that
legitimately changed, so the tool can prove pixels were untouched.

**Box-walking note:** ISO-BMFF box size `1` means a 64-bit size follows the
type; size `0` means the box runs to EOF. The sample HEIC uses size `1`, so
both cases are exercised by real input.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_payload.py
import struct
import pytest
from anonymizer.payload import payload_digest, container_of

def _box(typ: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body) + 8) + typ + body

def test_container_detection_isobmff(tmp_path):
    f = tmp_path / "a.heic"
    f.write_bytes(_box(b"ftyp", b"heic" + b"\0" * 8) + _box(b"mdat", b"PIXELS"))
    assert container_of(f) == "isobmff"

def test_isobmff_digest_ignores_metadata_changes(tmp_path):
    a = tmp_path / "a.heic"
    b = tmp_path / "b.heic"
    a.write_bytes(_box(b"ftyp", b"heic" + b"\0" * 8) + _box(b"meta", b"AAAA") + _box(b"mdat", b"PIXELS"))
    b.write_bytes(_box(b"ftyp", b"heic" + b"\0" * 8) + _box(b"meta", b"BBBBBBBB") + _box(b"mdat", b"PIXELS"))
    assert payload_digest(a) == payload_digest(b)

def test_isobmff_digest_detects_pixel_changes(tmp_path):
    a = tmp_path / "a.heic"
    b = tmp_path / "b.heic"
    a.write_bytes(_box(b"ftyp", b"heic" + b"\0" * 8) + _box(b"mdat", b"PIXELS"))
    b.write_bytes(_box(b"ftyp", b"heic" + b"\0" * 8) + _box(b"mdat", b"PIXELT"))
    assert payload_digest(a) != payload_digest(b)

def test_isobmff_handles_64bit_box_size(tmp_path):
    f = tmp_path / "big.heic"
    body = b"PIXELS"
    large = struct.pack(">I", 1) + b"mdat" + struct.pack(">Q", len(body) + 16) + body
    f.write_bytes(_box(b"ftyp", b"heic" + b"\0" * 8) + large)
    assert payload_digest(f) is not None

def test_png_digest_ignores_text_chunks(tmp_path):
    import zlib
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\x00"))
    iend = chunk(b"IEND", b"")
    a = tmp_path / "a.png"; a.write_bytes(sig + ihdr + idat + iend)
    b = tmp_path / "b.png"; b.write_bytes(sig + ihdr + chunk(b"tEXt", b"k\x00v") + idat + iend)
    assert container_of(a) == "png"
    assert payload_digest(a) == payload_digest(b)

def test_unknown_container_returns_none(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"NOTANIMAGE")
    assert payload_digest(f) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_payload.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/anonymizer/payload.py
"""Digest the image bitstream, ignoring metadata containers.

Gate G3 compares this digest before and after a write. Equal digests mean
no pixel data moved, which is what "compatible output" has to mean.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def container_of(path: Path) -> str:
    with open(path, "rb") as fh:
        head = fh.read(16)
    if head[:8] == _PNG_SIG:
        return "png"
    if head[:2] == b"\xff\xd8":
        return "jpeg"
    if head[4:8] == b"ftyp":
        return "isobmff"
    if head[:4] in (b"II\x2a\x00", b"MM\x00\x2a"):
        return "tiff"
    return "unknown"


def _digest_isobmff(fh, size: int) -> bytes:
    """Concatenate every mdat box body."""
    h = hashlib.sha256()
    pos = 0
    while pos + 8 <= size:
        fh.seek(pos)
        header = fh.read(8)
        if len(header) < 8:
            break
        box_size = struct.unpack(">I", header[:4])[0]
        box_type = header[4:8]
        body_start = pos + 8
        if box_size == 1:
            ext = fh.read(8)
            if len(ext) < 8:
                break
            box_size = struct.unpack(">Q", ext)[0]
            body_start = pos + 16
        elif box_size == 0:
            box_size = size - pos
        if box_size < 8:
            break
        if box_type == b"mdat":
            remaining = pos + box_size - body_start
            fh.seek(body_start)
            while remaining > 0:
                block = fh.read(min(1 << 20, remaining))
                if not block:
                    break
                h.update(block)
                remaining -= len(block)
        pos += box_size
    return h.digest()


def _digest_jpeg(data: bytes) -> bytes:
    """Hash entropy-coded scan data, skipping all marker segments."""
    h = hashlib.sha256()
    i = 2
    n = len(data)
    while i < n - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xD9:
            break
        if i + 4 > n:
            break
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker == 0xDA:  # start of scan: entropy data follows
            start = i + 2 + seg_len
            j = start
            while j < n - 1:
                if data[j] == 0xFF and data[j + 1] != 0x00 and not (
                    0xD0 <= data[j + 1] <= 0xD7
                ):
                    break
                j += 1
            h.update(data[start:j])
            i = j
            continue
        i += 2 + seg_len
    return h.digest()


def _digest_png(data: bytes) -> bytes:
    h = hashlib.sha256()
    i = len(_PNG_SIG)
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        body = data[i + 8:i + 8 + length]
        if ctype == b"IDAT":
            h.update(body)
        if ctype == b"IEND":
            break
        i += 12 + length
    return h.digest()


def _digest_tiff(data: bytes) -> bytes:
    """Hash strip and tile data referenced by the first IFD."""
    endian = "<" if data[:2] == b"II" else ">"
    h = hashlib.sha256()
    try:
        ifd_off = struct.unpack(endian + "I", data[4:8])[0]
        count = struct.unpack(endian + "H", data[ifd_off:ifd_off + 2])[0]
        offsets: list[int] = []
        counts: list[int] = []
        for k in range(count):
            e = ifd_off + 2 + k * 12
            tag, typ, num = struct.unpack(endian + "HHI", data[e:e + 8])
            raw = data[e + 8:e + 12]
            if tag in (273, 324, 279, 325):
                vals = []
                if typ == 3 and num == 1:
                    vals = [struct.unpack(endian + "H", raw[:2])[0]]
                elif typ == 4 and num == 1:
                    vals = [struct.unpack(endian + "I", raw)[0]]
                else:
                    ptr = struct.unpack(endian + "I", raw)[0]
                    width = 2 if typ == 3 else 4
                    fmt = "H" if typ == 3 else "I"
                    for m in range(num):
                        vals.append(struct.unpack(
                            endian + fmt, data[ptr + m * width:ptr + (m + 1) * width]
                        )[0])
                if tag in (273, 324):
                    offsets = vals
                else:
                    counts = vals
        for off, cnt in zip(offsets, counts):
            h.update(data[off:off + cnt])
    except (struct.error, IndexError):
        return b""
    return h.digest()


def payload_digest(path: Path) -> str | None:
    """Hex digest of the image bitstream, or None for unknown containers."""
    path = Path(path)
    kind = container_of(path)
    if kind == "unknown":
        return None
    size = path.stat().st_size
    if kind == "isobmff":
        with open(path, "rb") as fh:
            return _digest_isobmff(fh, size).hex()
    data = path.read_bytes()
    if kind == "jpeg":
        return _digest_jpeg(data).hex()
    if kind == "png":
        return _digest_png(data).hex()
    if kind == "tiff":
        digest = _digest_tiff(data)
        return digest.hex() if digest else None
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_payload.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/payload.py tests/test_payload.py
git commit -m "feat: add container-aware image payload digest"
```

---

### Task 7: Apply with four-gate verification

**Files:**
- Create: `src/anonymizer/apply.py`
- Test: `tests/test_apply.py`

**Interfaces:**
- Consumes: `ExifToolEngine`, `EditPlan`, `read_tags`, `payload_digest`
- Produces: `GateResult(name, ok, detail)`, `VerificationReport(ok, gates, output_path)`, `apply_plan(engine, src, dst, plan) -> VerificationReport`, `GateFailure` exception, `RENDER_TAGS: tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_apply.py
import pytest
from pathlib import Path
from anonymizer.apply import apply_plan, VerificationReport
from anonymizer.model import EditOp, EditPlan
from anonymizer.engine import ExifToolEngine
from anonymizer.inspect import read_tags
from scripts.fetch_exiftool import find_exiftool

pytestmark = pytest.mark.skipif(find_exiftool() is None, reason="exiftool not vendored")

@pytest.fixture(scope="module")
def engine():
    with ExifToolEngine(find_exiftool()) as e:
        yield e

@pytest.fixture
def jpeg_with_gps(engine, tmp_path):
    src = tmp_path / "in.jpg"
    src.write_bytes(bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300"
        + "08" * 64
        + "ffc2000b080001000101011100ffc4001400010000000000000000000000000000000"
        + "3ffda0008010100000001d2cf20ffd9"
    ))
    engine.write(src, src, [
        "-EXIF:Model=iPhone 15 Pro", "-EXIF:Make=Apple",
        "-GPS:GPSLatitude=47.62089", "-GPS:GPSLatitudeRef=N",
        "-EXIF:Orientation=1",
    ])
    return src

def test_apply_removes_gps_and_passes_all_gates(engine, jpeg_with_gps, tmp_path):
    out = tmp_path / "out.jpg"
    report = apply_plan(engine, jpeg_with_gps, out, EditPlan([EditOp("GPS:all", None)]))
    assert report.ok, report.gates
    assert {g.name for g in report.gates if g.ok} >= {
        "structural", "rendering", "payload", "regression"
    }
    after = read_tags(engine, out)
    assert not [k for k in after.keys() if k.startswith("GPS:")]

def test_apply_preserves_image_payload(engine, jpeg_with_gps, tmp_path):
    from anonymizer.payload import payload_digest
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
    assert read_tags(engine, out).get("EXIF:Model").value == "Pixel 9"

def test_regression_gate_catches_surviving_tag(engine, jpeg_with_gps, tmp_path, monkeypatch):
    """A plan claiming to delete a tag that survives must fail G4."""
    import anonymizer.apply as ap
    real_write = engine.write
    def sneaky_write(src, dst, args):
        return real_write(src, dst, [a for a in args if not a.startswith("-GPS")])
    monkeypatch.setattr(engine, "write", sneaky_write)
    out = tmp_path / "out.jpg"
    report = apply_plan(engine, jpeg_with_gps, out, EditPlan([EditOp("GPS:all", None)]))
    assert not report.ok
    assert any(g.name == "regression" and not g.ok for g in report.gates)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_apply.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/anonymizer/apply.py
"""Write a plan and verify the result before anyone is allowed to use it.

A partially-scrubbed file is more dangerous than no file, because the
operator believes it is clean. Every gate must pass or the output is
discarded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .inspect import read_tags
from .model import EditPlan, TagSet
from .payload import payload_digest

# Tags whose change would alter how the file renders.
RENDER_TAGS: tuple[str, ...] = (
    "ImageWidth", "ImageHeight", "Orientation", "Rotation",
    "ColorSpace", "BitsPerSample", "YCbCrSubSampling",
)


class GateFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class GateResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class VerificationReport:
    output_path: Path
    gates: list[GateResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(g.ok for g in self.gates)

    @property
    def failures(self) -> list[GateResult]:
        return [g for g in self.gates if not g.ok]


def _gate_structural(engine, src: Path, dst: Path) -> GateResult:
    try:
        before = engine.read_json(src, "-FileType", "-MIMEType")[0]
        after = engine.read_json(dst, "-FileType", "-MIMEType")[0]
    except Exception as exc:
        return GateResult("structural", False, f"output unreadable: {exc}")
    for key in ("File:FileType", "File:MIMEType"):
        if before.get(key) != after.get(key):
            return GateResult(
                "structural", False,
                f"{key} changed: {before.get(key)} -> {after.get(key)}",
            )
    return GateResult("structural", True, str(after.get("File:FileType", "")))


def _gate_rendering(before: TagSet, after: TagSet) -> GateResult:
    for name in RENDER_TAGS:
        b = before.by_name(name)
        a = after.by_name(name)
        bv = None if b is None else b.value
        av = None if a is None else a.value
        if bv != av:
            return GateResult("rendering", False, f"{name} changed: {bv} -> {av}")
    return GateResult("rendering", True, "dimensions, orientation and colour intact")


def _gate_payload(src: Path, dst: Path) -> GateResult:
    before = payload_digest(src)
    after = payload_digest(dst)
    if before is None or after is None:
        return GateResult("payload", True, "container unsupported - payload unverified")
    if before != after:
        return GateResult("payload", False, "image bitstream changed")
    return GateResult("payload", True, f"bitstream identical ({before[:12]})")


def _gate_regression(plan: EditPlan, after: TagSet) -> GateResult:
    survivors: list[str] = []
    for key in plan.deletions():
        group, _, name = key.partition(":")
        if name.lower() == "all":
            survivors += [k for k in after.keys() if k.split(":")[0] == group]
        elif key in ("all", "All"):
            survivors += list(after.keys())
        elif after.get(key) is not None:
            survivors.append(key)
    if survivors:
        return GateResult(
            "regression", False,
            f"{len(survivors)} tag(s) survived deletion: {', '.join(sorted(survivors)[:5])}",
        )
    return GateResult("regression", True, f"{len(plan.deletions())} deletion(s) confirmed")


def apply_plan(engine, src: Path, dst: Path, plan: EditPlan) -> VerificationReport:
    """Apply `plan` to a copy of `src` at `dst`, then verify. src is untouched."""
    src, dst = Path(src), Path(dst)
    before = read_tags(engine, src)

    args = plan.to_args() or ["-overwrite_original"]
    engine.write(src, dst, args)

    after = read_tags(engine, dst)
    report = VerificationReport(output_path=dst)
    report.gates = [
        _gate_structural(engine, src, dst),
        _gate_rendering(before, after),
        _gate_payload(src, dst),
        _gate_regression(plan, after),
    ]
    if not report.ok:
        dst.unlink(missing_ok=True)
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_apply.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/apply.py tests/test_apply.py
git commit -m "feat: add four-gate write verification"
```

---

### Task 8: Camera profiles and presets

**Files:**
- Create: `src/anonymizer/profiles.py`
- Create: `src/anonymizer/presets.py`
- Test: `tests/test_presets.py`

**Interfaces:**
- Consumes: `TagSet`, `EditPlan`, `Category`, `classify`
- Produces: `CameraProfile(key, make, model, lens_model, focal_length, f_number, software)`, `PROFILES: dict[str, CameraProfile]`; `PRESETS: dict[str, str]` (key → description), `build_plan(tagset, preset, options) -> EditPlan`

Presets are pure functions of a `TagSet`. No I/O means every preset is tested
against a synthetic input.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_presets.py
from pathlib import Path
from anonymizer.model import TagSet
from anonymizer.presets import build_plan, PRESETS
from anonymizer.profiles import PROFILES

def _ts(**kw):
    machine = {f"{k.replace('__', ':')}": v for k, v in kw.items()}
    return TagSet.from_exiftool(Path("a.heic"), machine, machine)

def test_presets_are_registered():
    assert set(PRESETS) == {"clean", "plausible", "reprofile", "manual"}

def test_manual_produces_empty_plan():
    plan = build_plan(_ts(EXIF__Model="iPhone"), "manual", {})
    assert plan.to_args() == []

def test_clean_deletes_all_but_keeps_rendering_tags():
    plan = build_plan(_ts(EXIF__Model="iPhone", EXIF__Orientation=1), "clean", {})
    args = plan.to_args()
    assert "-all=" in args
    assert any(a.startswith("-tagsfromfile") for a in args)

def test_plausible_removes_gps_entirely():
    ts = _ts(GPS__GPSLatitude=47.6, GPS__GPSLatitudeRef="N", EXIF__Model="iPhone 15 Pro")
    plan = build_plan(ts, "plausible", {})
    assert "-GPS:all=" in plan.to_args()

def test_plausible_keeps_camera_identity():
    ts = _ts(EXIF__Make="Apple", EXIF__Model="iPhone 15 Pro", GPS__GPSLatitude=47.6)
    plan = build_plan(ts, "plausible", {})
    pending = ts.with_plan(plan)
    assert pending.get("EXIF:Model").value == "iPhone 15 Pro"

def test_plausible_removes_serials_and_faces():
    ts = _ts(EXIF__SerialNumber="F2LW1", **{"XMP-mwg-rs__RegionName": "Alice"})
    plan = build_plan(ts, "plausible", {})
    deleted = set(plan.deletions())
    assert "EXIF:SerialNumber" in deleted
    assert "XMP-mwg-rs:RegionName" in deleted

def test_plausible_removes_embedded_thumbnails():
    ts = _ts(IFD1__ThumbnailImage="(binary)")
    assert "IFD1:ThumbnailImage" in build_plan(ts, "plausible", {}).deletions()

def test_reprofile_rewrites_identity_consistently():
    ts = _ts(EXIF__Make="Apple", EXIF__Model="iPhone 15 Pro")
    plan = build_plan(ts, "reprofile", {"profile": "pixel-8"})
    args = dict(a[1:].split("=", 1) for a in plan.to_args() if not a.endswith("="))
    p = PROFILES["pixel-8"]
    assert args["EXIF:Make"] == p.make
    assert args["EXIF:Model"] == p.model
    assert args["EXIF:LensModel"] == p.lens_model

def test_time_shift_moves_all_time_tags_together():
    ts = _ts(EXIF__DateTimeOriginal="2026:09:14 10:00:00",
             EXIF__CreateDate="2026:09:14 10:00:00")
    plan = build_plan(ts, "plausible", {"time_shift_days": 3})
    args = plan.to_args()
    assert any("AllDates" in a for a in args)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_presets.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementations**

```python
# src/anonymizer/profiles.py
"""Internally-consistent camera identities.

Every field in a profile has to agree with every other. A body paired with
a lens it never shipped with is the kind of contradiction the linter exists
to catch, so the source data must not contain any.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraProfile:
    key: str
    make: str
    model: str
    lens_model: str
    focal_length: str
    f_number: str
    software: str


PROFILES: dict[str, CameraProfile] = {
    p.key: p for p in [
        CameraProfile("iphone-15-pro", "Apple", "iPhone 15 Pro",
                      "iPhone 15 Pro back triple camera 6.765mm f/1.78",
                      "6.765", "1.78", "17.5.1"),
        CameraProfile("iphone-13", "Apple", "iPhone 13",
                      "iPhone 13 back dual wide camera 5.1mm f/1.6",
                      "5.1", "1.6", "16.6"),
        CameraProfile("pixel-8", "Google", "Pixel 8",
                      "Pixel 8 back camera 6.9mm f/1.68",
                      "6.9", "1.68", "HDR+ 1.0.640190411zd"),
        CameraProfile("galaxy-s23", "samsung", "SM-S911B",
                      "Galaxy S23 Rear Camera",
                      "5.4", "1.8", "S911BXXU3BWL1"),
    ]
}
```

```python
# src/anonymizer/presets.py
"""Preset -> EditPlan. Pure functions; no I/O."""
from __future__ import annotations

from .model import EditOp, EditPlan, TagSet
from .profiles import PROFILES
from .sensitivity import Category, classify

PRESETS: dict[str, str] = {
    "clean": "Remove everything identifying. Visibly scrubbed, maximally private.",
    "plausible": "Keep a coherent camera identity; drop location, serials, "
                 "faces and thumbnails as a device with location off would.",
    "reprofile": "Adopt a different, internally consistent camera identity.",
    "manual": "Change nothing automatically.",
}

# Preserved even by `clean`, because losing them changes how the file renders.
_KEEP_ON_CLEAN = (
    "-Orientation", "-ColorSpace", "-ICC_Profile",
    "-ExifImageWidth", "-ExifImageHeight",
    "-XResolution", "-YResolution", "-ResolutionUnit",
)

# Categories each preset strips wholesale.
_STRIP: dict[str, tuple[Category, ...]] = {
    "plausible": (
        Category.LOCATION, Category.CONTENT,
        Category.SOFTWARE, Category.EMBEDDED,
    ),
    "reprofile": (
        Category.LOCATION, Category.CONTENT,
        Category.SOFTWARE, Category.EMBEDDED,
    ),
}


def build_plan(tagset: TagSet, preset: str, options: dict) -> EditPlan:
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}")
    if preset == "manual":
        return EditPlan()
    if preset == "clean":
        return _clean_plan()

    ops: list[EditOp] = [EditOp("GPS:all", None)]

    for tag in tagset.tags.values():
        category = classify(tag)
        if category in _STRIP[preset]:
            ops.append(EditOp(tag.key, None))
        elif category is Category.DEVICE:
            # Serials and owner names go; make/model stay for coherence.
            ops.append(EditOp(tag.key, None))

    if preset == "reprofile":
        ops += _reprofile_ops(options.get("profile", "iphone-15-pro"))

    shift = int(options.get("time_shift_days") or 0)
    if shift:
        sign = "+" if shift > 0 else "-"
        ops.append(EditOp("AllDates", f"{sign}={abs(shift)}:0:0 0"))

    # Deduplicate, later ops winning.
    return EditPlan(()).merged(EditPlan(ops))


def _clean_plan() -> EditPlan:
    """`-all=` then restore rendering-critical tags from the original."""
    plan = EditPlan([EditOp("all", None)])
    restore = EditPlan([
        EditOp("tagsfromfile", "@"),
        *[EditOp(name.lstrip("-"), "") for name in ()],
    ])
    # tagsfromfile plus explicit tag names must appear as raw args, so they
    # are appended by to_args order; represent them as set-ops with no value.
    ops = list(plan.ops) + [EditOp("tagsfromfile", "@")]
    return EditPlan(ops)


def _reprofile_ops(profile_key: str) -> list[EditOp]:
    profile = PROFILES.get(profile_key)
    if profile is None:
        raise ValueError(f"Unknown profile: {profile_key}")
    return [
        EditOp("EXIF:Make", profile.make),
        EditOp("EXIF:Model", profile.model),
        EditOp("EXIF:LensModel", profile.lens_model),
        EditOp("EXIF:LensMake", profile.make),
        EditOp("EXIF:FocalLength", profile.focal_length),
        EditOp("EXIF:FNumber", profile.f_number),
        EditOp("EXIF:Software", profile.software),
    ]
```

**Note for the implementer:** `_clean_plan` as written renders
`-all=` followed by `-tagsfromfile=@`, but ExifTool expects
`-tagsfromfile @` as two arguments followed by bare `-TAG` names. Task 8's
test only asserts the args contain `-all=` and something starting with
`-tagsfromfile`. When wiring `apply.py`, special-case the `clean` preset so
it emits the literal argument sequence:

```python
["-all=", "-tagsfromfile", "@", *_KEEP_ON_CLEAN, "-overwrite_original"]
```

Add `EditPlan.to_args()` handling for this by giving `EditPlan` an optional
`raw_args: tuple[str, ...]` field that, when present, replaces the rendered
args entirely. Update `model.py` and its test accordingly in this task.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_presets.py tests/test_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/profiles.py src/anonymizer/presets.py src/anonymizer/model.py tests/
git commit -m "feat: add camera profiles and metadata presets"
```

---

### Task 9: Consistency linter

**Files:**
- Create: `src/anonymizer/linter.py`
- Test: `tests/test_linter.py`

**Interfaces:**
- Consumes: `TagSet`
- Produces: `Finding(rule, severity, message)`, `lint(tagset) -> list[Finding]`, `RULES: tuple[Callable[[TagSet], list[Finding]], ...]`

Each rule is an independent function, so adding one requires no dispatcher
change. Severity is `"warning"` or `"note"`. The linter never blocks.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_linter.py
from pathlib import Path
from anonymizer.model import TagSet
from anonymizer.linter import lint

def _ts(name="a.heic", **kw):
    m = {k.replace("__", ":"): v for k, v in kw.items()}
    return TagSet.from_exiftool(Path(name), m, m)

def _rules(findings):
    return {f.rule for f in findings}

def test_clean_file_produces_no_findings():
    ts = _ts(EXIF__Make="Apple", EXIF__Model="iPhone 15 Pro",
             EXIF__Software="17.5.1", EXIF__FocalLength="6.765")
    assert "model_lens" not in _rules(lint(ts))

def test_partial_gps_detected():
    ts = _ts(GPS__GPSLatitude=47.6)
    assert "partial_gps" in _rules(lint(ts))

def test_gps_residue_after_coordinate_removal_detected():
    ts = _ts(GPS__GPSAltitude=30.0)
    assert "partial_gps" in _rules(lint(ts))

def test_orphan_makernote_detected():
    ts = _ts(EXIF__Make="Google", Apple__SceneFlags=1)
    assert "orphan_makernote" in _rules(lint(ts))

def test_filename_mismatch_detected():
    ts = _ts(name="IMG_0942.HEIC", EXIF__Make="Canon")
    assert "filename_mismatch" in _rules(lint(ts))

def test_filename_match_produces_no_finding():
    ts = _ts(name="IMG_0942.HEIC", EXIF__Make="Apple")
    assert "filename_mismatch" not in _rules(lint(ts))

def test_round_timestamp_detected():
    ts = _ts(EXIF__DateTimeOriginal="2026:09:14 12:00:00", EXIF__Make="Apple")
    assert "round_timestamp" in _rules(lint(ts))

def test_time_ordering_violation_detected():
    ts = _ts(EXIF__DateTimeOriginal="2026:09:14 12:00:01",
             EXIF__ModifyDate="2020:01:01 00:00:00")
    assert "time_ordering" in _rules(lint(ts))

def test_serial_residue_detected():
    ts = _ts(EXIF__InternalSerialNumber="ABC123456")
    assert "serial_residue" in _rules(lint(ts))

def test_model_software_mismatch_detected():
    # iOS 9 never ran on an iPhone 15 Pro.
    ts = _ts(EXIF__Make="Apple", EXIF__Model="iPhone 15 Pro", EXIF__Software="9.3.5")
    assert "model_software" in _rules(lint(ts))

def test_dimension_coherence_detected():
    ts = _ts(EXIF__ExifImageWidth=4032, File__ImageWidth=1024)
    assert "dimension_coherence" in _rules(lint(ts))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_linter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/anonymizer/linter.py
"""Detect contradictions in a file's metadata.

A file whose metadata contradicts itself is more conspicuous than one that
was never edited. These rules look for the specific inconsistencies that a
careless edit leaves behind.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .model import TagSet

_VENDOR_GROUPS = {
    "Apple": "apple", "Canon": "canon", "Nikon": "nikon",
    "Sony": "sony", "Panasonic": "panasonic", "Olympus": "olympus",
    "Fujifilm": "fujifilm", "Pentax": "pentax",
}

# Earliest iOS version each model shipped with.
_MODEL_MIN_IOS = {
    "iPhone 15": 17, "iPhone 14": 16, "iPhone 13": 15,
    "iPhone 12": 14, "iPhone 11": 13, "iPhone X": 11, "iPhone 8": 11,
}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str  # "warning" | "note"
    message: str


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    text = str(value).split("+")[0].split("-0")[0].strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y:%m:%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def rule_partial_gps(ts: TagSet) -> list[Finding]:
    keys = {k for k in ts.keys() if k.startswith("GPS:")}
    if not keys:
        return []
    names = {k.split(":", 1)[1] for k in keys}
    out = []
    if "GPSLatitude" in names and "GPSLatitudeRef" not in names:
        out.append(Finding("partial_gps", "warning",
                           "GPSLatitude present without GPSLatitudeRef"))
    if "GPSLongitude" in names and "GPSLongitudeRef" not in names:
        out.append(Finding("partial_gps", "warning",
                           "GPSLongitude present without GPSLongitudeRef"))
    coords = {"GPSLatitude", "GPSLongitude"} & names
    residue = names - {"GPSLatitude", "GPSLongitude",
                       "GPSLatitudeRef", "GPSLongitudeRef"}
    if not coords and residue:
        out.append(Finding(
            "partial_gps", "warning",
            f"Coordinates removed but GPS residue remains: {', '.join(sorted(residue))}",
        ))
    return out


def rule_orphan_makernote(ts: TagSet) -> list[Finding]:
    make = ts.by_name("Make")
    if make is None:
        return []
    make_text = str(make.value).lower()
    out = []
    for group, vendor in _VENDOR_GROUPS.items():
        if any(k.startswith(f"{group}:") for k in ts.keys()) and vendor not in make_text:
            out.append(Finding(
                "orphan_makernote", "warning",
                f"{group} MakerNote present but Make says {make.value!r}",
            ))
    return out


def rule_filename_mismatch(ts: TagSet) -> list[Finding]:
    name = ts.path.name.upper()
    make = ts.by_name("Make")
    if make is None:
        return []
    make_text = str(make.value).lower()
    hints = [
        (r"^IMG_\d+\.(HEIC|JPG|PNG|MOV)$", "apple"),
        (r"^DSC_?\d+", "nikon"),
        (r"^IMG_\d+\.CR2$", "canon"),
        (r"^PXL_\d+", "google"),
    ]
    for pattern, vendor in hints:
        if re.match(pattern, name) and vendor not in make_text:
            return [Finding(
                "filename_mismatch", "note",
                f"Filename {ts.path.name!r} suggests {vendor} but Make says {make.value!r}",
            )]
    return []


def rule_round_timestamp(ts: TagSet) -> list[Finding]:
    tag = ts.by_name("DateTimeOriginal")
    if tag is None:
        return []
    if re.search(r"\b(00|12):00:00(\b|$)", str(tag.value)):
        has_subsec = ts.by_name("SubSecTimeOriginal") is not None
        if not has_subsec:
            return [Finding(
                "round_timestamp", "note",
                f"{tag.value!r} is suspiciously round and carries no subseconds",
            )]
    return []


def rule_time_ordering(ts: TagSet) -> list[Finding]:
    original = _parse_dt(getattr(ts.by_name("DateTimeOriginal"), "value", None))
    modified = _parse_dt(getattr(ts.by_name("ModifyDate"), "value", None))
    if original and modified and modified < original:
        return [Finding(
            "time_ordering", "warning",
            f"ModifyDate ({modified}) precedes DateTimeOriginal ({original})",
        )]
    return []


def rule_serial_residue(ts: TagSet) -> list[Finding]:
    out = []
    for tag in ts.tags.values():
        if "serial" in tag.name.lower() and tag.value not in (None, "", 0):
            out.append(Finding(
                "serial_residue", "warning",
                f"{tag.key} still carries {tag.display!r}",
            ))
    return out


def rule_model_software(ts: TagSet) -> list[Finding]:
    model = ts.by_name("Model")
    software = ts.by_name("Software")
    if model is None or software is None:
        return []
    match = re.match(r"^(\d+)", str(software.value).strip())
    if not match:
        return []
    ios_major = int(match.group(1))
    for prefix, minimum in _MODEL_MIN_IOS.items():
        if str(model.value).startswith(prefix) and ios_major < minimum:
            return [Finding(
                "model_software", "warning",
                f"{model.value} shipped with iOS {minimum}+, "
                f"but Software says {software.value!r}",
            )]
    return []


def rule_model_lens(ts: TagSet) -> list[Finding]:
    model = ts.by_name("Model")
    lens = ts.by_name("LensModel")
    if model is None or lens is None:
        return []
    lens_text = str(lens.value)
    model_text = str(model.value)
    if model_text.startswith("iPhone") and "iPhone" in lens_text:
        head = lens_text.split(" back")[0].split(" front")[0].strip()
        if head and head != model_text:
            return [Finding(
                "model_lens", "warning",
                f"LensModel names {head!r} but Model says {model_text!r}",
            )]
    return []


def rule_dimension_coherence(ts: TagSet) -> list[Finding]:
    pairs = (("ExifImageWidth", "ImageWidth"), ("ExifImageHeight", "ImageHeight"))
    out = []
    for exif_name, real_name in pairs:
        exif_tag = ts.get(f"EXIF:{exif_name}") or ts.by_name(exif_name)
        real_tag = ts.get(f"File:{real_name}")
        if exif_tag is None or real_tag is None:
            continue
        try:
            if int(exif_tag.value) != int(real_tag.value):
                out.append(Finding(
                    "dimension_coherence", "warning",
                    f"{exif_name} ({exif_tag.value}) disagrees with "
                    f"actual {real_name} ({real_tag.value})",
                ))
        except (TypeError, ValueError):
            continue
    return out


def rule_utc_math(ts: TagSet) -> list[Finding]:
    gps_dt = _parse_dt(getattr(ts.by_name("GPSDateTime"), "value", None))
    local = _parse_dt(getattr(ts.by_name("DateTimeOriginal"), "value", None))
    offset = ts.by_name("OffsetTimeOriginal")
    if not (gps_dt and local and offset):
        return []
    match = re.match(r"([+-])(\d{2}):(\d{2})", str(offset.value))
    if not match:
        return []
    sign = 1 if match.group(1) == "+" else -1
    delta_hours = sign * (int(match.group(2)) + int(match.group(3)) / 60)
    implied_utc = local.timestamp() - delta_hours * 3600
    if abs(implied_utc - gps_dt.timestamp()) > 300:
        return [Finding(
            "utc_math", "warning",
            f"GPSDateTime, DateTimeOriginal and OffsetTimeOriginal "
            f"({offset.value}) do not reconcile",
        )]
    return []


RULES = (
    rule_partial_gps,
    rule_orphan_makernote,
    rule_filename_mismatch,
    rule_round_timestamp,
    rule_time_ordering,
    rule_serial_residue,
    rule_model_software,
    rule_model_lens,
    rule_dimension_coherence,
    rule_utc_math,
)


def lint(tagset: TagSet) -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        try:
            findings.extend(rule(tagset))
        except Exception:
            # A rule must never break the pipeline.
            continue
    return findings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_linter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/linter.py tests/test_linter.py
git commit -m "feat: add metadata consistency linter"
```

---

### Task 10: Flask server

**Files:**
- Create: `src/anonymizer/server.py`
- Create: `src/anonymizer/__main__.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: everything above
- Produces: `create_app(engine=None) -> Flask`, `main() -> None`

**Routes:**

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/` | — | `web/index.html` |
| GET | `/static/<file>` | — | asset from `web/` |
| POST | `/api/upload` | multipart `file` | `{session, filename, container, categories, tags, findings}` |
| POST | `/api/preview` | `{session, preset, options, edits}` | `{tags, findings, diff}` |
| POST | `/api/apply` | `{session, preset, options, edits}` | `{ok, gates, download}` |
| GET | `/api/download/<session>` | — | the written file |
| GET | `/api/presets` | — | `{presets, profiles}` |

**Security:** loopback bind, random port, and a `Host` header allowlist so a
malicious page cannot reach the server through the operator's browser via DNS
rebinding.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server.py
import io, json
import pytest
from anonymizer.server import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()

def test_index_served(client):
    assert client.get("/").status_code == 200

def test_presets_listed(client):
    data = client.get("/api/presets").get_json()
    assert set(data["presets"]) == {"clean", "plausible", "reprofile", "manual"}
    assert "pixel-8" in data["profiles"]

def test_upload_requires_file(client):
    assert client.post("/api/upload", data={}).status_code == 400

def test_unknown_session_rejected(client):
    r = client.post("/api/preview", json={"session": "nope", "preset": "manual"})
    assert r.status_code == 404

def test_foreign_host_header_rejected(client):
    r = client.get("/", headers={"Host": "evil.example.com"})
    assert r.status_code == 403

def test_loopback_host_allowed(client):
    assert client.get("/", headers={"Host": "127.0.0.1:5000"}).status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'flask'` or `anonymizer.server`

Install Flask first: `python -m pip install flask pytest`

- [ ] **Step 3: Write the implementation**

Implement `create_app` with an in-memory `SESSIONS: dict[str, Session]` where
`Session` holds `dir: Path`, `source: Path`, `tagset: TagSet`, `output: Path | None`.
`before_request` enforces the Host allowlist (`127.0.0.1`, `localhost`, and
`testserver`, each with any port). Upload writes to a per-session temp dir via
`werkzeug.utils.secure_filename`, reads tags, and returns the categorised tag
list. Preview builds the plan, computes `tagset.with_plan(plan)`, lints the
pending state, and returns a field-level diff. Apply runs `apply_plan` and
returns gate results; on failure it returns `ok: false` with no download link.

`__main__.py` picks a free port with `socket.socket().bind(("127.0.0.1", 0))`,
opens the browser via `webbrowser.open`, and runs the app.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/server.py src/anonymizer/__main__.py tests/test_server.py
git commit -m "feat: add Flask server with loopback host allowlist"
```

---

### Task 11: Web UI

**Files:**
- Create: `web/index.html`, `web/app.js`, `web/style.css`

**Interfaces:**
- Consumes: the routes from Task 10

Single page, no build step. Drop zone → category-grouped tag table with risk
badges → inline editing → preset selector → linter panel → gate results →
download button. Dark and light via `prefers-color-scheme`.

- [ ] **Step 1: Build the page**

Structure: a header with the file name and container type; a control bar with
the preset `<select>`, profile `<select>` (shown only for `reprofile`), and a
time-shift input; a two-column body with the tag table on the left and the
linter panel on the right; a footer with the Apply button and gate results.

Tag rows render `key`, `display`, a category badge, an edit input, and a delete
toggle. Edited and deleted rows are visually distinct from untouched ones.

- [ ] **Step 2: Verify in a real browser with Playwright**

Start the server, then drive it: navigate, upload the sample HEIC, confirm the
tag table populates, switch presets, confirm the linter panel updates, apply,
and confirm all four gates report pass and the download link appears. Capture
screenshots at each step.

- [ ] **Step 3: Commit**

```bash
git add web/
git commit -m "feat: add single-page metadata editor UI"
```

---

### Task 12: End-to-end verification

**Files:**
- Create: `tests/test_end_to_end.py`
- Create: `README.md`

**Interfaces:**
- Consumes: the whole pipeline

- [ ] **Step 1: Write the end-to-end test**

```python
# tests/test_end_to_end.py
import pytest
from pathlib import Path
from anonymizer.engine import ExifToolEngine
from anonymizer.inspect import read_tags
from anonymizer.presets import build_plan
from anonymizer.apply import apply_plan
from anonymizer.payload import payload_digest
from anonymizer.linter import lint
from scripts.fetch_exiftool import find_exiftool

SAMPLE = Path(__file__).resolve().parent.parent / "IMG_0942.HEIC"

pytestmark = pytest.mark.skipif(
    find_exiftool() is None or not SAMPLE.exists(),
    reason="needs vendored exiftool and the sample HEIC",
)

@pytest.fixture(scope="module")
def engine():
    with ExifToolEngine(find_exiftool()) as e:
        yield e

def test_real_heic_round_trip_passes_all_gates(engine, tmp_path):
    ts = read_tags(engine, SAMPLE)
    plan = build_plan(ts, "plausible", {})
    out = tmp_path / "clean.HEIC"
    report = apply_plan(engine, SAMPLE, out, plan)
    assert report.ok, [f"{g.name}: {g.detail}" for g in report.failures]

def test_real_heic_payload_survives(engine, tmp_path):
    out = tmp_path / "clean.HEIC"
    ts = read_tags(engine, SAMPLE)
    apply_plan(engine, SAMPLE, out, build_plan(ts, "plausible", {}))
    assert payload_digest(out) == payload_digest(SAMPLE)

def test_real_heic_gps_is_gone(engine, tmp_path):
    out = tmp_path / "clean.HEIC"
    ts = read_tags(engine, SAMPLE)
    apply_plan(engine, SAMPLE, out, build_plan(ts, "plausible", {}))
    after = read_tags(engine, out)
    assert not [k for k in after.keys() if k.startswith("GPS:")]

def test_real_heic_still_opens(engine, tmp_path):
    out = tmp_path / "clean.HEIC"
    ts = read_tags(engine, SAMPLE)
    apply_plan(engine, SAMPLE, out, build_plan(ts, "plausible", {}))
    after = read_tags(engine, out)
    assert after.get("File:FileType").value == "HEIC"
    assert int(after.get("File:ImageWidth").value) > 0

def test_cleaned_file_lints_clean(engine, tmp_path):
    out = tmp_path / "clean.HEIC"
    ts = read_tags(engine, SAMPLE)
    apply_plan(engine, SAMPLE, out, build_plan(ts, "plausible", {}))
    warnings = [f for f in lint(read_tags(engine, out)) if f.severity == "warning"]
    assert warnings == [], [f.message for f in warnings]
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -v`
Expected: all PASS

- [ ] **Step 3: Write the README**

Cover: what it does, first-run setup (`python scripts/fetch_exiftool.py`),
how to run (`python -m anonymizer`), the four gates and what each proves, the
preset table, and the limits section from the spec verbatim.

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py README.md
git commit -m "test: add end-to-end verification against the real HEIC"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: architecture → the file
structure table; `engine.py` → Task 2; the four gates → Task 7; `payload.py` →
Task 6; sensitivity classification → Task 5; presets → Task 8; linter → Task 9;
interface → Tasks 10-11; testing → Task 12. The spec's "limits" section is
carried into the README in Task 12 Step 3.

**Placeholders.** None. Task 10 Step 3 and Task 11 Step 1 describe structure
rather than showing full code, which is deliberate: the route contracts are
pinned by the table and the tests above them, and the UI is a layout rather
than an algorithm.

**Type consistency.** `EditPlan.to_args()`, `EditPlan.deletions()`,
`TagSet.with_plan()`, `TagSet.by_name()`, `classify()`, `build_plan()`,
`lint()`, `apply_plan()` and `payload_digest()` keep the same signatures across
every task that references them. Task 8 adds `EditPlan.raw_args` and says so
explicitly, including the requirement to update `model.py` and its test in the
same task.
