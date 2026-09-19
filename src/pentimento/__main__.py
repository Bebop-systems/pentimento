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

from pentimento.engine import ExifToolEngine  # noqa: E402
from pentimento.paths import (  # noqa: E402
    default_output_dir, find_exiftool, is_frozen,
)
from pentimento.server import create_app  # noqa: E402
from pentimento.version import __version__  # noqa: E402

HOST = "127.0.0.1"
# Carries the version so two side-by-side copies are told apart in
# the taskbar, in Task Manager's Apps group and in a window list.
WINDOW_TITLE = f"Pentimento {__version__}"


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
        # A link in the colophon must open the operator's browser rather
        # than navigate the application window away from itself.
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.settings["ALLOW_DOWNLOADS"] = True
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


def selftest(report_path: Path | None = None) -> int:
    """Report what this build can actually do, and exit.

    Run against the packaged application by the build, because the things
    most likely to break in a bundle are exactly the things a source-tree
    test cannot see: a missing hidden import, a pruned data file, a
    webview host that silently declines and falls back to a browser.
    """
    import json

    from pentimento.paths import (
        describe_platform, native_window_support, web_dir,
    )

    window_ok, window_detail = native_window_support()
    exiftool = find_exiftool()
    report = {
        "version": __version__,
        "platform": describe_platform(),
        "frozen": is_frozen(),
        "exiftool": str(exiftool) if exiftool else None,
        "web_assets": (web_dir() / "index.html").is_file(),
        "native_window": window_ok,
        "native_window_detail": window_detail,
    }
    problems = []
    if not report["exiftool"]:
        problems.append("ExifTool is missing from this build")
    if not report["web_assets"]:
        problems.append("web assets are missing from this build")
    if is_frozen() and not window_ok:
        problems.append(f"no native window: {window_detail}")
    report["problems"] = problems

    rendered = json.dumps(report, indent=2)
    print(rendered)
    # A windowed build has no stdout at all, so the report is also written
    # where the caller can read it. That is the only way a build can ask a
    # packaged application whether it actually works.
    if report_path is not None:
        try:
            report_path.write_text(rendered, encoding="utf-8")
        except OSError:
            pass
    return 1 if problems else 0


def main() -> None:
    args = sys.argv[1:]
    if "--selftest" in args:
        destination = None
        for argument in args:
            if argument.startswith("--report="):
                destination = Path(argument.split("=", 1)[1])
        try:
            raise SystemExit(selftest(destination))
        except SystemExit:
            raise
        except BaseException as exc:          # noqa: BLE001
            # A windowed build has no console, so an exception here would
            # be invisible and the build would only see a bare exit code.
            # The report is the only channel there is.
            import json
            import traceback

            if destination is not None:
                try:
                    destination.write_text(json.dumps({
                        "version": __version__,
                        "problems": [f"self test raised {type(exc).__name__}: {exc}"],
                        "traceback": traceback.format_exc(),
                    }, indent=2), encoding="utf-8")
                except OSError:
                    pass
            raise SystemExit(1)
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
