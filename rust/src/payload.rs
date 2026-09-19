//! Digest the image bitstream, ignoring metadata containers.
//!
//! Gate G3 compares this before and after a write. Equal digests mean no
//! pixel data moved, which is what "compatible output" has to mean.
//!
//! This must agree with the Python implementation byte for byte. It is
//! the one module where a difference between the two would be invisible
//! and catastrophic: a wrong digest either blocks every legitimate edit
//! or passes one that damaged the picture.

use std::path::Path;

use crate::sha256::Sha256;

const PNG_SIGNATURE: [u8; 8] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];

/// HEIF item types that carry metadata rather than picture data.
const METADATA_ITEM_TYPES: [&[u8; 4]; 3] = [b"Exif", b"mime", b"uri "];

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Container {
    Png,
    Jpeg,
    IsoBmff,
    Tiff,
    Unknown,
}

pub fn container_of(data: &[u8]) -> Container {
    if data.len() >= 8 && data[..8] == PNG_SIGNATURE {
        return Container::Png;
    }
    if data.len() >= 2 && data[0] == 0xFF && data[1] == 0xD8 {
        return Container::Jpeg;
    }
    if data.len() >= 8 && &data[4..8] == b"ftyp" {
        return Container::IsoBmff;
    }
    if data.len() >= 4 && (&data[..4] == b"II\x2a\x00" || &data[..4] == b"MM\x00\x2a") {
        return Container::Tiff;
    }
    Container::Unknown
}

fn be32(data: &[u8], at: usize) -> Option<u32> {
    data.get(at..at + 4)
        .map(|s| u32::from_be_bytes([s[0], s[1], s[2], s[3]]))
}

fn be16(data: &[u8], at: usize) -> Option<u16> {
    data.get(at..at + 2).map(|s| u16::from_be_bytes([s[0], s[1]]))
}

/// Yield `(type, body_start, box_end)` for each box in a range.
///
/// Box size 1 means a 64-bit size follows the type; size 0 means the box
/// extends to the end. iPhone HEIC files use the 64-bit form, so both
/// paths are exercised by real input rather than only by tests.
fn walk_boxes(data: &[u8], start: usize, end: usize) -> Vec<([u8; 4], usize, usize)> {
    let mut found = Vec::new();
    let mut position = start;
    while position + 8 <= end {
        let size = match be32(data, position) {
            Some(size) => size as u64,
            None => break,
        };
        let kind = [
            data[position + 4], data[position + 5],
            data[position + 6], data[position + 7],
        ];
        let mut body = position + 8;
        let mut length = size;
        if size == 1 {
            if position + 16 > end {
                break;
            }
            let high = be32(data, position + 8).unwrap_or(0) as u64;
            let low = be32(data, position + 12).unwrap_or(0) as u64;
            length = (high << 32) | low;
            body = position + 16;
        } else if size == 0 {
            length = (end - position) as u64;
        }
        if length < 8 {
            break;
        }
        let stop = (position as u64 + length).min(end as u64) as usize;
        found.push((kind, body, stop));
        position += length as usize;
    }
    found
}

fn uint(data: &[u8], at: usize, width: usize) -> u64 {
    if width == 0 {
        return 0;
    }
    let mut value: u64 = 0;
    for index in 0..width {
        value = (value << 8) | *data.get(at + index).unwrap_or(&0) as u64;
    }
    value
}

/// `item_ID -> item_type`, from the item information box.
fn parse_iinf(data: &[u8], body: usize, end: usize) -> Vec<(u32, [u8; 4])> {
    let version = *data.get(body).unwrap_or(&0);
    let cursor = body + 4 + if version == 0 { 2 } else { 4 };
    let mut items = Vec::new();
    for (kind, infe_body, _) in walk_boxes(data, cursor, end) {
        if &kind != b"infe" {
            continue;
        }
        let infe_version = *data.get(infe_body).unwrap_or(&0);
        if infe_version < 2 {
            continue;
        }
        let id_width = if infe_version == 2 { 2 } else { 4 };
        let mut at = infe_body + 4;
        let id = uint(data, at, id_width) as u32;
        at += id_width + 2;
        if let Some(slice) = data.get(at..at + 4) {
            items.push((id, [slice[0], slice[1], slice[2], slice[3]]));
        }
    }
    items
}

/// `item_ID -> [(construction_method, offset, length)]`.
fn parse_iloc(data: &[u8], body: usize) -> Vec<(u32, Vec<(u8, u64, u64)>)> {
    let version = *data.get(body).unwrap_or(&0);
    let mut at = body + 4;
    let packed = *data.get(at).unwrap_or(&0);
    let offset_size = (packed >> 4) as usize;
    let length_size = (packed & 0xF) as usize;
    let packed2 = *data.get(at + 1).unwrap_or(&0);
    let base_offset_size = (packed2 >> 4) as usize;
    let index_size = if version == 1 || version == 2 {
        (packed2 & 0xF) as usize
    } else {
        0
    };
    at += 2;

    let item_count = if version < 2 {
        let count = be16(data, at).unwrap_or(0) as u64;
        at += 2;
        count
    } else {
        let count = be32(data, at).unwrap_or(0) as u64;
        at += 4;
        count
    };

    let mut items = Vec::new();
    for _ in 0..item_count {
        let id = if version < 2 {
            let id = uint(data, at, 2) as u32;
            at += 2;
            id
        } else {
            let id = uint(data, at, 4) as u32;
            at += 4;
            id
        };
        let mut construction = 0u8;
        if version == 1 || version == 2 {
            construction = (uint(data, at, 2) & 0xF) as u8;
            at += 2;
        }
        at += 2; // data_reference_index
        let base_offset = uint(data, at, base_offset_size);
        at += base_offset_size;
        let extent_count = uint(data, at, 2);
        at += 2;

        let mut extents = Vec::new();
        for _ in 0..extent_count {
            at += index_size;
            let offset = uint(data, at, offset_size);
            at += offset_size;
            let length = uint(data, at, length_size);
            at += length_size;
            extents.push((construction, base_offset + offset, length));
        }
        items.push((id, extents));
    }
    items
}

/// Hash the picture items' extents, located through `iloc`.
///
/// HEIC stores the Exif and XMP payloads inside `mdat`, right beside the
/// coded image tiles, so hashing `mdat` wholesale reports a metadata edit
/// as a pixel change. This was not a theory: it failed on the first real
/// file the Python version was given.
fn digest_heif_items(data: &[u8]) -> Option<String> {
    let meta = walk_boxes(data, 0, data.len())
        .into_iter()
        .find(|(kind, _, _)| kind == b"meta")?;
    let (_, meta_body, meta_end) = meta;

    let mut items: Vec<(u32, [u8; 4])> = Vec::new();
    let mut locations: Vec<(u32, Vec<(u8, u64, u64)>)> = Vec::new();
    let mut idat_start: Option<usize> = None;

    for (kind, body, end) in walk_boxes(data, meta_body + 4, meta_end) {
        match &kind {
            b"iinf" => items = parse_iinf(data, body, end),
            b"iloc" => locations = parse_iloc(data, body),
            b"idat" => idat_start = Some(body),
            _ => {}
        }
    }
    if items.is_empty() || locations.is_empty() {
        return None;
    }

    let mut ordered: Vec<(u32, [u8; 4])> = items.clone();
    ordered.sort_by_key(|(id, _)| *id);

    let mut hasher = Sha256::new();
    let mut hashed = 0usize;
    for (id, kind) in ordered {
        if METADATA_ITEM_TYPES.iter().any(|m| *m == &kind) {
            continue;
        }
        let extents = match locations.iter().find(|(other, _)| *other == id) {
            Some((_, extents)) => extents,
            None => continue,
        };
        for (construction, offset, length) in extents {
            let start = match construction {
                0 => *offset as usize,
                1 => match idat_start {
                    Some(base) => base + *offset as usize,
                    None => continue,
                },
                _ => continue,
            };
            let stop = (start + *length as usize).min(data.len());
            if start >= data.len() {
                continue;
            }
            hasher.update(&data[start..stop]);
            hashed += 1;
        }
    }
    if hashed == 0 {
        return None;
    }
    Some(hasher.hex())
}

/// Every `mdat` body. Used for MOV and MP4, which have no `iloc`.
fn digest_mdat(data: &[u8]) -> Option<String> {
    let mut hasher = Sha256::new();
    let mut found = false;
    for (kind, body, end) in walk_boxes(data, 0, data.len()) {
        if &kind == b"mdat" {
            hasher.update(&data[body.min(data.len())..end.min(data.len())]);
            found = true;
        }
    }
    found.then(|| hasher.hex())
}

fn digest_jpeg(data: &[u8]) -> Option<String> {
    let mut hasher = Sha256::new();
    let mut at = 2usize;
    let mut found = false;
    while at + 1 < data.len() {
        if data[at] != 0xFF {
            at += 1;
            continue;
        }
        let marker = data[at + 1];
        if marker == 0xFF || marker == 0xD8 || marker == 0x01 || (0xD0..=0xD7).contains(&marker) {
            at += 2;
            continue;
        }
        if marker == 0xD9 {
            break;
        }
        let segment = match be16(data, at + 2) {
            Some(length) => length as usize,
            None => break,
        };
        if marker == 0xDA {
            // Start of scan: entropy-coded data runs to the next real marker.
            let start = at + 2 + segment;
            let mut scan = start;
            while scan + 1 < data.len() {
                if data[scan] == 0xFF {
                    let next = data[scan + 1];
                    if next != 0x00 && !(0xD0..=0xD7).contains(&next) {
                        break;
                    }
                }
                scan += 1;
            }
            if start <= scan && scan <= data.len() {
                hasher.update(&data[start..scan]);
                found = true;
            }
            at = scan;
            continue;
        }
        at += 2 + segment;
    }
    found.then(|| hasher.hex())
}

fn digest_png(data: &[u8]) -> Option<String> {
    let mut hasher = Sha256::new();
    let mut at = PNG_SIGNATURE.len();
    let mut found = false;
    while at + 8 <= data.len() {
        let length = be32(data, at)? as usize;
        let kind = data.get(at + 4..at + 8)?;
        if kind == b"IDAT" {
            let body = data.get(at + 8..at + 8 + length)?;
            hasher.update(body);
            found = true;
        }
        if kind == b"IEND" {
            break;
        }
        at += 12 + length;
    }
    found.then(|| hasher.hex())
}

fn digest_tiff(data: &[u8]) -> Option<String> {
    let big_endian = &data[..2] == b"MM";
    let read32 = |at: usize| -> Option<u32> {
        let slice = data.get(at..at + 4)?;
        Some(if big_endian {
            u32::from_be_bytes([slice[0], slice[1], slice[2], slice[3]])
        } else {
            u32::from_le_bytes([slice[0], slice[1], slice[2], slice[3]])
        })
    };
    let read16 = |at: usize| -> Option<u16> {
        let slice = data.get(at..at + 2)?;
        Some(if big_endian {
            u16::from_be_bytes([slice[0], slice[1]])
        } else {
            u16::from_le_bytes([slice[0], slice[1]])
        })
    };

    let ifd = read32(4)? as usize;
    let count = read16(ifd)? as usize;
    let mut offsets: Vec<u32> = Vec::new();
    let mut counts: Vec<u32> = Vec::new();

    for index in 0..count {
        let entry = ifd + 2 + index * 12;
        let tag = read16(entry)?;
        if !matches!(tag, 273 | 324 | 279 | 325) {
            continue;
        }
        let kind = read16(entry + 2)?;
        let number = read32(entry + 4)? as usize;
        let width = if kind == 3 { 2 } else { 4 };
        let mut values = Vec::new();
        if number * width <= 4 {
            for slot in 0..number {
                values.push(if kind == 3 {
                    read16(entry + 8 + slot * 2)? as u32
                } else {
                    read32(entry + 8 + slot * 4)?
                });
            }
        } else {
            let pointer = read32(entry + 8)? as usize;
            for slot in 0..number {
                values.push(if kind == 3 {
                    read16(pointer + slot * 2)? as u32
                } else {
                    read32(pointer + slot * 4)?
                });
            }
        }
        if matches!(tag, 273 | 324) {
            offsets = values;
        } else {
            counts = values;
        }
    }
    if offsets.is_empty() || counts.is_empty() {
        return None;
    }

    let mut hasher = Sha256::new();
    for (offset, length) in offsets.iter().zip(counts.iter()) {
        let start = *offset as usize;
        let stop = (start + *length as usize).min(data.len());
        if start < data.len() {
            hasher.update(&data[start..stop]);
        }
    }
    Some(hasher.hex())
}

/// Hex digest of the image bitstream, or `None` when it cannot be
/// isolated. `None` means "unverified" and is reported as such rather
/// than treated as a pass.
pub fn digest(data: &[u8]) -> Option<String> {
    match container_of(data) {
        Container::IsoBmff => digest_heif_items(data).or_else(|| digest_mdat(data)),
        Container::Jpeg => digest_jpeg(data),
        Container::Png => digest_png(data),
        Container::Tiff => digest_tiff(data),
        Container::Unknown => None,
    }
}

pub fn digest_file(path: &Path) -> Option<String> {
    let data = std::fs::read(path).ok()?;
    digest(&data)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn boxed(kind: &[u8; 4], body: &[u8]) -> Vec<u8> {
        let mut out = ((body.len() + 8) as u32).to_be_bytes().to_vec();
        out.extend_from_slice(kind);
        out.extend_from_slice(body);
        out
    }

    fn ftyp() -> Vec<u8> {
        let mut body = b"heic".to_vec();
        body.extend_from_slice(&[0u8; 8]);
        boxed(b"ftyp", &body)
    }

    #[test]
    fn containers_are_recognised() {
        let mut heic = ftyp();
        heic.extend(boxed(b"mdat", b"PIXELS"));
        assert_eq!(container_of(&heic), Container::IsoBmff);
        assert_eq!(container_of(b"\x89PNG\r\n\x1a\n"), Container::Png);
        assert_eq!(container_of(b"\xff\xd8\xff\xe0"), Container::Jpeg);
        assert_eq!(container_of(b"NOTANIMAGE"), Container::Unknown);
    }

    #[test]
    fn mdat_digest_ignores_metadata_changes() {
        let mut a = ftyp();
        a.extend(boxed(b"meta", b"AAAA"));
        a.extend(boxed(b"mdat", b"PIXELS"));
        let mut b = ftyp();
        b.extend(boxed(b"meta", b"BBBBBBBB"));
        b.extend(boxed(b"mdat", b"PIXELS"));
        assert_eq!(digest(&a), digest(&b));
    }

    #[test]
    fn mdat_digest_detects_pixel_changes() {
        let mut a = ftyp();
        a.extend(boxed(b"mdat", b"PIXELS"));
        let mut b = ftyp();
        b.extend(boxed(b"mdat", b"PIXELT"));
        assert_ne!(digest(&a), digest(&b));
    }

    #[test]
    fn the_64_bit_box_form_agrees_with_the_32_bit_one() {
        let body = b"PIXELS";
        let mut large = 1u32.to_be_bytes().to_vec();
        large.extend_from_slice(b"mdat");
        large.extend_from_slice(&((body.len() + 16) as u64).to_be_bytes());
        large.extend_from_slice(body);

        let mut wide = ftyp();
        wide.extend(large);
        let mut narrow = ftyp();
        narrow.extend(boxed(b"mdat", body));
        assert_eq!(digest(&wide), digest(&narrow));
    }

    #[test]
    fn an_unknown_container_is_unverified_not_passed() {
        assert_eq!(digest(b"NOTANIMAGE"), None);
    }
}
