"""Where things live, running from source or from a packaged app.

A bundle changes two assumptions the rest of the code was written under:
its own folder is read-only, so output cannot be written beside the
executable, and the files it ships with are somewhere PyInstaller chose
rather than beside this module.
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent

# The folder ExifTool is unpacked into, relative to the resource root.
VENDOR_NAME = "vendor"

_EXIFTOOL_NAMES = (
    ("exiftool.exe", "exiftool(-k).exe") if os.name == "nt" else ("exiftool",)
)


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Read-only files shipped with the app: web assets and ExifTool.

    PyInstaller sets _MEIPASS for both onefile and onedir builds; falling
    back to the executable's folder keeps this working if that changes.
    """
    if is_frozen():
        bundled = getattr(sys, "_MEIPASS", None)
        return Path(bundled) if bundled else Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def web_dir() -> Path:
    return resource_dir() / "web"


def vendor_dir() -> Path:
    return resource_dir() / VENDOR_NAME


def find_exiftool(search: Path | None = None) -> Path | None:
    """Locate the ExifTool binary, bundled or vendored.

    A packaged app must never fall back to downloading, so this only looks
    at what shipped with it.
    """
    root = Path(search) if search is not None else vendor_dir()
    if not root.exists():
        return None
    for name in _EXIFTOOL_NAMES:
        direct = root / name
        if direct.is_file():
            return direct
        for candidate in sorted(root.rglob(name)):
            if candidate.is_file():
                return candidate
    return None


def default_output_dir() -> Path:
    """Where verified copies go.

    Beside the project when running from source, which keeps a checkout
    self-contained. Inside the user's Pictures folder when packaged,
    because an installed app cannot write next to itself.
    """
    override = os.environ.get("PENTIMENTO_OUTPUT")
    if override:
        return Path(override).expanduser()

    if not is_frozen():
        return PROJECT_ROOT / "output"

    home = Path.home()
    for candidate in ("Pictures", "Documents"):
        folder = home / candidate
        if folder.is_dir():
            return folder / "Pentimento"
    return home / "Pentimento"


def describe_platform() -> str:
    return f"{platform.system()} {platform.machine()}"


def native_window_support() -> tuple[bool, str]:
    """Whether a real application window can be shown, and why not.

    No browser is bundled and none needs to be: Windows supplies Edge
    WebView2 and macOS supplies WKWebView, both OS components. When
    neither answers, the app falls back to the default browser rather
    than failing.
    """
    try:
        import webview  # noqa: F401
    except ImportError:
        return False, "pywebview is not installed"

    system = platform.system()
    if system == "Windows":
        try:
            import clr  # noqa: F401
        except ImportError:
            return False, "pythonnet is missing, so the WinForms host cannot load"
        if _webview2_version() is None:
            return False, (
                "the Edge WebView2 runtime is not installed. Windows 11 ships "
                "it; on older builds install the Evergreen Bootstrapper."
            )
        return True, f"Edge WebView2 {_webview2_version()}"
    if system == "Darwin":
        return True, "WKWebView"
    return True, "system webview"


def _webview2_version() -> str | None:
    """Read the shared WebView2 runtime version from the registry."""
    if platform.system() != "Windows":
        return None
    try:
        import winreg
    except ImportError:
        return None
    client = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root, path in (
        (winreg.HKEY_LOCAL_MACHINE,
         rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{client}"),
        (winreg.HKEY_LOCAL_MACHINE,
         rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{client}"),
        (winreg.HKEY_CURRENT_USER,
         rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{client}"),
    ):
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version:
                    return str(version)
        except OSError:
            continue
    return None
