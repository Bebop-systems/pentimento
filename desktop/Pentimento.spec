# PyInstaller spec for Pentimento.
#
# Two shapes, chosen by PENTIMENTO_ONEFILE:
#
#   onefile  a single self-contained Pentimento.exe. Everything, including
#            508 ExifTool files, is unpacked to a temp directory on each
#            launch, so it starts slower but is one file to hand someone.
#   onedir   an exe beside an _internal folder. Starts immediately.
#
# macOS always uses the directory form, because a .app is a directory by
# definition and Finder already presents it as a single item.
#
# No browser is bundled. The window is drawn by Edge WebView2 on Windows
# and WKWebView on macOS, both of which are operating system components.
import os
import sys
from pathlib import Path, PurePosixPath

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent

sys.path.insert(0, str(ROOT / "src"))

WINDOWS = sys.platform.startswith("win")
MACOS = sys.platform == "darwin"

# A .app is already a bundle, so onefile would only hide it inside one.
ONEFILE = os.environ.get("PENTIMENTO_ONEFILE") == "1" and not MACOS

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "vendor"), "vendor"),
]


def _drop_exiftool_test_suite(entries):
    """Keep ExifTool's own test fixtures out of the bundle.

    fetch_exiftool prunes these, but a stale vendor directory must not be
    able to fail an entire build. t/images holds deliberately malformed
    files, including a Mach-O with no load commands; PyInstaller sees the
    magic number, tries to process it as a real binary and dies.
    """
    keep = []
    for entry in entries:
        target = entry[0].replace("\\", "/")
        if "/t/images/" in target or target.endswith("/t") or "/html/" in target:
            continue
        keep.append(entry)
    return keep

hiddenimports = [
    "pentimento",
    "pentimento.server",
    "pentimento.engine",
    "flask",
    "werkzeug.serving",
    "jinja2",
]
if WINDOWS:
    # pywebview reaches these through pythonnet at runtime, so static
    # analysis cannot see them.
    hiddenimports += [
        "webview.platforms.winforms",
        "clr",
        "clr_loader",
    ]
elif MACOS:
    hiddenimports += ["webview.platforms.cocoa"]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Nothing here draws a chart or opens a notebook.
        "tkinter", "matplotlib", "numpy", "pandas", "scipy",
        "PIL", "pytest", "PyInstaller", "setuptools", "pip",
        # 14 MB of cryptography and OpenSSL that this application never
        # imports. They were swept up from whatever else happened to be
        # installed on the build machine, which also meant a local build
        # and a CI build could differ in size.
        "cryptography", "OpenSSL", "pyOpenSSL", "cffi", "_cffi_backend",
        # Test and packaging machinery that follows dependencies in.
        "unittest", "pydoc_data", "lib2to3", "test", "idlelib",
    ],
    noarchive=False,
)

a.datas = _drop_exiftool_test_suite(a.datas)
a.binaries = _drop_exiftool_test_suite(a.binaries)


def _drop_hoisted_vendor_libraries(binaries, datas):
    """Remove top-level copies of DLLs that already ship inside vendor/.

    PyInstaller inspects the vendored ExifTool, finds Perl's own DLLs and
    helpfully copies them beside the executable as well. ExifTool loads
    them from its own folder, so the top-level pair is 4.6 MB of exact
    duplicate.
    """
    # Both copies arrive in `binaries`: the vendored one keeps its path,
    # the hoisted one is a bare filename at the bundle root.
    vendored = {
        PurePosixPath(dest.replace("\\", "/")).name.lower()
        for dest, *_ in list(binaries) + list(datas)
        if "vendor/" in dest.replace("\\", "/")
    }
    keep = []
    for entry in binaries:
        dest = entry[0].replace("\\", "/")
        name = PurePosixPath(dest).name.lower()
        if "/" not in dest and name in vendored:
            continue
        keep.append(entry)
    return keep


a.binaries = _drop_hoisted_vendor_libraries(a.binaries, a.datas)

pyz = PYZ(a.pure)

# Written by desktop/version_info.py from pentimento.version, so the
# binary's Properties dialog and any file-version detection rule agree
# with the single source.
VERSION_RES = SPEC_DIR / "version_info.txt"

common = dict(
    name="Pentimento",
    version=str(VERSION_RES) if WINDOWS and VERSION_RES.is_file() else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # a real application, not a terminal window
    disable_windowed_traceback=False,
    icon=str(SPEC_DIR / "icon.ico") if WINDOWS else None,
)

if ONEFILE:
    # Everything lives inside the executable and is unpacked at launch.
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
              runtime_tmpdir=None, **common)
    coll = exe
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                   name="Pentimento")

if MACOS:
    app = BUNDLE(
        coll,
        name="Pentimento.app",
        icon=str(SPEC_DIR / "icon.icns"),
        bundle_identifier="systems.bebop.pentimento",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            # The app never reaches the network; say so rather than let
            # macOS imply otherwise.
            "LSApplicationCategoryType": "public.app-category.photography",
        },
    )
