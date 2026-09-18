# Photo Metadata Anonymizer — Design

**Date:** 2026-09-18
**Status:** Approved

## Purpose

A local, single-user tool for inspecting and rewriting the metadata of a photo
or video before sharing it. The operator drops a file in, sees every tag the
file carries, edits or removes what they choose, and downloads a new file whose
image data is provably unchanged.

Two properties distinguish it from `exiftool -all=`:

1. **Coherence.** A file stripped bare is itself a signal. The tool can leave a
   self-consistent camera identity in place while removing what identifies the
   operator, and it checks that identity for internal contradictions before the
   file is written.
2. **Verified compatibility.** Every write is checked against the input for
   structural, rendering, and byte-level image equivalence. The tool refuses to
   hand over a file that fails.

## Constraints

- Runs entirely on the local machine. No network calls after first-run setup.
- The input file is never modified.
- Output keeps the input's container format and extension.
- Image bitstream must survive byte-identical.

## Architecture

```
anonymizer/
├─ vendor/exiftool/            ExifTool 13.59 (fetched, gitignored)
├─ scripts/fetch_exiftool.py   first-run setup, checksum-pinned
├─ src/anonymizer/
│  ├─ engine.py                persistent ExifTool process, JSON in/out
│  ├─ inspect.py               read → TagSet
│  ├─ sensitivity.py           tag → risk category
│  ├─ plan.py                  EditPlan: set/delete ops, format-agnostic
│  ├─ presets.py               preset → EditPlan
│  ├─ profiles.py              coherent camera identities
│  ├─ linter.py                consistency rules
│  ├─ apply.py                 write + four-gate verification
│  ├─ payload.py               container-aware image-bitstream extraction
│  └─ server.py                Flask, 127.0.0.1, random port
├─ web/                        index.html / app.js / style.css — no build step
├─ tests/
└─ fixtures/                   generated at test time
```

Data flows one way: `inspect → TagSet → (preset | manual edits) → EditPlan →
apply → verified output`. `TagSet` and `EditPlan` are plain dataclasses with no
ExifTool knowledge, so presets, the linter, and the GUI are all testable without
touching a real file or spawning a subprocess.

### engine.py

Wraps one long-lived `exiftool -stay_open True -@ -` process. Perl startup is
roughly 200 ms; a persistent process makes per-request cost negligible.

Reads issue two passes — `-j -G1 -a -u -struct` with and without `-n` — merged
so each tag carries both a machine value (`47.62089`) and a display value
(`47 deg 37' 15.20" N`).

Writes are marshalled through an ExifTool **args file**, never interpolated into
a shell string. Tag values originate in untrusted files; a value containing
`-delete_original!` or an embedded newline must be data, not an instruction.
Args-file mode gives that guarantee structurally.

The engine is the only module permitted to spawn a process.

### The four gates

`apply.py` writes to a temp copy and then verifies before the result is offered:

| Gate | Check | Failure meaning |
|---|---|---|
| **G1 structural** | Output re-reads without ExifTool `Error`; `FileType` and `MIMEType` match input | Container was damaged |
| **G2 rendering** | `ImageWidth`, `ImageHeight`, `Orientation`, `Rotation`, ICC profile presence, `ColorSpace` match input | File would render differently |
| **G3 payload** | Image bitstream byte-identical to input | Pixel data was touched |
| **G4 regression** | Tags the plan deleted are absent from the output | The scrub silently failed |

Any gate failing aborts the operation, preserves the input, and surfaces the
reason. A partially-scrubbed file is worse than no file, because the operator
believes it is clean.

### payload.py

G3 needs the image bitstream isolated from the metadata that legitimately
changed. Per container:

- **ISO-BMFF** (HEIC, MOV, MP4) — concatenated `mdat` box contents
- **JPEG** — entropy-coded data from each `SOS` marker to the next marker
- **PNG** — concatenated `IDAT` chunk data
- **TIFF** — strip/tile data at `StripOffsets`/`TileOffsets`

Unknown containers degrade to G1+G2+G4 with an explicit "payload unverified"
warning rather than a silent pass.

## Sensitivity classification

Six independently-toggleable categories:

| Category | Representative tags |
|---|---|
| **Location** | `GPS:*`, `XMP:Location`, IPTC location, QuickTime `GPSCoordinates`, Apple MakerNote location hints |
| **Device identity** | `SerialNumber`, `BodySerialNumber`, `LensSerialNumber`, `InternalSerialNumber`, `OwnerName`, `Artist`, `HostComputer` |
| **Time** | `DateTimeOriginal`, `CreateDate`, `ModifyDate`, `OffsetTime*`, `SubSecTime*`, `GPSDateStamp`, `GPSTimeStamp` |
| **Content-derived** | Apple MakerNote scene/face data, `XMP-mwg-rs` face regions, IPTC keywords and captions |
| **Software trail** | `Software`, `ProcessingSoftware`, XMP `History`, `DocumentID`, `InstanceID`, `OriginalDocumentID` |
| **Embedded images** | `ThumbnailImage`, `PreviewImage`, `OtherImage` |

Embedded images warrant emphasis. A thumbnail is frequently the original
pre-edit frame: crop or redact a photo in many editors and the thumbnail still
shows what was removed. The leak is invisible in any viewer that presents
metadata as a tag list, which is most of them.

Classification is data, not code — a table in `sensitivity.py` keyed by
normalized tag name with glob support, so adding a tag is a one-line change.

## Presets

| Preset | Behaviour |
|---|---|
| **Clean** | Remove every identifying category. Keep only rendering-critical tags (`Orientation`, `ColorSpace`, ICC, dimensions). Honest, visibly scrubbed. |
| **Plausible** | Keep a coherent camera identity. Drop GPS entirely, as a device with location services off would present. Remove serials, face regions, embedded thumbnails. Keep timestamps internally consistent, optionally jittered as a unit. |
| **Reprofile** | Adopt a different internally-consistent identity from `profiles.py`, rewriting `Make`, `Model`, `LensModel`, `Software`, and `ExifVersion` together. |
| **Manual** | No automatic changes. |

A preset is a pure function `TagSet -> EditPlan`. It performs no I/O, which
makes every preset testable against a synthetic `TagSet`.

## Consistency linter

Runs against the *pending* state — the `TagSet` as it would be after the
`EditPlan` applies — and emits warnings. It never blocks a write; the operator
decides.

| Rule | Detects |
|---|---|
| `model_lens` | `LensModel`/`FocalLength` inconsistent with the claimed body's optics |
| `model_software` | OS version that does not exist, or predates the claimed model |
| `utc_math` | `GPSDateTime`, `DateTimeOriginal`, and `OffsetTime` that do not reconcile |
| `partial_gps` | Latitude without `GPSLatitudeRef`; `GPSAltitude`/`GPSDateStamp` surviving a coordinate removal |
| `orphan_makernote` | Vendor MakerNote present while `Make` claims another vendor |
| `filename_mismatch` | `IMG_*.HEIC` implying Apple while metadata claims otherwise |
| `round_timestamp` | `12:00:00.00` on a device that always records subseconds |
| `dimension_coherence` | `ExifImageWidth`/`Height` disagreeing with actual pixel dimensions |
| `serial_residue` | Any serial-shaped value surviving a device-identity scrub |
| `time_ordering` | `ModifyDate` earlier than `DateTimeOriginal` |

Each rule is an independent function returning zero or more `Finding`s, so rules
are added without touching a dispatcher.

## Interface

Flask bound to `127.0.0.1` on a random port, browser opened automatically.
Session files live in a temp directory removed at shutdown.

Single page: drop zone → tag table grouped by category with risk badges →
inline editing → preset selector → linter panel → before/after diff → download.

No build step. Vanilla JS and hand-written CSS, so the page is auditable by
reading it.

The server is single-user and local. It binds the loopback interface only, and
rejects requests carrying a `Host` header it did not issue, which prevents DNS
rebinding from reaching it through a browser the operator has open.

## Testing

TDD throughout. Fixtures are generated at test time by ExifTool itself —
synthetic JPEG, PNG, TIFF, and MOV files with known tag values — so the suite is
self-contained and commits no binaries.

The real `IMG_0942.HEIC` serves as a local-only real-world HEIC case. Tests
depending on it skip when absent. It is never committed; it carries genuine GPS
coordinates.

Layer coverage:

- `engine` — args-file escaping, `stay_open` lifecycle, crash recovery
- `sensitivity` — classification table, glob matching
- `presets` — `TagSet -> EditPlan` against synthetic inputs, no I/O
- `linter` — each rule in isolation, positive and negative cases
- `payload` — bitstream extraction per container
- `apply` — all four gates, including deliberately-induced failures
- `server` — route contracts against a mock engine
- end-to-end — real files through the full pipeline, verifying gates pass

## Out of scope

Batch mode, CLI, user accounts, cloud sync, pixel editing, undo history beyond
the untouched original.

## Limits

The tool operates at the metadata layer. It does not alter pixel-level traces —
sensor noise patterns, JPEG quantization tables, HEIC encoder and tile-layout
fingerprints — which continue to identify a capture device under forensic
analysis. By design, G3 guarantees those traces survive: preserving the image
exactly and altering provenance claims are opposing goals, and this tool chooses
preservation.

It is therefore effective against casual inspection, automated metadata
scrapers, and the properties panel of a photo viewer. It is not effective
against a laboratory, and a plausible timestamp is suitable for privacy rather
than for any context where provenance is relied upon.
