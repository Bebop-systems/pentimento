"""How a cleaned file gets its name.

A filename is metadata too. `IMG_0942.HEIC` says Apple as loudly as the
Make tag does, so a file reprofiled to a Pixel and still called IMG_0942
contradicts itself — which is precisely what the linter reports. Letting
the output follow the claimed camera's own convention closes that gap.

Patterns are plain text with {tokens}. Rendering is deliberately not
str.format on arbitrary input: that would expose attribute access
({stem.__class__}) and crash on stray braces.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_PATTERN = "{stem}_clean{ext}"

# What each token means, shown in the interface.
TOKENS: dict[str, str] = {
    "stem": "the original filename without its extension",
    "ext": "the original extension, including the dot",
    "preset": "the preset used, e.g. reprofile",
    "profile": "the camera identity used, e.g. pixel-8",
    "date": "today, as YYYYMMDD",
    "time": "now, as HHMMSS",
    "datetime": "now, as YYYYMMDD_HHMMSS",
    "n": "a sequence number, the lowest not already taken",
}

# What to do when the rendered name already exists and carries no {n}.
COLLISION_MODES: dict[str, str] = {
    "overwrite": "Overwrite it",
    "number": "Add a number",
    "timestamp": "Add the time",
}
DEFAULT_COLLISION = "overwrite"

_TOKEN = re.compile(r"\{([a-z]+)(?::([^{}]*))?\}")

# Characters no filesystem here will accept, plus the device names Windows
# still reserves whatever the extension.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_SEQUENCE_LIMIT = 100_000


class NamingError(ValueError):
    """The pattern cannot produce a filename."""


def render(pattern: str, values: dict) -> str:
    """Substitute {tokens}, rejecting anything not in TOKENS."""
    if not pattern.strip():
        raise NamingError("The filename pattern is empty.")

    unmatched = _TOKEN.sub("", pattern)
    if "{" in unmatched or "}" in unmatched:
        raise NamingError("Unbalanced { } in the pattern.")

    def replace(match: re.Match) -> str:
        token, spec = match.group(1), match.group(2)
        if token not in TOKENS:
            known = ", ".join(sorted(TOKENS))
            raise NamingError(f"Unknown token {{{token}}}. Available: {known}")
        value = values.get(token, "")
        if spec:
            try:
                return format(value, spec)
            except (ValueError, TypeError) as exc:
                raise NamingError(f"{{{token}:{spec}}} is not a valid format") from exc
        return str(value)

    return _TOKEN.sub(replace, pattern)


def safe_filename(name: str, fallback_ext: str = "") -> str:
    """Reduce a rendered name to something safe to create.

    The pattern is typed by the operator, so this is about slips rather
    than attack, but a stray slash would otherwise write outside the
    output folder.
    """
    name = _ILLEGAL.sub("_", name).strip().strip(". ")
    name = re.sub(r"_{3,}", "__", name)
    if not name:
        name = "cleaned" + fallback_ext
    stem = Path(name).stem
    if stem.upper() in _RESERVED:
        name = f"_{name}"
    return name[:180]


def build_values(source: Path, preset: str, profile: str = "", moment=None) -> dict:
    moment = moment or datetime.now()
    return {
        "stem": source.stem,
        "ext": source.suffix,
        "preset": preset or "",
        "profile": profile or "",
        "date": moment.strftime("%Y%m%d"),
        "time": moment.strftime("%H%M%S"),
        "datetime": moment.strftime("%Y%m%d_%H%M%S"),
        "n": 1,
    }


@dataclass(frozen=True)
class Naming:
    pattern: str = DEFAULT_PATTERN
    on_collision: str = DEFAULT_COLLISION

    def __post_init__(self):
        if self.on_collision not in COLLISION_MODES:
            raise NamingError(f"Unknown collision mode: {self.on_collision}")

    @property
    def sequenced(self) -> bool:
        """A pattern carrying {n} numbers itself and never collides."""
        return any(m.group(1) == "n" for m in _TOKEN.finditer(self.pattern))

    def preview(self, values: dict) -> str:
        """The name this pattern gives, ignoring what is already on disk."""
        return safe_filename(render(self.pattern, values), values.get("ext", ""))

    def resolve(self, out_dir: Path, values: dict) -> Path:
        """The path to actually write, honouring {n} and the collision mode."""
        out_dir = Path(out_dir)

        if self.sequenced:
            # A camera does not overwrite frame 1; it moves to frame 2.
            for index in range(1, _SEQUENCE_LIMIT):
                candidate = safe_filename(
                    render(self.pattern, {**values, "n": index}),
                    values.get("ext", ""),
                )
                path = out_dir / candidate
                if not path.exists():
                    return path
            raise NamingError(
                f"Every sequence number up to {_SEQUENCE_LIMIT} is taken."
            )

        name = self.preview(values)
        path = out_dir / name
        if not path.exists() or self.on_collision == "overwrite":
            return path

        stem, suffix = Path(name).stem, Path(name).suffix
        if self.on_collision == "timestamp":
            stamp = datetime.now().strftime("%H%M%S")
            return out_dir / safe_filename(f"{stem}_{stamp}{suffix}", suffix)

        for index in range(2, _SEQUENCE_LIMIT):
            candidate = out_dir / safe_filename(f"{stem}_{index}{suffix}", suffix)
            if not candidate.exists():
                return candidate
        raise NamingError("Could not find a free filename.")
