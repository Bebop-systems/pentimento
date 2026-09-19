#!/usr/bin/env python3
"""Build the desktop application.

    python desktop/build.py              build for this platform
    python desktop/build.py --zip        also produce a portable archive
    python desktop/build.py --installer  also build the Windows installer
    python desktop/build.py --check      report readiness and stop

Build on the platform you are shipping to. PyInstaller freezes the
interpreter it is run by, so it cannot cross-compile: a Windows build
needs Windows and a macOS build needs macOS.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "desktop"
DIST = ROOT / "dist"
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

APP_NAME = "Pentimento"
MACOS_APP = "Pentimento.app"


def check() -> list[str]:
    """Everything that must be true before a build is worth starting."""
    problems: list[str] = []

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        problems.append("PyInstaller is not installed (pip install pyinstaller)")

    try:
        import webview  # noqa: F401
    except ImportError:
        problems.append(
            "pywebview is not installed, so the app would fall back to a "
            "browser (pip install pywebview)"
        )

    if sys.platform.startswith("win"):
        try:
            import clr  # noqa: F401
        except ImportError:
            problems.append(
                "pythonnet is not installed; pywebview needs it on Windows"
            )

    from pentimento.paths import find_exiftool

    if find_exiftool(ROOT / "vendor") is None:
        problems.append(
            "ExifTool is not vendored (python scripts/fetch_exiftool.py)"
        )
    if not (ROOT / "web" / "index.html").is_file():
        problems.append("web/index.html is missing")
    return problems


def report() -> None:
    from pentimento.paths import describe_platform, native_window_support

    ok, detail = native_window_support()
    print(f"platform      : {describe_platform()}")
    print(f"python        : {sys.version.split()[0]}")
    print(f"native window : {'yes' if ok else 'no'} - {detail}")
    problems = check()
    if problems:
        print("\nnot ready:")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("\nready to build")


def stamp_version() -> str:
    """Regenerate the files that cannot read Python at build time.

    Running this every build is what stops a release shipping a binary or
    an installer that disagrees with the source about its own version.
    """
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "set_version.py"), "--regenerate"],
        check=True, cwd=ROOT, capture_output=True,
    )
    from pentimento.version import __version__
    return __version__


def find_iscc() -> Path | None:
    """The Inno Setup compiler, wherever winget happened to put it."""
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
        / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("iscc") or shutil.which("ISCC")
    return Path(found) if found else None


def installer() -> Path:
    """Wrap the built folder in a per-user installer.

    This is the answer to wanting one file to download. A self-extracting
    executable would unpack 737 files into %TEMP% and run an unsigned
    binary from there on every launch, which is indistinguishable from a
    dropper; installing once puts that work where it belongs.
    """
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit(
            "Inno Setup is not installed "
            "(winget install --id JRSoftware.InnoSetup)"
        )
    subprocess.run([str(iscc), str(DESKTOP / "installer.iss")],
                   check=True, cwd=DESKTOP)
    from pentimento.version import __version__
    produced = DIST / f"Pentimento-{__version__}-windows-setup.exe"
    print(f"installer {produced}  ({produced.stat().st_size / 1048576:.0f} MB)")
    return produced


def icons() -> None:
    from desktop.make_icon import build_icns, build_ico, build_png

    build_ico(DESKTOP / "icon.ico")
    build_png(DESKTOP / "icon.png")
    build_icns(DESKTOP / "icon.icns")
    print("icons generated")


def build() -> Path:
    problems = check()
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        raise SystemExit(1)

    version = stamp_version()
    print(f"building {APP_NAME} {version}")
    icons()
    for stale in (DIST / APP_NAME, DIST / MACOS_APP):
        shutil.rmtree(stale, ignore_errors=True)

    subprocess.run(
        [sys.executable, "-m", "PyInstaller",
         str(DESKTOP / f"{APP_NAME}.spec"),
         "--noconfirm",
         "--distpath", str(DIST),
         "--workpath", str(ROOT / "build" / "pyi")],
        check=True, cwd=ROOT,
    )

    produced = DIST / (MACOS_APP if sys.platform == "darwin" else APP_NAME)
    size = sum(f.stat().st_size for f in produced.rglob("*") if f.is_file())
    print(f"\nbuilt {produced}  ({size / 1048576:.0f} MB)")
    return produced


def archive(produced: Path) -> Path:
    system = "macos" if sys.platform == "darwin" else "windows"
    target = DIST / f"{APP_NAME}-{system}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in produced.rglob("*"):
            if item.is_file():
                bundle.write(item, produced.name + "/" + str(item.relative_to(produced)))
    print(f"archived {target}  ({target.stat().st_size / 1048576:.0f} MB)")
    return target


if __name__ == "__main__":
    if "--check" in sys.argv:
        report()
    else:
        result = build()
        if "--zip" in sys.argv:
            archive(result)
        if "--installer" in sys.argv:
            installer()
