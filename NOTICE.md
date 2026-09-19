# Third-party components

## ExifTool

Pentimento does every read and write through
[ExifTool](https://exiftool.org/) by Phil Harvey, which is **not** included
in this source tree. `scripts/fetch_exiftool.py` downloads a pinned release
at setup time, and the desktop build bundles that copy into the application.

ExifTool is distributed under the same terms as Perl itself: the **Artistic
License** or the **GNU General Public License v1 or later**, at your option.
Its full licence travels inside the download, at
`vendor/exiftool-*/exiftool_files/LICENSE`, and is included in every packaged
release.

The Windows standalone build also carries a Strawberry Perl runtime, whose
licences are in `exiftool_files/Licenses_Strawberry_Perl.zip`.

Pentimento invokes ExifTool as a separate process and neither links against
it nor modifies it.

## GeoDzk design system

The interface is built on the GeoDzk design system. `web/geodzk.css` is
vendored verbatim and should be replaced rather than edited; everything
specific to this application lives in `web/app.css` and only references the
system's tokens.

## Runtime dependencies

| Package | Licence |
|---|---|
| Flask, Werkzeug, Jinja2 | BSD-3-Clause |
| pywebview | BSD-3-Clause |
| pythonnet (Windows only) | MIT |
| PyInstaller (build only) | GPL-2.0-or-later with a bundling exception |

PyInstaller's exception permits distributing the applications it produces
under any licence.
