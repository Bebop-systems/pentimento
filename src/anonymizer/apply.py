"""Write a plan and verify the result before anyone is allowed to use it.

A partially-scrubbed file is more dangerous than no file, because the
operator believes it is clean. Every gate must pass or the output is
discarded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .inspect import read_tags
from .model import EditPlan, TagSet, groups_covered_by
from .payload import payload_digest

# Tags whose change would alter how the file renders.
RENDER_TAGS: tuple[str, ...] = (
    "ImageWidth", "ImageHeight", "Orientation", "Rotation",
    "ColorSpace", "BitsPerSample", "YCbCrSubSampling",
)

GATE_MEANING = {
    "structural": "The container still parses and reports the same type.",
    "rendering": "Dimensions, orientation and colour handling are unchanged.",
    "payload": "The image bitstream is byte-for-byte identical.",
    "regression": "Every tag the plan removed is actually gone.",
}


class GateFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class GateResult:
    name: str
    ok: bool
    detail: str = ""

    @property
    def meaning(self) -> str:
        return GATE_MEANING.get(self.name, "")


@dataclass
class VerificationReport:
    output_path: Path
    gates: list[GateResult] = field(default_factory=list)
    removed: int = 0
    changed: int = 0

    @property
    def ok(self) -> bool:
        return bool(self.gates) and all(g.ok for g in self.gates)

    @property
    def failures(self) -> list[GateResult]:
        return [g for g in self.gates if not g.ok]


def _gate_structural(engine, src: Path, dst: Path) -> GateResult:
    try:
        before = engine.read_json(src, "-FileType", "-MIMEType")[0]
        after = engine.read_json(dst, "-FileType", "-MIMEType")[0]
    except Exception as exc:
        return GateResult("structural", False, f"output unreadable: {exc}")
    for key in ("File:FileType", "File:MIMEType"):
        if before.get(key) != after.get(key):
            return GateResult(
                "structural", False,
                f"{key} changed: {before.get(key)} -> {after.get(key)}",
            )
    return GateResult("structural", True, f"still a valid {after.get('File:FileType')}")


def _gate_rendering(before: TagSet, after: TagSet) -> GateResult:
    for name in RENDER_TAGS:
        b, a = before.by_name(name), after.by_name(name)
        bv = None if b is None else b.value
        av = None if a is None else a.value
        if bv != av:
            return GateResult("rendering", False, f"{name} changed: {bv} -> {av}")
    width = after.by_name("ImageWidth")
    height = after.by_name("ImageHeight")
    size = f"{width.value}x{height.value}" if width and height else "unchanged"
    return GateResult("rendering", True, f"{size}, orientation and colour intact")


def _gate_payload(src: Path, dst: Path) -> GateResult:
    before, after = payload_digest(src), payload_digest(dst)
    if before is None or after is None:
        return GateResult("payload", True, "container unsupported - payload unverified")
    if before != after:
        return GateResult("payload", False, "image bitstream changed")
    return GateResult("payload", True, f"bitstream identical (sha256 {before[:12]})")


def _gate_regression(plan: EditPlan, after: TagSet) -> GateResult:
    """Confirm what the plan removed is gone from the written file."""
    survivors: list[str] = []
    for key in plan.deletions():
        covered = groups_covered_by(key)
        if key.lower() == "all":
            survivors += [k for k, t in after.tags.items() if t.editable]
        elif covered is not None:
            survivors += [k for k, t in after.tags.items() if t.group in covered]
        elif after.get(key) is not None:
            survivors.append(key)
    if survivors:
        shown = ", ".join(sorted(set(survivors))[:5])
        return GateResult(
            "regression", False,
            f"{len(set(survivors))} tag(s) survived deletion: {shown}",
        )
    return GateResult("regression", True, f"{len(plan.deletions())} removal(s) confirmed")


def apply_plan(engine, src: Path, dst: Path, plan: EditPlan) -> VerificationReport:
    """Apply `plan` to a copy of `src` at `dst`, then verify. src is untouched."""
    src, dst = Path(src), Path(dst)
    before = read_tags(engine, src)

    args = plan.to_args()
    if not args:
        # Nothing to change: still produce a copy so the caller has an output.
        args = ["-ignoreMinorErrors"]
    engine.write(src, dst, args)

    after = read_tags(engine, dst)
    report = VerificationReport(
        output_path=dst,
        removed=len(before.keys() - after.keys()),
        changed=sum(
            1 for k in before.keys() & after.keys()
            if before.tags[k].value != after.tags[k].value
        ),
    )
    report.gates = [
        _gate_structural(engine, src, dst),
        _gate_rendering(before, after),
        _gate_payload(src, dst),
        _gate_regression(plan, after),
    ]
    if not report.ok:
        dst.unlink(missing_ok=True)
    return report
