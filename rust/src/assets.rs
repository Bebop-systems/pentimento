//! The web interface, compiled into the binary.
//!
//! The Python version served these over a loopback HTTP listener, because
//! a browser can only fetch what a server offers. A webview can be handed
//! a protocol of its own, so the files are embedded here and the network
//! disappears: no port, no listener, nothing for anything to connect to.
//!
//! The files themselves are shared with the Python version rather than
//! copied. Both must render the same interface, and a second copy would
//! drift within a week.

pub struct Asset {
    pub path: &'static str,
    pub mime: &'static str,
    pub body: &'static [u8],
}

macro_rules! asset {
    ($path:literal, $mime:literal) => {
        Asset {
            path: $path,
            mime: $mime,
            body: include_bytes!(concat!("../../web/", $path)),
        }
    };
}

pub const ASSETS: &[Asset] = &[
    asset!("index.html", "text/html; charset=utf-8"),
    asset!("app.js", "text/javascript; charset=utf-8"),
    asset!("app.css", "text/css; charset=utf-8"),
    asset!("geodzk.css", "text/css; charset=utf-8"),
    asset!("geodzk-eink.css", "text/css; charset=utf-8"),
];

/// Look up an asset by request path, tolerating the leading slash and the
/// `/static/` prefix the interface uses.
pub fn lookup(request_path: &str) -> Option<&'static Asset> {
    let cleaned = request_path
        .trim_start_matches('/')
        .trim_start_matches("static/");
    let wanted = if cleaned.is_empty() { "index.html" } else { cleaned };
    ASSETS.iter().find(|asset| asset.path == wanted)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_asset_has_content() {
        for asset in ASSETS {
            assert!(!asset.body.is_empty(), "{} is empty", asset.path);
        }
    }

    #[test]
    fn the_root_serves_the_interface() {
        assert_eq!(lookup("/").unwrap().path, "index.html");
        assert_eq!(lookup("").unwrap().path, "index.html");
    }

    #[test]
    fn the_static_prefix_is_accepted() {
        // The page asks for /static/app.js, which is the path the Python
        // server exposed. The markup is shared, so the prefix stays.
        assert_eq!(lookup("/static/app.js").unwrap().path, "app.js");
        assert_eq!(lookup("/static/geodzk.css").unwrap().path, "geodzk.css");
    }

    #[test]
    fn an_unknown_path_is_not_invented() {
        assert!(lookup("/static/../secret").is_none());
        assert!(lookup("/nope.js").is_none());
    }
}
