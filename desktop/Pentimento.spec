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
from pathlib import Path

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
    ],
    noarchive=False,
)

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
