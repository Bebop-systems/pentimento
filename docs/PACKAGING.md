# Packaging the desktop application

```bash
python desktop/build.py --check      # is this machine ready
python desktop/build.py --zip        # build, then archive it
```

The result is `dist/MetadataEditor/` with `MetadataEditor.exe` at the top,
plus `dist/MetadataEditor-windows.zip` to hand to someone else. On macOS the
same command produces `dist/Metadata Editor.app`.

Build on the platform you are shipping to. PyInstaller freezes the
interpreter running it, so it cannot cross-compile.

## About the browser

**Nothing bundles a browser, and nothing needs to.** The window is drawn by
a webview the operating system already provides:

| Platform | Draws the window | Ships with the OS |
|---|---|---|
| Windows 10/11 | Edge WebView2 | Yes — Windows 11 always; Windows 10 via Windows Update since 2021 |
| macOS | WKWebView | Yes — always |

That is why the bundle is 74 MB rather than 200 MB, and 35 MB of what
remains is ExifTool. A genuinely small Chromium does not exist: any real one
is 100 MB and up.

If the runtime is somehow missing, `native_window_support()` says so and the
app opens the default browser instead. It degrades rather than fails.

### If you need to guarantee it

For fleets that might lack WebView2 — older Windows 10, LTSC, stripped
images — Microsoft offers two options. The **Evergreen Bootstrapper** is
about 2 MB and installs the shared runtime on first run. The **Fixed Version
runtime** is roughly 130 MB and lives inside your app, immune to anything
installed on the machine. Neither is needed on Windows 11.

## Two tracks

**Track one, which is what exists now.** One folder, a native window from
the system webview, a browser fallback, an unsigned executable. Build and
zip it in about twenty seconds. Anyone on Windows 11 or a current macOS can
run it. This is the whole of the current build.

**Track two, when it needs to be handed to strangers.** Code signing so
SmartScreen and Gatekeeper stay quiet, a real installer (MSI or DMG),
optionally the Fixed Version WebView2 runtime, and a notarisation pass for
macOS. That work is mostly certificates and CI rather than code, and none of
it changes the application.

## Unsigned builds

Windows SmartScreen will warn on first run: More info, then Run anyway.
macOS Gatekeeper will refuse a downloaded unsigned app outright; right-click
and Open, or clear it with:

```bash
xattr -dr com.apple.quarantine "dist/Metadata Editor.app"
```

Signing is the only real fix, and it costs money on both platforms.

## What changes inside a bundle

Two assumptions from running out of a checkout stop holding, and
`src/anonymizer/paths.py` is where both are handled.

**Files move.** PyInstaller unpacks to its own directory, so `web/` and
`vendor/` are found through `resource_dir()` rather than beside the module.

**The app folder is read-only.** Output cannot be written next to the
executable, so a packaged build writes to `~/Pictures/Metadata Editor`. From
a checkout it stays in `output/`. `ANONYMIZER_OUTPUT` overrides both.

A packaged app also never downloads ExifTool. If its bundled copy is missing
that is a broken build, not something to paper over at runtime.

## macOS

The build is written and the spec produces a `.app` with a generated
`.icns`, but **it has not been run on a Mac.** Two things to check first:

ExifTool ships differently. Windows gets the standalone build with its own
Perl; everything else gets the plain distribution, which is a Perl script
relying on the system Perl. `scripts/fetch_exiftool.py` picks the right
archive per platform, but macOS has been deprecating its bundled scripting
runtimes for years. If `/usr/bin/perl` ever goes, the fix is to bundle a
Perl alongside ExifTool.

The icon is generated without `iconutil`, which only exists on macOS, by
writing the ICNS container directly. It validates structurally here; it has
not been seen in a Finder window.

## Size

| Part | Size |
|---|---|
| ExifTool, 508 files | 35 MB |
| Python runtime and Flask | ~25 MB |
| pythonnet and the WinForms host | ~12 MB |
| This application | under 1 MB |
| **Total** | **74 MB, 30 MB zipped** |
