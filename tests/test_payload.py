import struct
import zlib

from pentimento.payload import container_of, payload_digest


def _box(typ: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body) + 8) + typ + body


_FTYP = _box(b"ftyp", b"heic" + b"\x00" * 8)


def _png_chunk(typ: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))


def test_container_detection_isobmff(tmp_path):
    f = tmp_path / "a.heic"
    f.write_bytes(_FTYP + _box(b"mdat", b"PIXELS"))
    assert container_of(f) == "isobmff"


def test_isobmff_digest_ignores_metadata_changes(tmp_path):
    a = tmp_path / "a.heic"
    b = tmp_path / "b.heic"
    a.write_bytes(_FTYP + _box(b"meta", b"AAAA") + _box(b"mdat", b"PIXELS"))
    b.write_bytes(_FTYP + _box(b"meta", b"BBBBBBBB") + _box(b"mdat", b"PIXELS"))
    assert payload_digest(a) == payload_digest(b)


def test_isobmff_digest_detects_pixel_changes(tmp_path):
    a = tmp_path / "a.heic"
    b = tmp_path / "b.heic"
    a.write_bytes(_FTYP + _box(b"mdat", b"PIXELS"))
    b.write_bytes(_FTYP + _box(b"mdat", b"PIXELT"))
    assert payload_digest(a) != payload_digest(b)


def test_isobmff_handles_64bit_box_size(tmp_path):
    """The 64-bit and 32-bit forms wrap identical payloads, so they agree."""
    body = b"PIXELS"
    large = struct.pack(">I", 1) + b"mdat" + struct.pack(">Q", len(body) + 16) + body
    f = tmp_path / "big.heic"
    f.write_bytes(_FTYP + large)
    small = tmp_path / "small.heic"
    small.write_bytes(_FTYP + _box(b"mdat", body))
    assert payload_digest(f) == payload_digest(small)


def test_png_digest_ignores_text_chunks(tmp_path):
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat = _png_chunk(b"IDAT", zlib.compress(b"\x00\x00"))
    iend = _png_chunk(b"IEND", b"")
    a = tmp_path / "a.png"
    a.write_bytes(sig + ihdr + idat + iend)
    b = tmp_path / "b.png"
    b.write_bytes(sig + ihdr + _png_chunk(b"tEXt", b"k\x00v") + idat + iend)
    assert container_of(a) == "png"
    assert payload_digest(a) == payload_digest(b)


def test_jpeg_digest_ignores_exif_segment(engine, make_jpeg, tmp_path):
    src = make_jpeg()
    out = tmp_path / "out.jpg"
    engine.write(src, out, ["-EXIF:Model=SomethingVeryMuchLongerThanBefore"])
    assert container_of(out) == "jpeg"
    assert payload_digest(out) == payload_digest(src)


def test_jpeg_digest_detects_scan_change(make_jpeg, tmp_path):
    src = make_jpeg()
    data = bytearray(src.read_bytes())
    data[-3] ^= 0xFF  # flip a byte inside the entropy-coded scan
    other = tmp_path / "other.jpg"
    other.write_bytes(bytes(data))
    assert payload_digest(other) != payload_digest(src)


def test_unknown_container_returns_none(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"NOTANIMAGE")
    assert payload_digest(f) is None


def test_real_heic_payload_is_stable(sample_heic):
    assert container_of(sample_heic) == "isobmff"
    assert payload_digest(sample_heic) == payload_digest(sample_heic)
