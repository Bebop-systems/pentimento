# Changelog

All notable changes to this project are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-09-18

First public release. Windows is supported; macOS is written but unverified.

### Added

- **Four-gate verification.** Every write is checked for structural
  integrity, rendering equivalence, a byte-identical image bitstream, and
  that removals actually happened. A failed gate discards the output.
- **Plain-English explanations** for roughly sixty metadata fields, each
  saying what it is and what an inspector learns from it, with category
  fallbacks so no field renders blank.
- **Risk overview** grouping fields into Location, Device, Content, Time,
  Software, Embedded and Technical, each with a count and a one-line summary.
- **Four presets** — Manual, Plausible, Reprofile and Clean.
- **24 camera identities**, eleven credible and thirteen deliberately not,
  each internally consistent and carrying its camera's real filename
  convention plus a note on which details are true.
- **Consistency checker** with ten rules covering lens/body mismatches,
  impossible OS versions, partial GPS, orphaned MakerNotes, UTC arithmetic,
  round timestamps, dimension disagreements and filename contradictions.
- **Configurable output naming** with `{stem} {ext} {preset} {profile}
  {date} {time} {datetime} {n}` tokens, format specs, and a choice of
  overwrite, number or timestamp on collision.
- **Concealed values** that start blurred and reveal on demand, implemented
  as real buttons so they work by keyboard and with a screen reader.
- **Desktop application** for Windows and macOS, bundling ExifTool, opening
  a native window through the OS webview with a browser fallback.
- Built on the GeoDzk design system, dark by default, with light and two
  high-contrast themes.

### Notes

- ExifTool is downloaded at setup time rather than committed, and bundled
  into packaged releases. See [NOTICE.md](NOTICE.md).
- 350 tests, run with warnings as errors.
