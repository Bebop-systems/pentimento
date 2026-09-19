# PyInstaller spec for Metadata Editor.
#
# One folder, not one file. ExifTool ships as 500-odd Perl files; a
# single-file build would unpack all of them to a temp directory on every
# launch, which is slow and pointless when the folder can just sit there.
#
# No browser is bundled. The window is drawn by Edge WebView2 on Windows
# and WKWebView on macOS, both of which are operating system components.
import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent

sys.path.insert(0, str(ROOT / "src"))

WINDOWS = sys.platform.startswith("win")
MACOS = sys.platform == "darwin"

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "vendor"), "vendor"),
]

hiddenimports = [
    "anonymizer",
    "anonymizer.server",
    "anonymizer.engine",
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MetadataEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # a real application, not a terminal window
    disable_windowed_traceback=False,
    icon=str(SPEC_DIR / "icon.ico") if WINDOWS else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MetadataEditor",
)

if MACOS:
    app = BUNDLE(
        coll,
        name="Metadata Editor.app",
        icon=str(SPEC_DIR / "icon.icns"),
        bundle_identifier="me.adamcho.metadataeditor",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            # The app never reaches the network; say so rather than let
            # macOS imply otherwise.
            "LSApplicationCategoryType": "public.app-category.photography",
        },
    )
