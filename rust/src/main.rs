//! Pentimento — a window, and nothing listening on a port.
//!
//! The Python version ran a loopback HTTP server because a browser can
//! only fetch what a server offers. A webview takes a custom protocol
//! instead, so `fetch("/api/preview")` from the page arrives here as a
//! function call. The interface markup does not change, and there is no
//! socket for anything to connect to.

// Windowed in release so no console flashes behind the application.
// `cargo run` in debug keeps a console, which is where --digest is used.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod assets;
mod childguard;
mod engine;
mod model;
mod payload;
mod sha256;

use std::borrow::Cow;

use tao::{
    event::{Event, WindowEvent},
    event_loop::{ControlFlow, EventLoopBuilder},
    window::WindowBuilder,
};
use wry::{
    http::{header::CONTENT_TYPE, Request, Response},
    WebViewBuilder,
};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// A scheme of our own. The page's origin becomes `pentimento://local`,
/// so relative fetches from the interface land in the handler below
/// rather than on a network.
const SCHEME: &str = "pentimento";

fn respond(request: Request<Vec<u8>>) -> Response<Cow<'static, [u8]>> {
    let path = request.uri().path().to_owned();

    if let Some(asset) = assets::lookup(&path) {
        return Response::builder()
            .header(CONTENT_TYPE, asset.mime)
            .body(Cow::Borrowed(asset.body))
            .unwrap();
    }

    Response::builder()
        .status(404)
        .header(CONTENT_TYPE, "application/json")
        .body(Cow::Owned(
            br#"{"error":"not found"}"#.to_vec(),
        ))
        .unwrap()
}

/// A hidden entry point used to prove the port agrees with the Python
/// implementation. The payload digest is the one number where a silent
/// difference would be catastrophic, so it is comparable from a shell.
fn digest_mode() -> bool {
    let args: Vec<String> = std::env::args().collect();
    let Some(position) = args.iter().position(|a| a == "--digest") else {
        return false;
    };
    match args.get(position + 1) {
        Some(path) => {
            match payload::digest_file(std::path::Path::new(path)) {
                Some(hex) => println!("{hex}"),
                None => println!("unverified"),
            }
        }
        None => eprintln!("--digest needs a path"),
    }
    true
}

fn main() -> wry::Result<()> {
    if digest_mode() {
        return Ok(());
    }
    let event_loop = EventLoopBuilder::new().build();
    let window = WindowBuilder::new()
        .with_title(format!("Pentimento {VERSION}"))
        .with_inner_size(tao::dpi::LogicalSize::new(1280.0, 880.0))
        .with_min_inner_size(tao::dpi::LogicalSize::new(900.0, 620.0))
        // The taskbar and Explorer take the icon from the executable's
        // own resource, set in build.rs, so the window needs none.
        .build(&event_loop)
        .expect("could not create a window");

    let _webview = WebViewBuilder::new()
        .with_url(format!("{SCHEME}://local/"))
        .with_custom_protocol(SCHEME.to_string(), |_id, request| respond(request))
        .build(&window)?;

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;
        if let Event::WindowEvent {
            event: WindowEvent::CloseRequested,
            ..
        } = event
        {
            *control_flow = ControlFlow::Exit;
        }
    });
}
