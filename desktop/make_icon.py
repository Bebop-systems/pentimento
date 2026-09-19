"""Generate the application icon.

Written by hand rather than with an imaging library: the project has no
image dependency and this is the only thing that would need one. An .ico
may contain PNG data directly (Vista onward), and a PNG is a signature,
an IHDR, a zlib-compressed IDAT and an IEND, which is about forty lines.

The mark matches the one in the interface: a geodesic triangle, drawn at
60 degrees like everything else in the design system.
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

# The design system's dark background and accent.
BG = (0x11, 0x0F, 0x0D, 0xFF)
INK = (0x7D, 0xB9, 0xF2, 0xFF)
FAINT = (0x7D, 0xB9, 0xF2, 0x66)

SIZES = (16, 24, 32, 48, 64, 128, 256)


def _line(canvas, size, x0, y0, x1, y1, colour, width):
    """Draw a line by sampling distance to the segment, which antialiases."""
    dx, dy = x1 - x0, y1 - y0
    length_sq = dx * dx + dy * dy or 1.0
    half = width / 2.0
    lo_x, hi_x = int(min(x0, x1) - width), int(max(x0, x1) + width) + 1
    lo_y, hi_y = int(min(y0, y1) - width), int(max(y0, y1) + width) + 1

    for py in range(max(0, lo_y), min(size, hi_y)):
        for px in range(max(0, lo_x), min(size, hi_x)):
            t = ((px - x0) * dx + (py - y0) * dy) / length_sq
            t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
            nx, ny = x0 + t * dx, y0 + t * dy
            distance = ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5
            coverage = half + 0.5 - distance
            if coverage <= 0:
                continue
            alpha = (1.0 if coverage >= 1 else coverage) * (colour[3] / 255.0)
            index = (py * size + px) * 4
            for channel in range(3):
                under = canvas[index + channel]
                canvas[index + channel] = int(
                    under + (colour[channel] - under) * alpha
                )


def render(size: int) -> bytes:
    canvas = bytearray()
    for _ in range(size * size):
        canvas += bytes(BG)

    # A triangle inset from the edges, with its median lines, so the mark
    # reads as a facet rather than a plain outline.
    m = size * 0.16
    top = (size / 2.0, m)
    left = (m * 0.85, size - m)
    right = (size - m * 0.85, size - m)
    stroke = max(1.0, size * 0.062)

    _line(canvas, size, *top, *left, INK, stroke)
    _line(canvas, size, *left, *right, INK, stroke)
    _line(canvas, size, *right, *top, INK, stroke)
    if size >= 32:
        thin = max(1.0, stroke * 0.5)
        mid_left = ((top[0] + left[0]) / 2, (top[1] + left[1]) / 2)
        mid_right = ((top[0] + right[0]) / 2, (top[1] + right[1]) / 2)
        _line(canvas, size, *mid_left, *mid_right, FAINT, thin)
        _line(canvas, size, top[0], top[1], size / 2.0, size - m, FAINT, thin)

    rows = bytearray()
    for y in range(size):
        rows.append(0)  # filter: none
        rows += canvas[y * size * 4:(y + 1) * size * 4]
    return _png(size, bytes(rows))


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def _png(size: int, raw: bytes) -> bytes:
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))


def build_ico(destination: Path) -> Path:
    images = [(size, render(size)) for size in SIZES]
    offset = 6 + 16 * len(images)
    directory = b""
    body = b""
    for size, png in images:
        dimension = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset
        )
        body += png
        offset += len(png)
    destination.write_bytes(
        struct.pack("<HHH", 0, 1, len(images)) + directory + body
    )
    return destination


def build_png(destination: Path, size: int = 512) -> Path:
    """macOS iconutil wants PNGs; this is the largest source image."""
    destination.write_bytes(render(size))
    return destination


# ICNS chunk types that accept PNG data, and the pixel size each expects.
_ICNS_TYPES = (
    (b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
    (b"ic07", 128), (b"ic08", 256), (b"ic09", 512),
    (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512),
)


def build_icns(destination: Path) -> Path:
    """Write a macOS icon without iconutil, which only exists on macOS.

    Every chunk type used here accepts a PNG payload directly, so the
    format is a magic word, a length, and a run of typed PNGs.
    """
    rendered: dict[int, bytes] = {}
    body = b""
    for kind, size in _ICNS_TYPES:
        if size not in rendered:
            rendered[size] = render(size)
        png = rendered[size]
        body += kind + struct.pack(">I", len(png) + 8) + png
    destination.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
    return destination


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    ico = build_ico(here / "icon.ico")
    png = build_png(here / "icon.png")
    icns = build_icns(here / "icon.icns")
    for produced in (ico, png, icns):
        print(f"{produced}  ({produced.stat().st_size} bytes)")
    sys.exit(0)
