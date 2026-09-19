//! Persistent ExifTool process.
//!
//! The only module that spawns anything. A port of the Python engine
//! including every lesson it had to learn the hard way — each of those
//! is commented, because none of them are obvious and all of them cost
//! real time to find.

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;

use crate::childguard::Guard;

#[derive(Debug)]
pub enum EngineError {
    Spawn(String),
    Protocol(String),
    ExifTool(String),
    Json(String),
}

impl std::fmt::Display for EngineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EngineError::Spawn(m) => write!(f, "could not start ExifTool: {m}"),
            EngineError::Protocol(m) => write!(f, "ExifTool protocol error: {m}"),
            EngineError::ExifTool(m) => write!(f, "{m}"),
            EngineError::Json(m) => write!(f, "could not read ExifTool output: {m}"),
        }
    }
}

pub type Result<T> = std::result::Result<T, EngineError>;

struct Session {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    sequence: u64,
}

pub struct ExifTool {
    binary: PathBuf,
    /// One process, many callers. Held for the whole exchange rather than
    /// just the write: the sentinel ending a command must be read by the
    /// caller that issued it, or two overlapping commands interleave on
    /// one stdin and each reads the other's answer. In the Python version
    /// that deadlocked the process, which presents as the application
    /// hanging with nothing in the log.
    session: Mutex<Option<Session>>,
    guard: Option<Guard>,
    restarts: Mutex<u32>,
}

impl ExifTool {
    pub fn new(binary: impl Into<PathBuf>) -> Self {
        Self {
            binary: binary.into(),
            session: Mutex::new(None),
            guard: Guard::new(),
            restarts: Mutex::new(0),
        }
    }

    fn start(&self) -> Result<Session> {
        let mut command = Command::new(&self.binary);
        command
            .args(["-stay_open", "True", "-@", "-"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            // No console window flashing behind a windowed application,
            // which is both visible to the operator and noisy to anything
            // watching process creation.
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = command
            .spawn()
            .map_err(|e| EngineError::Spawn(e.to_string()))?;

        if let Some(guard) = &self.guard {
            guard.adopt(child.id());
        }

        let stdin = child.stdin.take().expect("stdin was piped");
        let stdout = BufReader::new(child.stdout.take().expect("stdout was piped"));
        Ok(Session { child, stdin, stdout, sequence: 0 })
    }

    /// Run one command. Each argument becomes its own line, so a tag
    /// value that looks like an option stays a value: there is no shell
    /// to reinterpret it.
    pub fn execute(&self, args: &[String]) -> Result<String> {
        for arg in args {
            if arg.contains('\n') || arg.contains('\r') {
                return Err(EngineError::Protocol(format!(
                    "argument contains a newline: {arg:?}"
                )));
            }
        }

        let mut held = self.session.lock().unwrap();

        // Restart after a crash rather than failing every later request.
        if let Some(session) = held.as_mut() {
            if matches!(session.child.try_wait(), Ok(Some(_))) {
                *held = None;
                *self.restarts.lock().unwrap() += 1;
            }
        }
        if held.is_none() {
            *held = Some(self.start()?);
        }

        let session = held.as_mut().expect("session was just ensured");
        session.sequence += 1;
        let sequence = session.sequence;

        let mut payload = String::new();
        for arg in args {
            payload.push_str(arg);
            payload.push('\n');
        }
        payload.push_str(&format!("-execute{sequence}\n"));

        let outcome = (|| -> Result<String> {
            session
                .stdin
                .write_all(payload.as_bytes())
                .map_err(|e| EngineError::Protocol(e.to_string()))?;
            session
                .stdin
                .flush()
                .map_err(|e| EngineError::Protocol(e.to_string()))?;

            let sentinel = format!("{{ready{sequence}}}");
            let mut collected = String::new();
            loop {
                let mut line = String::new();
                let read = session
                    .stdout
                    .read_line(&mut line)
                    .map_err(|e| EngineError::Protocol(e.to_string()))?;
                if read == 0 {
                    return Err(EngineError::Protocol(
                        "ExifTool exited unexpectedly".into(),
                    ));
                }
                if line.trim_end_matches(['\r', '\n']) == sentinel {
                    return Ok(collected);
                }
                collected.push_str(&line);
            }
        })();

        if outcome.is_err() {
            // The stream is out of step with the protocol now, so the
            // process cannot be reused. The next call starts a fresh one.
            if let Some(mut session) = held.take() {
                let _ = session.child.kill();
                let _ = session.child.wait();
            }
        }
        outcome
    }

    pub fn read_json(&self, path: &Path, extra: &[&str]) -> Result<serde_json::Value> {
        let mut args: Vec<String> = vec![
            "-j".into(), "-G1".into(), "-a".into(), "-u".into(), "-struct".into(),
        ];
        args.extend(extra.iter().map(|s| s.to_string()));
        args.push(path.to_string_lossy().into_owned());

        let out = self.execute(&args)?;
        let trimmed = out.trim();
        if trimmed.is_empty() {
            return Err(EngineError::ExifTool(format!(
                "no metadata returned for {}",
                path.display()
            )));
        }
        let parsed: serde_json::Value =
            serde_json::from_str(trimmed).map_err(|e| EngineError::Json(e.to_string()))?;
        parsed
            .as_array()
            .and_then(|items| items.first().cloned())
            .ok_or_else(|| EngineError::Json("expected a JSON array".into()))
    }

    /// Copy `source` to `destination`, then apply `args` to the copy.
    /// The source is never modified.
    ///
    /// `-n` is not optional. Without it ExifTool applies print conversion
    /// to incoming values and silently coerces anything it cannot match
    /// in a tag's lookup table: `-Orientation=1` and `-Orientation=8`
    /// both land as 3, with nothing on stderr. Reads use `-n` for machine
    /// values, so writes must too or the round trip lies.
    pub fn write(&self, source: &Path, destination: &Path, args: &[String]) -> Result<()> {
        if let Some(parent) = destination.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| EngineError::Spawn(e.to_string()))?;
        }
        if source != destination {
            std::fs::copy(source, destination)
                .map_err(|e| EngineError::Spawn(e.to_string()))?;
        }

        let mut full: Vec<String> = vec!["-n".into()];
        full.extend(args.iter().cloned());
        full.push("-overwrite_original".into());
        full.push(destination.to_string_lossy().into_owned());

        let out = self.execute(&full)?;
        // stderr is discarded, so errors are recognised from stdout, which
        // is where -stay_open reports them for a write.
        for line in out.lines() {
            if line.trim_start().to_ascii_lowercase().starts_with("error") {
                return Err(EngineError::ExifTool(line.trim().to_string()));
            }
        }
        Ok(())
    }

    pub fn restarts(&self) -> u32 {
        *self.restarts.lock().unwrap()
    }
}

impl Drop for ExifTool {
    fn drop(&mut self) {
        if let Some(mut session) = self.session.lock().unwrap().take() {
            let _ = session.stdin.write_all(b"-stay_open\nFalse\n");
            let _ = session.stdin.flush();
            let _ = session.child.wait();
        }
    }
}
