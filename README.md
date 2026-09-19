<div align="center">

# Pentimento

**The earlier picture, still showing through.**

See everything your photos are telling people — then decide what they keep saying.

[![tests](https://github.com/Bebop-systems/pentimento/actions/workflows/test.yml/badge.svg)](https://github.com/Bebop-systems/pentimento/actions/workflows/test.yml)
[![release](https://img.shields.io/github/v/release/Bebop-systems/pentimento?sort=semver)](https://github.com/Bebop-systems/pentimento/releases/latest)
[![licence](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)

</div>

---

In painting, a *pentimento* is the earlier image showing through the finished
one — a hand moved, a figure painted out, still faintly there. Photographs do
the same thing. Under the picture you meant to share sits the street you took
it on, the phone you took it with, the names of people your software
recognised, and often a thumbnail of the frame from *before* you cropped it.

Pentimento shows you all of it, in plain English, and lets you change or
remove any of it — with proof that the image itself never changed.

## Install

### One machine

Download **`Pentimento-0.1.0-windows-setup.exe`** from
[Releases](https://github.com/Bebop-systems/pentimento/releases/latest) and run
it. Pentimento appears in the Start menu. It installs per user, so there is no
administrator prompt, and it uninstalls from Add or Remove Programs.

Prefer portable? The `-portable.zip` unzips to a folder you can run from
anywhere, including a USB stick.

Nothing else to install: no Python, no ExifTool, no account. Windows warns that
the app is unsigned the first time — **More info → Run anyway** — because
signing certificates cost money and this is version 0.1.0.

### A fleet

Pentimento is built to be deployed, not only downloaded.
**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** covers Intune end to end: the
`.intunewin` packaging command, every field in the portal, the app logo,
detection rules read back from a real install, per-user versus machine-wide,
and the two things that genuinely bite — Attack Surface Reduction rules
blocking unsigned binaries, and Known Folder Move syncing cleaned photos into
OneDrive.

The short version, for an administrator skimming:

| | |
|---|---|
| App type | **Windows app (Win32)** — Intune's line-of-business type does not accept an `.exe` |
| Install | `Pentimento-0.1.0-windows-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL /CURRENTUSER` |
| Detection | `HKCU` uninstall key `{7B2F5A64-9C3E-4D18-9A6F-2E5C1D0B7A43}_is1`, `DisplayVersion` at or above `0.1.0` |
| Network | None. No update check, no telemetry. |
| Elevation | None required. |
| Logo | `desktop/icon-intune-256.png` |

> **macOS:** the build is written and produces a proper `.app`, but it has not
> yet been run on a Mac. See [macOS](#macos) below.

## What it looks like

```
┌─ Pentimento ──────────────────────────── Load another · Dark ─┐
│ LOCAL ONLY · no network, no account    IMG_0942.HEIC · 1.9 MB │
├───────────────────────────────────────────────────────────────┤
│ WHAT THIS FILE REVEALS                              206 fields│
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ 17       │ │  1       │ │ 59       │ │ 14       │          │
│  │ LOCATION │ │ DEVICE   │ │ CONTENT  │ │ TIME     │          │
│  │ Where you│ │ Which    │ │ What's in│ │ When you │          │
│  │ were     │ │ camera,  │ │ it, incl.│ │ were     │          │
│  │ standing │ │ and whose│ │ names    │ │ there    │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
├───────────────────────────────────────────────────────────────┤
│ GPSLatitude  GPS                              [Edit] [Remove] │
│ ░░░░░░░░░░░░░░░░░  ← click to reveal                          │
│ The exact latitude where the shutter fired. REVEALS: With      │
│ longitude this places you within a few metres. On a map it     │
│ names the building, which is often a home or a school.         │
└───────────────────────────────────────────────────────────────┘
```

### Why there is no single portable .exe

A self-extracting build would unpack **737 files and 69 MB into `%TEMP%` on
every launch** and then run an unsigned binary from there — measured, not
guessed. Self-extraction to temp, execution from temp, and the duplicated
process image it also creates are three behaviours endpoint security scores
heavily, for good reason.

The installer does that unpacking once, at install, into a stable folder. It
costs half a second of startup to avoid, and buys a great deal of plausibility
on a managed machine.

## How it works

Your original is **never modified**. Every write goes to a copy, and that copy
has to pass four checks before you are allowed to have it:

| Gate | What it proves |
|---|---|
| **Structural** | The container still parses and reports the same type |
| **Rendering** | Dimensions, orientation and colour handling are unchanged |
| **Payload** | The image bitstream is byte-for-byte identical |
| **Regression** | Every field you removed is genuinely gone |

If any gate fails, the output is deleted rather than handed over. A
half-scrubbed file is more dangerous than no file, because you would believe it
was clean.

The payload gate is the one that earns the word *compatible*. For HEIC it
locates the picture items through the `iloc` table and hashes their extents,
because HEIC stores Exif and XMP **inside `mdat`**, right next to the coded
image tiles — hashing `mdat` wholesale would report every metadata edit as a
pixel change.

## Presets

| Preset | What it does |
|---|---|
| **Manual** | Nothing automatic. You decide every field. |
| **Plausible** | Keeps a coherent camera identity. Drops location, serials, faces, captions and embedded thumbnails, the way a phone with location services off would present. |
| **Reprofile** | Everything Plausible does, then adopts a different, internally consistent camera identity. |
| **Clean** | Removes every field not needed to render the image. Maximally private, and visibly scrubbed. |

## 24 camera identities

**Eleven credible** — iPhone 15 Pro and 13, Pixel 8, Galaxy S23, Canon EOS R5,
Nikon Z 6II, Sony a7 IV, Fujifilm X100V, GoPro HERO12, DJI Mavic 3, and an
Epson flatbed scan.

**Thirteen not** — a Game Boy Camera, a 1949 toaster, a dream you had once, a
potato, an oatmeal-tin pinhole, an 1839 daguerreotype, the first webcam, a
trail cam, the Perseverance rover, Voyager 1, an Etch A Sketch, a camera
obscura, and Hubble.

The novelty ones are absurd about *which* camera they claim and rigorous about
everything else — the numeric fields stay real numbers, so the output still
passes all four gates and still opens everywhere. Most are more real than they
sound, and each says which part is true:

> **Game Boy Camera** — All of this is real. It used a Mitsubishi M64282FP
> sensor: 128×128 pixels, four shades of grey, f/2.0, fixed focus. It held the
> Guinness record for smallest digital camera for a decade.

> **Voyager 1** — A 1500mm f/8.5 vidicon tube, not a sensor, running on about
> 70 kilobytes of memory. It took the Pale Blue Dot and is now the most distant
> camera from Earth.

Each identity also brings its camera's own filename convention, which is the
point rather than decoration: `IMG_0942` announces Apple as loudly as the Make
tag does, so a Pixel file keeping that name contradicts itself — and the
consistency checker says so.

## The consistency checker

A file whose metadata contradicts itself is more conspicuous than one that was
never edited. It checks the pending state and warns; it never blocks.

It catches a lens that never shipped with the claimed body, an OS version that
predates the model, GPS coordinates left without their reference fields, a
vendor MakerNote surviving next to a different `Make`, timestamps that do not
reconcile against the GPS clock, suspiciously round times with no subseconds,
and a filename naming a different manufacturer than the metadata does.

## Worth knowing about thumbnails

Embedded thumbnails are frequently the original, pre-edit frame. Crop or redact
a photo in many editors and the thumbnail still shows what you removed. It is
invisible in any viewer that presents metadata as a list of fields, which is
most of them.

This is the pentimento the project is named for. Every preset except Manual
removes them.

## Filenames

The default output name is `{stem}_clean{ext}` and it **overwrites**, so
repeating a file does not leave a pile of numbered copies. The Output panel
controls this:

| Token | Becomes |
|---|---|
| `{stem}` `{ext}` | the original name and extension |
| `{preset}` `{profile}` | what you applied |
| `{date}` `{time}` `{datetime}` | when you wrote it |
| `{n}` | the lowest sequence number not already used |

Format specs work, so `{n:03}` gives `001`. **If it already exists** offers
Overwrite, Add a number, or Add the time — and a pattern containing `{n}` picks
the next free number, so it never overwrites and that choice disables itself.

## Privacy

No network calls after first-run setup. No account, no telemetry, no upload.
Working files live in a temporary folder deleted when the app closes, and
cleaned copies are written to `~/Pictures/Pentimento`.

Identifying values start blurred and reveal on click, so your own coordinates
are not on screen by accident during a screen share. Because blur alone would
protect a sighted person and nobody else, each concealed value is a real button
— keyboard reachable, carrying its state in `aria-expanded`, and hidden from
assistive technology until deliberately revealed.

## Limits

Pentimento works at the metadata layer. It does not change pixel-level traces —
sensor noise patterns, JPEG quantization tables, HEIC encoder and tile-layout
fingerprints — which still identify a capture device under forensic analysis.

That is by design: the payload gate **guarantees** those traces survive.
Preserving the image exactly and altering provenance claims are opposing goals,
and this tool chooses preservation.

So it is effective against casual inspection, automated metadata scrapers, and
the properties panel of a photo viewer. It is not effective against a
laboratory, and a plausible timestamp is suitable for privacy rather than for
any situation where provenance is relied upon.

## Formats

Whatever ExifTool can write: HEIC, JPEG, PNG, TIFF, WebP, DNG and other raw
formats, plus MOV and MP4 — phone videos carry GPS too. Output always keeps the
input's format and extension.

The payload gate understands ISO-BMFF, JPEG, PNG and TIFF. For anything else it
reports *payload unverified* rather than claiming a guarantee it cannot make.

## Running from source

```bash
git clone https://github.com/Bebop-systems/pentimento
cd pentimento
python -m pip install -r requirements.txt
python scripts/fetch_exiftool.py     # one time, ~35 MB
python run.py                        # browser
python run.py --window               # native window
```

Python 3.11 or newer.

## Building the app

```bash
python desktop/build.py --check      # is this machine ready
python desktop/build.py --zip        # build, then archive it
```

No browser is bundled and none is needed: the window is drawn by Edge WebView2
on Windows and WKWebView on macOS, both supplied by the operating system. Full
detail in [docs/PACKAGING.md](docs/PACKAGING.md).

## macOS

The spec produces a `.app` with a generated `.icns`, written directly so the
build does not need `iconutil` and therefore does not need a Mac. It has not
been run on one.

The specific risk is Perl. Windows gets the ExifTool standalone build with its
own Perl; everything else gets the plain distribution, which relies on the
system Perl that macOS has been deprecating for years. If `/usr/bin/perl` ever
goes, the fix is bundling a Perl alongside ExifTool.

Reports welcome — that is the fastest way to get macOS promoted from *written*
to *supported*.

## Tests

```bash
python -m pytest -q
```

350 tests. The suite runs with warnings as errors, which is how two real
file-handle leaks were caught. Tests needing a real HEIC skip when none is
present; drop any `.heic` in the repository root to enable them.

## Licence

MIT — see [LICENSE](LICENSE). ExifTool is downloaded at setup time and carries
its own licence; see [NOTICE.md](NOTICE.md).
