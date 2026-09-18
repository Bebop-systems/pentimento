# Metadata Editor

A local tool for inspecting and rewriting the metadata of a photo or video
before you share it. Drop a file in, see every tag it carries, change or
remove whatever you like, and download a new file whose image data is
provably unchanged.

Nothing leaves your machine. There is no account, no upload, and no network
call after first-run setup.

## Setup

```bash
python scripts/fetch_exiftool.py     # one time: downloads ExifTool 13.59
python -m pip install flask
```

## Run

```bash
python run.py                        # picks a free port, opens a browser
python run.py 8731                   # or pick the port yourself
python run.py --no-browser
```

## What it does

Your original file is never modified. Every write goes to a copy, and that
copy has to pass four checks before you are offered a download:

| Gate | What it proves |
|---|---|
| **Structural** | The container still parses and reports the same type. |
| **Rendering** | Dimensions, orientation and colour handling are unchanged. |
| **Payload** | The image bitstream is byte-for-byte identical. |
| **Regression** | Every tag you removed is genuinely gone. |

If any gate fails the output is deleted rather than handed to you. A
half-scrubbed file is more dangerous than no file, because you would
believe it was clean.

The payload gate is the one that earns the word "compatible". For HEIC it
locates the picture items through the `iloc` table and hashes their
extents, because HEIC stores Exif and XMP *inside* `mdat` next to the coded
image tiles — hashing `mdat` wholesale would report every metadata edit as
a pixel change.

## Presets

| Preset | What it does |
|---|---|
| **Manual** | Nothing automatic. You decide every field. |
| **Plausible** | Keeps a coherent camera identity. Drops location, serials, faces, captions and embedded thumbnails, the way a phone with location services off would present. |
| **Reprofile** | Everything Plausible does, then adopts a different, internally consistent camera identity. |
| **Clean** | Removes every tag not needed to render the image. Maximally private, and visibly scrubbed. |

## The consistency linter

A file whose metadata contradicts itself is more conspicuous than one that
was never edited. The linter checks the pending state and warns; it never
blocks.

It catches a lens that never shipped with the claimed body, an OS version
that predates the model, GPS coordinates left without their reference
fields, a vendor MakerNote surviving next to a different `Make`, timestamps
that do not reconcile against the GPS clock, suspiciously round times with
no subseconds, and a filename that names a different manufacturer than the
metadata does.

That last one is easy to overlook: reprofile `IMG_0942.HEIC` to a Pixel 8
and the filename still says Apple.

## Worth knowing about thumbnails

Embedded thumbnails are frequently the original, pre-edit frame. Crop or
redact a photo in many editors and the thumbnail still shows what you
removed. It is invisible in any viewer that presents metadata as a list of
tags, which is most of them. Every preset except Manual removes them.

## Formats

Whatever ExifTool can write: HEIC, JPEG, PNG, TIFF, WebP, DNG and other raw
formats, plus MOV and MP4. Phone videos carry GPS too. Output always keeps
the input's format and extension.

The payload gate understands ISO-BMFF, JPEG, PNG and TIFF. For anything
else it reports "payload unverified" rather than claiming a guarantee it
cannot make.

## Tests

```bash
python -m pytest -q
```

The suite runs with warnings as errors, which is how two real file-handle
leaks were caught. Tests needing the sample HEIC skip if it is absent.

## Limits

This works at the metadata layer. It does not change pixel-level traces —
sensor noise patterns, JPEG quantization tables, HEIC encoder and
tile-layout fingerprints — which still identify a capture device under
forensic analysis. That is by design: the payload gate guarantees those
traces survive, because preserving the image exactly and altering
provenance claims are opposing goals, and this tool chooses preservation.

So it is effective against casual inspection, automated metadata scrapers,
and the properties panel of a photo viewer. It is not effective against a
laboratory, and a plausible timestamp is suitable for privacy rather than
for any situation where provenance is being relied upon.
