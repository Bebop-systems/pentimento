"""Start the local editor and open a browser at it."""
from __future__ import annotations

import socket
import sys
import threading
import webbrowser
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent.parent.parent)]

from anonymizer.engine import ExifToolEngine  # noqa: E402
from anonymizer.server import create_app  # noqa: E402
from scripts.fetch_exiftool import ensure_exiftool  # noqa: E402

HOST = "127.0.0.1"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def main() -> None:
    exiftool = ensure_exiftool()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else free_port()
    with ExifToolEngine(exiftool) as engine:
        app = create_app(engine)
        url = f"http://{HOST}:{port}/"
        print(f"Metadata editor running at {url}")
        print("Nothing leaves this machine. Ctrl-C to stop.")
        if "--no-browser" not in sys.argv:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        app.run(host=HOST, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
