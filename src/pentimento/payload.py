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


# HEIF item types that carry metadata rather than picture data.
_METADATA_ITEM_TYPES = {"Exif", "mime", "uri "}


def _walk_boxes(data: bytes, start: int, end: int):
    """Yield (type, body_start, box_end) for each box in a range.

    Box size 1 means a 64-bit size follows the type; size 0 means the box
    extends to end of file. iPhone HEIC files use the 64-bit form.
    """
    pos = start
    while pos + 8 <= end:
        box_size = struct.unpack(">I", data[pos:pos + 4])[0]
        box_type = data[pos + 4:pos + 8]
        body = pos + 8
        if box_size == 1:
            if pos + 16 > end:
                return
            box_size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            body = pos + 16
        elif box_size == 0:
            box_size = end - pos
        if box_size < 8:
            return
        yield box_type, body, min(pos + box_size, end)
        pos += box_size


def _uint(data: bytes, offset: int, width: int) -> int:
    if width == 0:
        return 0
    return int.from_bytes(data[offset:offset + width], "big")


def _parse_iinf(data: bytes, body: int, end: int) -> dict[int, str]:
    """item_ID -> item_type, from the item information box."""
    version = data[body]
    cursor = body + 4
    if version == 0:
        cursor += 2
    else:
        cursor += 4
    items: dict[int, str] = {}
    for box_type, ibody, iend in _walk_boxes(data, cursor, end):
        if box_type != b"infe":
            continue
        infe_version = data[ibody]
        p = ibody + 4
        if infe_version >= 2:
            id_width = 2 if infe_version == 2 else 4
            item_id = _uint(data, p, id_width)
            p += id_width + 2
            items[item_id] = data[p:p + 4].decode("latin1")
    return items


def _parse_iloc(data: bytes, body: int) -> dict[int, list[tuple[int, int, int]]]:
    """item_ID -> [(construction_method, offset, length), ...]."""
    version = data[body]
    p = body + 4
    offset_size = data[p] >> 4
    length_size = data[p] & 0xF
    base_offset_size = data[p + 1] >> 4
    index_size = data[p + 1] & 0xF if version in (1, 2) else 0
    p += 2
    if version < 2:
        item_count = _uint(data, p, 2)
        p += 2
    else:
        item_count = _uint(data, p, 4)
        p += 4

    out: dict[int, list[tuple[int, int, int]]] = {}
    for _ in range(item_count):
        if version < 2:
            item_id = _uint(data, p, 2)
            p += 2
        else:
            item_id = _uint(data, p, 4)
            p += 4
        construction = 0
        if version in (1, 2):
            construction = _uint(data, p, 2) & 0xF
            p += 2
        p += 2  # data_reference_index
        base_offset = _uint(data, p, base_offset_size)
        p += base_offset_size
        extent_count = _uint(data, p, 2)
        p += 2
        extents = []
        for _ in range(extent_count):
            p += index_size
            extent_offset = _uint(data, p, offset_size)
            p += offset_size
            extent_length = _uint(data, p, length_size)
            p += length_size
            extents.append((construction, base_offset + extent_offset, extent_length))
        out[item_id] = extents
    return out


def _digest_heif_items(data: bytes) -> bytes:
    """Hash the picture items' extents, located through iloc.

    HEIC stores the Exif and XMP payloads inside mdat alongside the coded
    image tiles, so hashing mdat wholesale reports a metadata edit as a
    pixel change. Hashing the items that iloc marks as pictures isolates
    the image data exactly.
    """
    meta_range = None
    for box_type, body, end in _walk_boxes(data, 0, len(data)):
        if box_type == b"meta":
            meta_range = (body + 4, end)  # meta is a FullBox
            break
    if meta_range is None:
        return b""

    items: dict[int, str] = {}
    locations: dict[int, list[tuple[int, int, int]]] = {}
    idat_start = None
    for box_type, body, end in _walk_boxes(data, *meta_range):
        if box_type == b"iinf":
            items = _parse_iinf(data, body, end)
        elif box_type == b"iloc":
            locations = _parse_iloc(data, body)
        elif box_type == b"idat":
            idat_start = body
    if not items or not locations:
        return b""

    h = hashlib.sha256()
    hashed = 0
    for item_id in sorted(items):
        if items[item_id] in _METADATA_ITEM_TYPES:
            continue
        for construction, offset, length in locations.get(item_id, ()):
            if construction == 0:
                start = offset
            elif construction == 1 and idat_start is not None:
                start = idat_start + offset
            else:
                continue
            h.update(data[start:start + length])
            hashed += 1
    return h.digest() if hashed else b""


def _digest_mdat(data: bytes) -> bytes:
    """Concatenate every mdat body. Used for MOV/MP4, which have no iloc."""
    h = hashlib.sha256()
    found = False
    for box_type, body, end in _walk_boxes(data, 0, len(data)):
        if box_type == b"mdat":
            h.update(data[body:end])
            found = True
    return h.digest() if found else b""


def _digest_isobmff(data: bytes) -> bytes:
    return _digest_heif_items(data) or _digest_mdat(data)


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
    data = path.read_bytes()
    digest = {
        "isobmff": _digest_isobmff,
        "jpeg": _digest_jpeg,
        "png": _digest_png,
        "tiff": _digest_tiff,
    }[kind](data)
    return digest.hex() if digest else None
