"""Digest the image bitstream, ignoring metadata containers.

Gate G3 compares this digest before and after a write. Equal digests mean
no pixel data moved, which is what "compatible output" has to mean.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_CHUNK = 1 << 20


def container_of(path: Path) -> str:
    with open(path, "rb") as fh:
        head = fh.read(16)
    if head[:8] == _PNG_SIG:
        return "png"
    if head[:2] == b"\xff\xd8":
        return "jpeg"
    if head[4:8] == b"ftyp":
        return "isobmff"
    if head[:4] in (b"II\x2a\x00", b"MM\x00\x2a"):
        return "tiff"
    return "unknown"


def _digest_isobmff(fh, size: int) -> bytes:
    """Concatenate every mdat box body.

    Box size 1 means a 64-bit size follows the type; size 0 means the box
    extends to end of file. iPhone HEIC files use the 64-bit form.
    """
    h = hashlib.sha256()
    pos = 0
    found = False
    while pos + 8 <= size:
        fh.seek(pos)
        header = fh.read(8)
        if len(header) < 8:
            break
        box_size = struct.unpack(">I", header[:4])[0]
        box_type = header[4:8]
        body_start = pos + 8
        if box_size == 1:
            ext = fh.read(8)
            if len(ext) < 8:
                break
            box_size = struct.unpack(">Q", ext)[0]
            body_start = pos + 16
        elif box_size == 0:
            box_size = size - pos
        if box_size < 8:
            break
        if box_type == b"mdat":
            found = True
            remaining = pos + box_size - body_start
            fh.seek(body_start)
            while remaining > 0:
                block = fh.read(min(_CHUNK, remaining))
                if not block:
                    break
                h.update(block)
                remaining -= len(block)
        pos += box_size
    return h.digest() if found else b""


def _digest_jpeg(data: bytes) -> bytes:
    """Hash entropy-coded scan data, skipping every marker segment."""
    h = hashlib.sha256()
    i, n = 2, len(data)
    found = False
    while i < n - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xFF, 0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xD9:
            break
        if i + 4 > n:
            break
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker == 0xDA:
            # Start of scan: entropy-coded data runs to the next real marker.
            start = i + 2 + seg_len
            j = start
            while j < n - 1:
                if data[j] == 0xFF:
                    nxt = data[j + 1]
                    if nxt != 0x00 and not (0xD0 <= nxt <= 0xD7):
                        break
                j += 1
            h.update(data[start:j])
            found = True
            i = j
            continue
        i += 2 + seg_len
    return h.digest() if found else b""


def _digest_png(data: bytes) -> bytes:
    h = hashlib.sha256()
    i = len(_PNG_SIG)
    found = False
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        if ctype == b"IDAT":
            h.update(data[i + 8:i + 8 + length])
            found = True
        if ctype == b"IEND":
            break
        i += 12 + length
    return h.digest() if found else b""


def _digest_tiff(data: bytes) -> bytes:
    """Hash strip and tile data referenced by the first IFD."""
    endian = "<" if data[:2] == b"II" else ">"
    h = hashlib.sha256()
    try:
        ifd_off = struct.unpack(endian + "I", data[4:8])[0]
        count = struct.unpack(endian + "H", data[ifd_off:ifd_off + 2])[0]
        offsets: list[int] = []
        counts: list[int] = []
        for k in range(count):
            e = ifd_off + 2 + k * 12
            tag, typ, num = struct.unpack(endian + "HHI", data[e:e + 8])
            if tag not in (273, 324, 279, 325):
                continue
            raw = data[e + 8:e + 12]
            width, fmt = (2, "H") if typ == 3 else (4, "I")
            if num * width <= 4:
                vals = [
                    struct.unpack(endian + fmt, raw[m * width:(m + 1) * width])[0]
                    for m in range(num)
                ]
            else:
                ptr = struct.unpack(endian + "I", raw)[0]
                vals = [
                    struct.unpack(
                        endian + fmt, data[ptr + m * width:ptr + (m + 1) * width]
                    )[0]
                    for m in range(num)
                ]
            if tag in (273, 324):
                offsets = vals
            else:
                counts = vals
        if not offsets or not counts:
            return b""
        for off, cnt in zip(offsets, counts):
            h.update(data[off:off + cnt])
    except (struct.error, IndexError):
        return b""
    return h.digest()


def payload_digest(path: Path) -> str | None:
    """Hex digest of the image bitstream, or None when it cannot be isolated."""
    path = Path(path)
    kind = container_of(path)
    if kind == "unknown":
        return None
    if kind == "isobmff":
        with open(path, "rb") as fh:
            digest = _digest_isobmff(fh, path.stat().st_size)
        return digest.hex() if digest else None
    data = path.read_bytes()
    digest = {
        "jpeg": _digest_jpeg,
        "png": _digest_png,
        "tiff": _digest_tiff,
    }[kind](data)
    return digest.hex() if digest else None
