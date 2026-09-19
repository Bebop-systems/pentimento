//! Plain data. No I/O, no ExifTool knowledge.
//!
//! A direct port of the Python model, including the parts that look odd
//! until you know why. Both versions have to agree field for field, so
//! the behaviour is copied rather than improved.

use std::collections::BTreeMap;

use serde::Serialize;

/// Groups ExifTool reports that are derived or filesystem-level rather
/// than stored in the file. Deleting a Composite tag is meaningless — it
/// is computed from other tags — so these are never edit targets.
pub const DERIVED_GROUPS: &[&str] = &["Composite", "ExifTool", "File", "System"];

/// Colour management. Editing these changes how the image renders.
pub const PROTECTED_GROUPS: &[&str] =
    &["ICC-header", "ICC_Profile", "ICC-view", "ICC-meas", "ICC-chrm"];

/// ExifTool reports MakerNote tags under a family-1 vendor group (Apple,
/// Canon, ...), but the block is only writable as a whole, under the
/// family-0 group MakerNotes. Deleting the sub-tags one by one silently
/// does nothing.
pub const MAKERNOTE_GROUPS: &[&str] = &[
    "Apple", "Canon", "Casio", "DJI", "FLIR", "FujiFilm", "GE", "GoPro", "HP",
    "JVC", "Kodak", "Leica", "Minolta", "Motorola", "Nikon", "Olympus",
    "Panasonic", "Pentax", "PhaseOne", "Reconyx", "Ricoh", "Samsung", "Sanyo",
    "Sigma", "Sony", "MakerNotes", "MakerUnknown",
];

pub fn is_derived(group: &str) -> bool {
    DERIVED_GROUPS.contains(&group)
}

pub fn is_protected(group: &str) -> bool {
    PROTECTED_GROUPS.contains(&group)
}

pub fn is_uneditable(group: &str) -> bool {
    is_derived(group) || is_protected(group)
}

pub fn is_makernote(group: &str) -> bool {
    MAKERNOTE_GROUPS.contains(&group)
}

/// Which family-1 groups a `Group:all` deletion actually removes.
/// `None` when the key is not a group-wide deletion.
pub fn groups_covered_by(key: &str) -> Option<Vec<String>> {
    let (group, name) = split_key(key);
    if !name.eq_ignore_ascii_case("all") {
        return None;
    }
    if group.eq_ignore_ascii_case("makernotes") {
        return Some(MAKERNOTE_GROUPS.iter().map(|g| g.to_string()).collect());
    }
    Some(vec![group.to_string()])
}

/// `"IFD0:Model"` becomes `("IFD0", "Model")`; a bare key keeps an empty
/// group, matching Python's `str.partition`.
pub fn split_key(key: &str) -> (&str, &str) {
    match key.find(':') {
        Some(index) => (&key[..index], &key[index + 1..]),
        None => (key, ""),
    }
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Tag {
    pub group: String,
    pub name: String,
    /// The machine value, from ExifTool's `-n` pass.
    pub value: String,
    /// The human value, from the pass without `-n`.
    pub display: String,
}

impl Tag {
    pub fn key(&self) -> String {
        format!("{}:{}", self.group, self.name)
    }

    pub fn editable(&self) -> bool {
        !is_uneditable(&self.group)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum EditOp {
    Set { key: String, value: String },
    Delete { key: String },
    /// An ExifTool date shift, `-AllDates+=0:0:3 0`. Held apart because
    /// it is neither a set nor a delete and has its own syntax.
    Shift { key: String, value: String },
}

impl EditOp {
    pub fn key(&self) -> &str {
        match self {
            EditOp::Set { key, .. } | EditOp::Delete { key } | EditOp::Shift { key, .. } => key,
        }
    }

    pub fn render(&self) -> String {
        match self {
            EditOp::Set { key, value } => format!("-{key}={value}"),
            EditOp::Delete { key } => format!("-{key}="),
            EditOp::Shift { key, value } => format!("-{key}={value}"),
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct EditPlan {
    pub ops: Vec<EditOp>,
    /// A few ExifTool idioms are argument sequences rather than tag
    /// assignments — notably `-tagsfromfile @`, which restores named tags
    /// after a wholesale `-all=`. When present this replaces the rendered
    /// arguments entirely.
    pub raw_args: Vec<String>,
}

impl EditPlan {
    pub fn new(ops: Vec<EditOp>) -> Self {
        Self { ops, raw_args: Vec::new() }
    }

    pub fn deletions(&self) -> Vec<&str> {
        self.ops
            .iter()
            .filter_map(|op| match op {
                EditOp::Delete { key } => Some(key.as_str()),
                _ => None,
            })
            .collect()
    }

    pub fn to_args(&self) -> Vec<String> {
        if !self.raw_args.is_empty() {
            return self.raw_args.clone();
        }
        self.ops.iter().map(EditOp::render).collect()
    }

    /// Later operations on the same key win, preserving first-seen order,
    /// which is what Python's dict-based merge does.
    pub fn deduplicated(mut self) -> Self {
        let mut order: Vec<String> = Vec::new();
        let mut latest: BTreeMap<String, EditOp> = BTreeMap::new();
        for op in self.ops.drain(..) {
            let key = op.key().to_string();
            if !latest.contains_key(&key) {
                order.push(key.clone());
            }
            latest.insert(key, op);
        }
        self.ops = order
            .into_iter()
            .filter_map(|key| latest.remove(&key))
            .collect();
        self
    }

    pub fn is_empty(&self) -> bool {
        self.ops.is_empty() && self.raw_args.is_empty()
    }
}

#[derive(Clone, Debug, Default)]
pub struct TagSet {
    /// The filename this set describes. The consistency checker reads it,
    /// because a filename is metadata too.
    pub path: String,
    /// Insertion-ordered, because the interface shows them in the order
    /// ExifTool reported them within each category.
    pub order: Vec<String>,
    pub tags: BTreeMap<String, Tag>,
}

impl TagSet {
    pub fn get(&self, key: &str) -> Option<&Tag> {
        self.tags.get(key)
    }

    /// First stored tag matching a bare name, ignoring group. Derived
    /// groups are searched last, so a real stored value wins over the
    /// Composite tag computed from it.
    pub fn by_name(&self, name: &str) -> Option<&Tag> {
        let mut fallback = None;
        for key in &self.order {
            let tag = match self.tags.get(key) {
                Some(tag) => tag,
                None => continue,
            };
            if tag.name != name {
                continue;
            }
            if is_derived(&tag.group) {
                fallback.get_or_insert(tag);
            } else {
                return Some(tag);
            }
        }
        fallback
    }

    pub fn insert(&mut self, tag: Tag) {
        let key = tag.key();
        if !self.tags.contains_key(&key) {
            self.order.push(key.clone());
        }
        self.tags.insert(key, tag);
    }

    pub fn remove(&mut self, key: &str) {
        self.tags.remove(key);
        self.order.retain(|existing| existing != key);
    }

    pub fn editable_tags(&self) -> Vec<&Tag> {
        self.order
            .iter()
            .filter_map(|key| self.tags.get(key))
            .filter(|tag| tag.editable())
            .collect()
    }

    pub fn keys(&self) -> Vec<&str> {
        self.order.iter().map(String::as_str).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tag(group: &str, name: &str, value: &str) -> Tag {
        Tag {
            group: group.into(),
            name: name.into(),
            value: value.into(),
            display: value.into(),
        }
    }

    #[test]
    fn key_joins_group_and_name() {
        assert_eq!(tag("EXIF", "Model", "x").key(), "EXIF:Model");
    }

    #[test]
    fn derived_and_protected_groups_are_not_editable() {
        assert!(!tag("Composite", "GPSPosition", "x").editable());
        assert!(!tag("File", "ImageWidth", "1").editable());
        assert!(!tag("ICC-header", "ProfileDateTime", "x").editable());
        assert!(tag("GPS", "GPSLatitude", "1").editable());
    }

    #[test]
    fn by_name_prefers_a_stored_tag_over_composite() {
        let mut set = TagSet::default();
        set.insert(tag("Composite", "GPSAltitude", "312.1 m"));
        set.insert(tag("GPS", "GPSAltitude", "312.17"));
        assert_eq!(set.by_name("GPSAltitude").unwrap().group, "GPS");
    }

    #[test]
    fn makernotes_all_covers_every_vendor_group() {
        let covered = groups_covered_by("MakerNotes:all").unwrap();
        assert!(covered.contains(&"Apple".to_string()));
        assert!(covered.contains(&"Canon".to_string()));
        assert!(groups_covered_by("GPS:all").unwrap() == vec!["GPS".to_string()]);
        assert!(groups_covered_by("EXIF:Model").is_none());
    }

    #[test]
    fn plan_renders_set_and_delete_like_python() {
        let plan = EditPlan::new(vec![
            EditOp::Set { key: "EXIF:Model".into(), value: "X".into() },
            EditOp::Delete { key: "GPS:all".into() },
        ]);
        assert_eq!(plan.to_args(), vec!["-EXIF:Model=X", "-GPS:all="]);
        assert_eq!(plan.deletions(), vec!["GPS:all"]);
    }

    #[test]
    fn raw_args_replace_the_rendered_ones() {
        let mut plan = EditPlan::new(vec![EditOp::Delete { key: "all".into() }]);
        plan.raw_args = vec!["-all=".into(), "-tagsfromfile".into(), "@".into()];
        assert_eq!(plan.to_args(), vec!["-all=", "-tagsfromfile", "@"]);
    }

    #[test]
    fn later_operations_win_but_order_is_kept() {
        let plan = EditPlan::new(vec![
            EditOp::Set { key: "A".into(), value: "1".into() },
            EditOp::Set { key: "B".into(), value: "2".into() },
            EditOp::Set { key: "A".into(), value: "3".into() },
        ])
        .deduplicated();
        assert_eq!(plan.to_args(), vec!["-A=3", "-B=2"]);
    }
}
