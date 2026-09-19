# Changelog

All notable changes to this project are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] — 2026-09-19

Complete uninstall, a theme picker, and a smaller bundle.

### Added

- **E-ink theme** from the GeoDzk design system, and a proper selector in
  place of the cycling toggle — five themes is four wrong answers away if
  you have to cycle. Where this app used colour as the only signal, e-ink
  substitutes a shape: the pass and fail gate marks become a disc and a
  rotated square, the category swatches give way to their labels, and the
  concealed-value blur becomes a solid block, because a panel renders a
  blur as a smear.

### Fixed

- **Uninstall now removes everything.** It deleted every installed file
  but left the empty directory tree, which also stopped it removing the
  uninstaller and the folder — so a later install moved into the shell.
  Scoped to `{app}`, so removing one side-by-side copy leaves the other
  untouched.

### Changed

- The bundle is **29% smaller**: 74.5 MB to 53 MB installed, 24 MB to
  18 MB for the installer. 14 MB of cryptography and OpenSSL the
  application never imports, 7.6 MB of ExifTool payloads it never asks
  for, and 4.6 MB of Perl DLLs duplicated beside the executable.

## [0.1.2] — 2026-09-19

Side-by-side installs, and telling two copies apart.

### Added

- The installer detects an existing installation and says so, offering to
  upgrade it (the default and the recommendation) or install alongside it.
  A side-by-side install takes its own identity: its own uninstall entry,
  directory and Start menu group, so the two never collide. `/PARALLEL=yes`
  does the same without the wizard, for deployment tooling.
- Icons carry the version inside the mark. Major and minor sit in the two
  upper cells the median lines create, patch in the lower one, so two
  installed copies are distinguishable in the Start menu and the taskbar
  without reading a tooltip.
- The window title and the executable's FileDescription both carry the
  version, so Task Manager and any process list identify which copy is
  which.
- The installer wears the application's own colours: the same dark panel
  and geodesic mark rather than the default grey.

### Notes

- Upgrading in place already worked and was verified rather than assumed:
  installing a newer build over an older one reuses its location, replaces
  the files, and leaves exactly one uninstall entry.

## [0.1.1] — 2026-09-19

macOS is now built and tested in CI rather than written and hoped for.

### Added

- A macOS `.app` is produced and published alongside the Windows build.
  It is still unrun on real hardware, but it is now built by the same
  pipeline that tests it.
- macOS is a blocking CI job rather than an advisory one.

### Fixed

- `start_new_session=True` on POSIX did the opposite of its intent: it
  detached the ExifTool child into its own session so it survived the
  parent entirely. Caught by macOS CI on its first run.
- Orphaned ExifTool processes are now reaped by the next run. `-stay_open`
  is documented to keep reading past end of file, so closing stdin never
  stopped it, and no POSIX mechanism can guarantee otherwise. Preventing
  accumulation is the achievable goal, and accumulation was the real harm.
- `test_find_exiftool_locates_binary` assumed a Windows layout; the
  archives genuinely differ per platform.
- The test suite no longer requires build tooling to be installed, which
  had made the tests workflow fail on a fresh checkout.

## [0.1.0] — 2026-09-19

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
