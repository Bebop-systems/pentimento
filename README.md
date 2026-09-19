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

## Where your cleaned file goes

Every verified copy is written to `output/` next to this README, named after
the original with `_clean` appended, and the full path is shown on screen
with a **Copy path** button. Nothing is ever overwritten: a second run of
the same file becomes `_clean_2`.

A browser download is offered too, but the file on disk is the reliable
one. Browser downloads can land somewhere you will not find, or be
intercepted by a security policy, which is exactly what happened during
testing.

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

## Camera identities

**Reprofile** adopts a different camera identity, and the picker is grouped
into two kinds.

**Plausible** — iPhone 15 Pro, iPhone 13, Pixel 8, Galaxy S23. Every field
agrees with every other, so the file reads as an ordinary photo.

**Novelty** — Game Boy Camera, a 1949 toaster, a dream you had once, a
potato, an oatmeal-tin pinhole, and the Hubble Space Telescope. These are
absurd about *which* camera they claim and rigorous about everything else:
the numeric fields stay real numbers, so the output still passes all four
gates and still opens everywhere.

Several are more real than they sound. The Game Boy Camera genuinely used a
Mitsubishi M64282FP sensor at 128x128 and f/2.0. A pinhole genuinely works
out to about f/180. Hubble genuinely is 57.6 metres at f/24. Each one
explains itself under the picker.

The consistency panel *will* flag a novelty identity, and that is correct:
claiming a Game Boy took your `IMG_0942.HEIC` is meant to be obviously
untrue. The note says so, so a warning does not read as a bug.

## Doing another file

Three ways, whichever is nearest:

- **Load another** in the header, at any time
- **Clean another file** in the verification panel, once a write finishes
- **Drop a file anywhere on the window** — the whole page is a drop target
  once the start panel is gone

Picking the same file twice works too, which needs saying because it is a
common bug: the input is cleared after each pick so the browser still fires
a change event.

## Reading the metadata

Every field is shown with two sentences in plain English: what it is, and
what someone inspecting your file learns from it. A tag list is only useful
if you know what the tags mean, and almost nobody does.

Fields are grouped into cards - Location, Device, Content, Time, Software,
Embedded, Technical - each with a count and a one-line summary. Clicking a
card shows just those fields, so you are never scrolling one long
undifferentiated list.

Values in the identifying categories start blurred and reveal on click, or
all at once with **Reveal values**. Your own coordinates should not be on
screen by accident during a screen share.

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

## Appearance

The interface is built on the **GeoDzk** design system, using its tokens,
panels, trust chips, engraved surfaces and sealed-value pattern. Dark is the
default; the control in the header cycles dark, light, and both
high-contrast themes, and the choice is remembered per browser.

`web/geodzk.css` is a verbatim copy of the system's stylesheet and should be
replaced rather than edited. Everything specific to this app lives in
`web/app.css` and only ever references the system's tokens, so all four
themes keep working.

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
