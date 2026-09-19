"""Persistent ExifTool process.

This is the only module permitted to spawn a subprocess. Everything above
it works on dataclasses, which keeps the rest of the codebase testable
without ExifTool present.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .childguard import ChildGuard


class ExifToolError(RuntimeError):
    """ExifTool reported an error for a specific command."""


@dataclass(frozen=True)
class ExifToolResult:
    stdout: str
    stderr: str

    @property
    def errors(self) -> list[str]:
        return [
            line for line in self.stderr.splitlines()
            if line.strip().lower().startswith("error")
        ]

    @property
    def warnings(self) -> list[str]:
        return [
            line for line in self.stderr.splitlines()
            if line.strip().lower().startswith("warning")
        ]


class ExifToolEngine:
    """Wraps `exiftool -stay_open True -@ -`.

    ExifTool is Perl; a cold start costs roughly 200ms. One long-lived
    process makes per-request cost negligible.
    """

    def __init__(self, exiftool_path: Path):
        self.exiftool_path = Path(exiftool_path)
        self._proc: subprocess.Popen | None = None
        self._seq = 0
        # One process, many request threads. Flask's server is threaded by
        # default, and two overlapping commands on a single stay_open
        # process interleave their stdin writes and read each other's
        # stdout. The result is a hang, which looks like the server dying.
        self._lock = threading.RLock()
        self.restarts = 0
        # Binds the ExifTool child to this process, so a hard kill of the
        # parent cannot leave it orphaned.
        self._guard = ChildGuard()

    def start(self) -> "ExifToolEngine":
        if self._proc is not None:
            return self
        self._proc = subprocess.Popen(
            [str(self.exiftool_path), "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **ChildGuard.spawn_kwargs(),
        )
        self._guard.adopt(self._proc)
        return self

    @staticmethod
    def _close_pipes(proc: subprocess.Popen) -> None:
        # Popen does not close pipes for us unless it was used as a context
        # manager; leaving them open leaks file descriptors.
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _discard(self) -> None:
        """Drop a process that is dead or no longer trustworthy."""
        if self._proc is None:
            return
        proc, self._proc = self._proc, None
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        self._close_pipes(proc)

    def _ensure_running(self) -> None:
        """Restart after a crash rather than failing every later request.

        ExifTool can be killed by the OS or die on a malformed file. Without
        this, one bad moment would leave the whole session broken until the
        server was restarted.
        """
        if self._proc is not None and self._proc.poll() is not None:
            self._discard()
            self.restarts += 1
        if self._proc is None:
            self.start()

    def stop(self) -> None:
        with self._lock:
            if self._proc is None:
                return
            proc, self._proc = self._proc, None
            try:
                proc.stdin.write("-stay_open\nFalse\n")
                proc.stdin.flush()
                proc.wait(timeout=10)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                proc.kill()
                proc.wait(timeout=5)
            finally:
                self._close_pipes(proc)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    def _read_until(self, stream, sentinel: str) -> str:
        chunks: list[str] = []
        while True:
            line = stream.readline()
            if line == "":
                raise ExifToolError("ExifTool exited unexpectedly")
            if line.rstrip("\r\n") == sentinel:
                return "".join(chunks)
            chunks.append(line)

    def execute(self, *args: str) -> ExifToolResult:
        """Run one ExifTool command. Each argument becomes its own line.

        Because arguments are newline-delimited rather than shell-parsed, a
        tag value that looks like an option is still only ever a value.
        """
        for line in args:
            if "\n" in line or "\r" in line:
                raise ExifToolError(f"Argument contains a newline: {line!r}")

        # Held for the whole exchange, not just the write: the sentinel that
        # ends this command must be read by the thread that issued it.
        with self._lock:
            self._ensure_running()
            self._seq += 1
            seq = self._seq
            lines = [*args, "-echo4", f"{{readyerr{seq}}}", f"-execute{seq}"]
            try:
                self._proc.stdin.write("\n".join(lines) + "\n")
                self._proc.stdin.flush()
                # Drain stdout first: a large JSON payload can fill the pipe
                # buffer and deadlock a reader blocked on stderr.
                stdout = self._read_until(self._proc.stdout, f"{{ready{seq}}}")
                stderr = self._read_until(self._proc.stderr, f"{{readyerr{seq}}}")
            except (ExifToolError, OSError, ValueError):
                # The stream is out of step with the protocol now, so the
                # process cannot be reused. The next call starts a fresh one.
                self._discard()
                raise
            return ExifToolResult(stdout, stderr)

    def read_json(self, path: Path, *extra: str) -> list[dict]:
        result = self.execute("-j", "-G1", "-a", "-u", "-struct", *extra, str(path))
        if result.errors:
            raise ExifToolError("; ".join(result.errors))
        text = result.stdout.strip()
        if not text:
            raise ExifToolError(f"No metadata returned for {path}")
        return json.loads(text)

    def write(self, src: Path, dst: Path, arg_lines: list[str]) -> ExifToolResult:
        """Copy src to dst, then apply arg_lines to dst. src is never modified.

        `-n` is not optional. Without it ExifTool applies print conversion to
        incoming values, and a value it cannot match in a tag's lookup table
        is silently coerced rather than rejected: `-Orientation=1` and
        `-Orientation=8` both land as 3, with nothing on stderr. Reads use
        `-n` for machine values, so writes must too or the round trip lies.
        """
        src, dst = Path(src), Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        result = self.execute("-n", *arg_lines, "-overwrite_original", str(dst))
        if result.errors:
            raise ExifToolError("; ".join(result.errors))
        return result
