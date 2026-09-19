"""Start the editor.

Opens a real application window where one is available, and falls back to
the default browser otherwise. Either way the server is loopback-only and
shuts down when the window closes.
"""
from __future__ import annotations

import socket
import sys
import threading
import webbrowser
from pathlib import Path

if __package__ in (None, ""):
    sys.path[:0] = [str(Path(__file__).resolve().parent.parent.parent)]

from werkzeug.serving import make_server  # noqa: E402

from anonymizer.engine import ExifToolEngine  # noqa: E402
from anonymizer.paths import (  # noqa: E402
    default_output_dir, find_exiftool, is_frozen,
)
from anonymizer.server import create_app  # noqa: E402

HOST = "127.0.0.1"
WINDOW_TITLE = "Metadata Editor"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def resolve_exiftool() -> Path:
    """The bundled copy, or fetch one when running from a checkout."""
    binary = find_exiftool()
    if binary is not None:
        return binary
    if is_frozen():
        raise SystemExit(
            "ExifTool is missing from this build. Reinstall the application."
        )
    from scripts.fetch_exiftool import ensure_exiftool
    return ensure_exiftool()


def open_window(url: str) -> bool:
    """Show a native window. False if no webview backend is available."""
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.create_window(WINDOW_TITLE, url, width=1280, height=880,
                              min_size=(900, 620))
        webview.start()
        return True
    except Exception as exc:  # no GUI backend, headless session, etc.
        print(f"Native window unavailable ({exc}); using the browser.",
              file=sys.stderr)
        return False


def choose_mode(args: list[str]) -> str:
    """window, browser, or headless.

    A packaged app should feel like an application, so it opens its own
    window. Run from a checkout the browser stays the default, which is
    what a developer already expects.
    """
    if "--no-browser" in args:
        return "headless"
    if "--window" in args:
        return "window"
    if "--browser" in args:
        return "browser"
    return "window" if is_frozen() else "browser"


def main() -> None:
    args = sys.argv[1:]
    ports = [int(a) for a in args if a.isdigit()]
    port = ports[0] if ports else free_port()
    mode = choose_mode(args)

    exiftool = resolve_exiftool()
    output = default_output_dir()
    output.mkdir(parents=True, exist_ok=True)

    with ExifToolEngine(exiftool) as engine:
        app = create_app(engine, output_dir=output)
        server = make_server(HOST, port, app, threaded=True)
        url = f"http://{HOST}:{port}/"

        print(f"{WINDOW_TITLE} running at {url}")
        print(f"Cleaned files are saved to {output}")
        print("Nothing leaves this machine.")

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            if mode == "window" and open_window(url):
                return  # the window closed, so the app is done
            if mode != "headless":
                threading.Timer(0.6, lambda: webbrowser.open(url)).start()
            thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
