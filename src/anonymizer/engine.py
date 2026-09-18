"""Persistent ExifTool process.

This is the only module permitted to spawn a subprocess. Everything above
it works on dataclasses, which keeps the rest of the codebase testable
without ExifTool present.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


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
        )
        return self

    def stop(self) -> None:
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
            # Popen does not close pipes for us unless it was used as a
            # context manager; leaving them open leaks file descriptors.
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass

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
        if self._proc is None:
            self.start()
        self._seq += 1
        seq = self._seq
        lines = [*args, "-echo4", f"{{readyerr{seq}}}", f"-execute{seq}"]
        for line in lines:
            if "\n" in line or "\r" in line:
                raise ExifToolError(f"Argument contains a newline: {line!r}")
        self._proc.stdin.write("\n".join(lines) + "\n")
        self._proc.stdin.flush()
        # Drain stdout first: a large JSON payload can fill the pipe buffer
        # and deadlock if we block on stderr while stdout goes unread.
        stdout = self._read_until(self._proc.stdout, f"{{ready{seq}}}")
        stderr = self._read_until(self._proc.stderr, f"{{readyerr{seq}}}")
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
        """Copy src to dst, then apply arg_lines to dst. src is never modified."""
        src, dst = Path(src), Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        result = self.execute(*arg_lines, "-overwrite_original", str(dst))
        if result.errors:
            raise ExifToolError("; ".join(result.errors))
        return result
