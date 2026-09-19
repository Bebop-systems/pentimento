# Pentimento — Rust shell

A port of the shell, not of the engine. ExifTool stays exactly as it is,
because it is the part that makes the four gates mean anything. What goes
away is the 27 MB of Python runtime, pythonnet and Flask around it.

## Status

| Piece | State |
|---|---|
| Window, WebView2, embedded UI | working |
| Custom protocol instead of HTTP | working — no listening socket at all |
| Job object child guard | ported |
| Tag model and edit plans | ported, tested |
| SHA-256 | written out, NIST vectors pass |
| Payload digest, all four containers | **byte-identical to Python** |
| ExifTool engine | ported, not yet exercised |
| Four gates | not yet |
| Presets, profiles, linter, naming | not yet |

## Parity

The payload digest is the number where a silent difference between the
two implementations would be worst: wrong either way, it blocks every
legitimate edit or passes one that damaged the picture. Both agree on
the real sample and on every container:

```
IMG_0942.HEIC   e2b49da1bf5576736f7cd40b0a9a65e5...   identical
cleaned outputs e2b49da1bf5576736f7cd40b0a9a65e5...   identical
JPEG            0a9a1c39ad97701fd8cf...              identical
PNG             a6e905a26ae2db6f6ab3...              identical
unknown         unverified                            identical
```

`--digest <path>` on a debug build prints it, which is how the comparison
is run.

## Measured so far

| | Python | Rust |
|---|---|---|
| shell binary | 27 MB of runtime | **0.5 MB** |
| working set | 43 MB | **23 MB** |
| listening ports | 1 loopback | **0** |
| processes | 3 | 2 |

The port target is roughly 30 MB installed against the Python version's
53 MB, and nearly all of the remainder is ExifTool.

## Why there is no HTTP server

The Python version ran one because a browser can only fetch what a server
offers. A webview takes a protocol of its own, so `fetch("/api/preview")`
from the page arrives as a function call. The interface markup is shared
with the Python version unchanged — both must render the same thing, and
a second copy would drift within a week.

It also removes a listening socket from a privacy tool, which is worth
more than the bytes.

## Dependencies

Four, deliberately: `wry` and `tao` for the window, `serde` and
`serde_json` for the API payloads. No HTTP server, no async runtime, no
TLS stack. The count is the number to watch — every crate is one more
thing that can change under the application between releases.
