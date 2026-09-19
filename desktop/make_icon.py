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
# Quiet enough to read as a mark rather than a label.
VERSION_INK = (0xA9, 0x9C, 0x8C, 0xDD)

SIZES = (16, 24, 32, 48, 64, 128, 256)



# A 3x5 bitmap font, digits and a full stop. Enough to stamp a version on
# an icon, and small enough to write out rather than depend on one.
_GLYPHS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    ".": ("000", "000", "000", "000", "010"),
}

# Below this the digits turn to mush, so small icons stay unmarked.
MIN_VERSION_SIZE = 32


def _stamp(canvas, size, text, colour, centre, scale):
    """Draw `text` centred on a point, at a given pixel scale."""
    glyphs = [g for g in text if g in _GLYPHS]
    if not glyphs:
        return
    gap = 1
    cells = len(glyphs) * 3 + (len(glyphs) - 1) * gap
    width = cells * scale
    height = 5 * scale
    left = int(centre[0] - width / 2)
    top = int(centre[1] - height / 2)

    for index, glyph in enumerate(glyphs):
        origin = left + index * (3 + gap) * scale
        for row, bits in enumerate(_GLYPHS[glyph]):
            for column, bit in enumerate(bits):
                if bit != "1":
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        px = origin + column * scale + dx
                        py = top + row * scale + dy
                        if not (0 <= px < size and 0 <= py < size):
                            continue
                        i = (py * size + px) * 4
                        alpha = colour[3] / 255.0
                        for channel in range(3):
                            under = canvas[i + channel]
                            canvas[i + channel] = int(
                                under + (colour[channel] - under) * alpha
                            )


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


def render(size: int, version: str = "") -> bytes:
    canvas = bytearray()
    for _ in range(size * size):
        canvas += bytes(BG)

    # A triangle inset from the edges, with its median lines, so the mark
    # reads as a facet rather than a plain outline.
    m = size * 0.15
    base = size - m
    top = (size / 2.0, m)
    left = (m * 0.85, base)
    right = (size - m * 0.85, base)
    stroke = max(1.0, size * 0.062)

    _line(canvas, size, *top, *left, INK, stroke)
    _line(canvas, size, *left, *right, INK, stroke)
    _line(canvas, size, *right, *top, INK, stroke)
    if size >= 32:
        thin = max(1.0, stroke * 0.5)
        mid_left = ((top[0] + left[0]) / 2, (top[1] + left[1]) / 2)
        mid_right = ((top[0] + right[0]) / 2, (top[1] + right[1]) / 2)
        _line(canvas, size, *mid_left, *mid_right, FAINT, thin)
        # The vertical median stops at the crossing rather than running to
        # the base, which would strike straight through the patch digit.
        _line(canvas, size, top[0], top[1], size / 2.0, mid_left[1], FAINT, thin)

    # The version sits inside the mark rather than under it: major and
    # minor in the two upper cells the median lines create, patch in the
    # wide bottom one. Read as part of the geometry, not a caption.
    if version and size >= MIN_VERSION_SIZE:
        parts = version.split("+")[0].split("-")[0].split(".")
        major, minor, patch = (parts + ["0", "0", "0"])[:3]
        scale = max(1, int((size * 0.10) // 5))
        span = base - m
        # Just above the crossing, where the upper cells are wide enough,
        # and centred in the open lower half.
        _stamp(canvas, size, major, VERSION_INK,
               (size / 2.0 - size * 0.085, m + span * 0.42), scale)
        _stamp(canvas, size, minor, VERSION_INK,
               (size / 2.0 + size * 0.085, m + span * 0.42), scale)
        _stamp(canvas, size, patch, VERSION_INK,
               (size / 2.0, m + span * 0.76), scale)

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


def build_ico(destination: Path, version: str = "") -> Path:
    images = [(size, render(size, version)) for size in SIZES]
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


def build_png(destination: Path, size: int = 512, version: str = "") -> Path:
    """macOS iconutil wants PNGs; this is the largest source image."""
    destination.write_bytes(render(size, version))
    return destination


def _render_panel(width: int, height: int, mark_scale: float,
                  align: str = "centre") -> bytes:
    """A wizard panel in the application's own colours.

    Inno Setup draws these beside the installer pages. Matching the dark
    background and the geodesic mark makes the installer feel like the
    thing it is installing rather than a generic Windows dialog.
    """
    canvas = bytearray()
    for _ in range(width * height):
        canvas += bytes(BG)

    size = min(width, height)
    mark = size * mark_scale
    cx = width / 2.0
    cy = height * (0.30 if align == "top" else 0.5)

    top = (cx, cy - mark * 0.58)
    left = (cx - mark * 0.55, cy + mark * 0.42)
    right = (cx + mark * 0.55, cy + mark * 0.42)
    stroke = max(1.0, mark * 0.055)

    _line_rect(canvas, width, height, *top, *left, INK, stroke)
    _line_rect(canvas, width, height, *left, *right, INK, stroke)
    _line_rect(canvas, width, height, *right, *top, INK, stroke)

    thin = max(1.0, stroke * 0.45)
    mid_left = ((top[0] + left[0]) / 2, (top[1] + left[1]) / 2)
    mid_right = ((top[0] + right[0]) / 2, (top[1] + right[1]) / 2)
    _line_rect(canvas, width, height, *mid_left, *mid_right, FAINT, thin)
    _line_rect(canvas, width, height, top[0], top[1], cx, right[1], FAINT, thin)

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        rows += canvas[y * width * 4:(y + 1) * width * 4]
    return _png_sized(width, height, bytes(rows))


def _line_rect(canvas, width, height, x0, y0, x1, y1, colour, thickness):
    """_line, for a canvas that is not square."""
    dx, dy = x1 - x0, y1 - y0
    length_sq = dx * dx + dy * dy or 1.0
    half = thickness / 2.0
    for py in range(max(0, int(min(y0, y1) - thickness)),
                    min(height, int(max(y0, y1) + thickness) + 1)):
        for px in range(max(0, int(min(x0, x1) - thickness)),
                        min(width, int(max(x0, x1) + thickness) + 1)):
            t = ((px - x0) * dx + (py - y0) * dy) / length_sq
            t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
            nx, ny = x0 + t * dx, y0 + t * dy
            distance = ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5
            coverage = half + 0.5 - distance
            if coverage <= 0:
                continue
            alpha = (1.0 if coverage >= 1 else coverage) * (colour[3] / 255.0)
            index = (py * width + px) * 4
            for channel in range(3):
                under = canvas[index + channel]
                canvas[index + channel] = int(
                    under + (colour[channel] - under) * alpha
                )


PNG_SIGNATURE = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


def _png_sized(width: int, height: int, raw: bytes) -> bytes:
    """A PNG of any aspect ratio; _png above is the square case."""
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (PNG_SIGNATURE
            + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))


# Inno draws the tall panel on the welcome and finished pages, and the
# small one in the header of every other page. It picks the closest size
# for the display scaling, so several are supplied.
WIZARD_LARGE = ((164, 314), (192, 386), (246, 459), (273, 556))
WIZARD_SMALL = ((55, 55), (64, 68), (83, 80), (92, 97))


def build_wizard_images(folder: Path) -> list[Path]:
    written = []
    for width, height in WIZARD_LARGE:
        path = folder / f"wizard-large-{width}x{height}.png"
        path.write_bytes(_render_panel(width, height, 0.62, align="top"))
        written.append(path)
    for width, height in WIZARD_SMALL:
        path = folder / f"wizard-small-{width}x{height}.png"
        path.write_bytes(_render_panel(width, height, 0.78))
        written.append(path)
    return written


# ICNS chunk types that accept PNG data, and the pixel size each expects.
_ICNS_TYPES = (
    (b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
    (b"ic07", 128), (b"ic08", 256), (b"ic09", 512),
    (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512),
)


def build_icns(destination: Path, version: str = "") -> Path:
    """Write a macOS icon without iconutil, which only exists on macOS.

    Every chunk type used here accepts a PNG payload directly, so the
    format is a magic word, a length, and a run of typed PNGs.
    """
    rendered: dict[int, bytes] = {}
    body = b""
    for kind, size in _ICNS_TYPES:
        if size not in rendered:
            rendered[size] = render(size, version)
        png = rendered[size]
        body += kind + struct.pack(">I", len(png) + 8) + png
    destination.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
    return destination


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    sys.path[:0] = [str(here.parent / "src")]
    from pentimento.version import __version__

    # Stamped with the version, so two installed copies are told apart at
    # a glance in the Start menu, the taskbar and Explorer.
    ico = build_ico(here / "icon.ico", __version__)
    png = build_png(here / "icon.png", 512, __version__)
    icns = build_icns(here / "icon.icns", __version__)
    # Intune's app logo field wants a square PNG, 256x256, under 1 MB.
    intune = build_png(here / "icon-intune-256.png", 256, __version__)
    wizard = build_wizard_images(here)
    for produced in (ico, png, icns, intune, *wizard):
        print(f"{produced.name}  ({produced.stat().st_size} bytes)")
    sys.exit(0)
