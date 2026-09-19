"""The packaging configuration.

These do not run a build. They pin the decisions a build depends on, so a
change that would quietly produce a broken app fails here first.
"""
import importlib.util
import struct
from pathlib import Path

import pytest

from pentimento.paths import PROJECT_ROOT

DESKTOP = PROJECT_ROOT / "desktop"
SPEC = DESKTOP / "Pentimento.spec"


def test_spec_exists():
    assert SPEC.is_file()


def test_the_bundle_ships_exiftool_and_the_web_assets():
    """Without these the packaged app starts and then cannot do anything."""
    spec = SPEC.read_text(encoding="utf-8")
    assert '(str(ROOT / "web"), "web")' in spec
    assert '(str(ROOT / "vendor"), "vendor")' in spec


def test_the_build_is_one_folder_not_one_file():
    """ExifTool is 500-odd files; onefile would unpack them every launch."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "COLLECT(" in spec
    assert "exclude_binaries=True" in spec


def test_the_app_has_no_console_window():
    assert "console=False" in SPEC.read_text(encoding="utf-8")


def test_windows_webview_imports_are_declared():
    """pywebview reaches these through pythonnet, so PyInstaller cannot see
    them by static analysis and they have to be named."""
    spec = SPEC.read_text(encoding="utf-8")
    for needed in ("webview.platforms.winforms", "clr", "clr_loader"):
        assert needed in spec


def test_no_browser_is_bundled():
    """The window is drawn by an OS component, not a shipped Chromium."""
    spec = SPEC.read_text(encoding="utf-8")
    for absent in ("cefpython", "chromium", "electron"):
        assert absent not in spec.lower()


@pytest.mark.parametrize("name", ["icon.ico", "icon.icns", "icon.png"])
def test_icons_are_generated_and_valid(name):
    from desktop.make_icon import build_icns, build_ico, build_png

    builders = {"icon.ico": build_ico, "icon.icns": build_icns,
                "icon.png": build_png}
    path = DESKTOP / name
    if not path.is_file():
        builders[name](path)
    data = path.read_bytes()
    assert len(data) > 500

    if name == "icon.png":
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
    elif name == "icon.ico":
        reserved, kind, count = struct.unpack("<HHH", data[:6])
        assert (reserved, kind) == (0, 1) and count >= 5
    else:
        assert data[:4] == b"icns"
        assert struct.unpack(">I", data[4:8])[0] == len(data)


def test_icon_renders_deterministically():
    """A build should not produce a different binary from the same source."""
    from desktop.make_icon import render
    assert render(32) == render(32)


def test_build_check_reports_problems_as_actionable_strings():
    """What check() returns is testable anywhere; whether this particular
    machine can build is not a property of the code."""
    from desktop.build import check

    problems = check()
    assert isinstance(problems, list)
    assert all(isinstance(p, str) and p for p in problems)
    # Every problem has to say how to fix it, since it is read by someone
    # who just wants a build.
    assert all(("install" in p.lower() or "missing" in p.lower()
                or "run " in p.lower()) for p in problems), problems


@pytest.mark.skipif(
    importlib.util.find_spec("PyInstaller") is None,
    reason="build tooling not installed; see requirements-build.txt",
)
def test_a_build_machine_reports_ready():
    from desktop.build import check
    assert check() == [], "build tooling is installed but check() objects"


# ---------- installer behaviour ----------

INSTALLER = DESKTOP / "installer.iss"


def test_installer_exists():
    assert INSTALLER.is_file()


def test_upgrade_is_the_default_identity():
    """A fixed AppId is what makes a new build replace the old one rather
    than pile up beside it. Losing it would silently break upgrades."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert '#define BaseAppId     "7B2F5A64-9C3E-4D18-9A6F-2E5C1D0B7A43"' in text
    assert "AppId={code:GetAppId}" in text
    # The upgrade branch must return the base id unchanged.
    assert "Result := '{#BaseAppId}';" in text


def test_a_side_by_side_install_gets_its_own_identity():
    """Two installs sharing one uninstall key would leave the second
    unremovable, so every identifying field is suffixed."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "Result := '{#BaseAppId}_{#AppVersion}'" in text
    for suffixed in ("GetDefaultDir", "GetGroupName", "GetDisplayName"):
        assert f"function {suffixed}" in text
    assert "{#AppName} {#AppVersion}" in text


def test_scripted_appid_has_its_required_companions():
    """Inno refuses to compile an AppId containing constants unless both
    of these are disabled, and the error names them only at build time."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "UsePreviousLanguage=no" in text
    assert "UsePreviousPrivileges=no" in text


def test_the_parallel_switch_is_scriptable():
    """Deployment tooling cannot click a wizard page."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "{param:PARALLEL|no}" in text


def test_the_installer_wears_the_application_styling():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "WizardImageFile=" in text
    assert "WizardSmallImageFile=" in text
    for name in ("wizard-large-164x314.png", "wizard-small-55x55.png"):
        assert name in text
        assert (DESKTOP / name).is_file(), f"{name} is referenced but missing"


def test_wizard_images_are_generated_not_drawn_by_hand():
    """They have to be reproducible, or they drift from the app's icon."""
    from desktop.make_icon import build_wizard_images

    produced = build_wizard_images(DESKTOP)
    assert len(produced) >= 8
    for path in produced:
        data = path.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(data) > 200


def test_parallel_choice_does_not_rely_on_short_circuit_evaluation():
    """Inno's Pascal does not short-circuit `and`, so reading a page's
    selection in the same expression that checks it exists would fault."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert "if not Assigned(ChoicePage) then" in text


def test_icons_carry_the_version_inside_the_mark():
    """Two installed copies have to be distinguishable at a glance."""
    from desktop.make_icon import MIN_VERSION_SIZE, render

    plain = render(128, "")
    stamped = render(128, "0.1.2")
    assert plain != stamped, "the version stamp made no difference"

    # Different versions must look different, or the whole point is lost.
    assert render(128, "0.1.2") != render(128, "0.2.0")

    # Below the threshold the digits would be mush, so they are omitted.
    assert render(16, "0.1.2") == render(16, "")
    assert MIN_VERSION_SIZE >= 32


def test_the_process_identifies_its_version():
    """Task Manager reads FileDescription, and groups apps by window
    title. Both have to name the version or side-by-side copies are
    indistinguishable in a process list."""
    from pentimento.version import __version__

    resource = (DESKTOP / "version_info.txt").read_text(encoding="utf-8")
    description = [line for line in resource.splitlines()
                   if "FileDescription" in line][0]
    assert __version__ in description

    main = (PROJECT_ROOT / "src" / "pentimento" / "__main__.py").read_text(
        encoding="utf-8")
    assert "WINDOW_TITLE = f\"Pentimento {__version__}\"" in main


def test_the_build_excludes_what_it_never_imports():
    """14 MB of cryptography and OpenSSL were being swept up from whatever
    else happened to be installed on the build machine, which also meant a
    local build and a CI build could differ."""
    spec = SPEC.read_text(encoding="utf-8")
    for unused in ("cryptography", "OpenSSL", "cffi"):
        assert f'"{unused}"' in spec


def test_hoisted_vendor_libraries_are_deduplicated():
    """PyInstaller copies Perl's DLLs beside the executable as well as
    leaving them in vendor/. ExifTool loads them from its own folder, so
    the top-level pair was 4.6 MB of exact duplicate."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "_drop_hoisted_vendor_libraries" in spec
    # Both copies arrive in binaries, which is the bug the first attempt had.
    assert "list(binaries) + list(datas)" in spec


def test_exiftool_optional_payloads_are_pruned():
    import scripts.fetch_exiftool as fx

    assert "lib/Image/ExifTool/Geolocation.dat" in fx._PRUNE_FILES
    assert "lib/Image/ExifTool/TagNames.pod" in fx._PRUNE_FILES
    assert any("Lang" in g for g in fx._PRUNE_GLOBS)


def test_cffi_is_kept_even_though_it_looks_like_crypto_clutter():
    """The regression that shipped in 0.1.3.

    cffi sits beside cryptography in any dependency listing and is about a
    megabyte, so it looked like part of the same unused cluster. But
    clr_loader imports it to load the .NET runtime: without it pythonnet
    fails, pywebview finds no host, and the application quietly opens a
    browser tab instead of its own window.
    """
    spec = SPEC.read_text(encoding="utf-8")
    excludes = spec.split("excludes=[")[1].split("]")[0]
    assert '"cffi"' not in excludes
    assert '"_cffi_backend"' not in excludes
    assert '"cffi"' in spec, "cffi must be a hidden import"


def test_the_build_interrogates_its_own_output():
    """Size was verified and the window was not, which is how 0.1.3
    shipped. A bundle is only trustworthy if it is asked directly."""
    build = (DESKTOP / "build.py").read_text(encoding="utf-8")
    assert "def verify(" in build
    assert "--selftest" in build
    assert "verify(produced)" in build


def test_selftest_reports_what_a_bundle_can_break():
    from pentimento.__main__ import selftest
    import io, json, contextlib

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = selftest()
    report = json.loads(out.getvalue())
    for key in ("version", "exiftool", "web_assets", "native_window", "problems"):
        assert key in report
    assert code == 0, report["problems"]


def _png_pixels(png: bytes) -> bytes:
    """Decoded scanlines, so a comparison survives a different zlib.

    Comparing compressed bytes was the first attempt and it failed in CI:
    zlib output differs between versions, so identical pixels produced
    different files on Python 3.13 and 3.14.
    """
    import struct
    import zlib

    body = png[8:]
    idat = b""
    offset = 0
    while offset < len(body):
        length = struct.unpack(">I", body[offset:offset + 4])[0]
        kind = body[offset + 4:offset + 8]
        if kind == b"IDAT":
            idat += body[offset + 8:offset + 8 + length]
        offset += 12 + length
    return zlib.decompress(idat)


def test_the_committed_icons_carry_the_current_version():
    """They were generated stamped, committed stamped, and then rebuilt
    unstamped by every build, so the numbers never reached a release."""
    import struct

    from desktop.make_icon import render
    from pentimento.version import __version__

    data = (DESKTOP / "icon.ico").read_bytes()
    count = struct.unpack("<HHH", data[:6])[2]
    checked = 0
    for index in range(count):
        width, _, _, _, _, _, size, offset = struct.unpack(
            "<BBBBHHII", data[6 + 16 * index:22 + 16 * index]
        )
        pixels = width or 256
        if pixels < 64:
            continue
        entry = _png_pixels(data[offset:offset + size])
        assert entry == _png_pixels(render(pixels, __version__)), (
            f"the {pixels}px icon is not stamped {__version__} - run "
            f"python desktop/make_icon.py"
        )
        assert entry != _png_pixels(render(pixels, "")), (
            f"the {pixels}px icon carries no version stamp at all"
        )
        checked += 1
    assert checked, "no icon large enough to carry a stamp was checked"


def test_the_build_stamps_the_icons_it_regenerates():
    build = (DESKTOP / "build.py").read_text(encoding="utf-8")
    icons = build.split("def icons(")[1].split("\ndef ")[0]
    assert "__version__" in icons, "build.py regenerates icons unstamped"
    for produced in ("build_ico", "build_png", "build_icns",
                     "build_wizard_images"):
        assert produced in icons


def test_uninstall_removes_the_webview_profile():
    """WebView2 writes a browser profile beside the executable the first
    time the window opens. The installer never placed it, so it would
    never remove it - and left behind it keeps {app} non-empty, which is
    exactly what stopped the folder going."""
    text = INSTALLER.read_text(encoding="utf-8")
    assert r'Name: "{app}\*.WebView2"' in text
