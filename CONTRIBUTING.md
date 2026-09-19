# Contributing

## Getting set up

```bash
python -m pip install -r requirements.txt
python scripts/fetch_exiftool.py
python -m pytest -q
```

Tests needing a real HEIC skip when none is present. Drop any `.heic` in the
repository root to enable them — it is gitignored, because sample photos carry
real GPS coordinates and device serials that do not belong in git history.

## What this project cares about

**Real files over unit tests.** Every bug worth fixing here was found by
running an actual photograph through the pipeline, not by mocking. If you
change how writing works, verify it against a real file.

**The gates are the product.** Nothing may weaken structural, rendering,
payload or regression verification. If a gate fails, the answer is to
understand why, never to relax the check.

**Camera identities must be internally consistent.** A body paired with a
lens it never shipped with is exactly the contradiction the checker hunts.
Numeric fields stay real numbers or ExifTool cannot write them.

**Novelty identities are absurd about *which* camera, never about
consistency.** The comedy lives in the text fields; the optics stay
arithmetic. If you can state which part is genuinely true, put it in the note.

## Adding a camera identity

Add a `CameraProfile` to `src/pentimento/profiles.py`. The test suite will
check it end to end against a real file and verify any f-number quoted in the
lens description matches the profile's own.

## Style

Follow the surrounding code. Comments explain *why*, especially where
something non-obvious was learned the hard way — several in this codebase
record bugs that cost real time, and they are there so the next person does
not repeat them.
