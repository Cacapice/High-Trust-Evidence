"""Figures as first-class research artifacts.

A figure is an inferential claim rendered as an image. This module gives it the
same treatment the numerical results already receive: a declared inference
status, provenance sufficient to regenerate it, a lifecycle state, and a
publication gate that refuses rather than degrades.

The design mirrors `transfermod.certification`:

    ScientificResult  -> publishable / estimate_kind / strict_publish
    FigureResult      -> publishable / inference_status / strict_include

Two deliberate departures from a naive provenance schema:

1.  `input_hash` is not universally meaningful. A schematic has no input data;
    its content lives in the generating script. `ProvenanceRecord` therefore
    records a `content_source` of either `data` or `script` and hashes whichever
    actually determines the rendering. A nullable hash that is silently empty
    for half the corpus is worse than no field.

2.  A commit recorded from a dirty working tree does not describe the figure it
    is attached to. `ProvenanceRecord.dirty` records this, and a dirty tree
    forces `publishable = False`. Provenance that cannot be trusted is treated
    the same way as a censored estimate.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

FIGURE_SCHEMA_VERSION = "1.0"
FIGURE_STANDARD_VERSION = "1.2"


class Lifecycle(str, Enum):
    """How mature a figure is. Only PUBLICATION_READY enters a release bundle."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    QUALIFIED = "qualified"
    PUBLICATION_READY = "publication_ready"
    ARCHIVED = "archived"


class InferenceStatus(str, Enum):
    """Mirrors the repository's result semantics.

    SUPPORTED     certified or exact under the declared coverage assumptions
    QUALIFIED     lower bound, empirical estimate, or censored but directional
    BLOCKED       publishable=False upstream, or indeterminate censoring
    NOT_IDENTIFIED the design does not license the inference at all
    SCHEMATIC     asserts a structure rather than reporting a measurement
    """

    SUPPORTED = "supported"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"
    NOT_IDENTIFIED = "not_identified"
    SCHEMATIC = "schematic"


#: Statuses that may appear in a release bundle.
_INCLUDABLE_STATUS = {
    InferenceStatus.SUPPORTED,
    InferenceStatus.QUALIFIED,
    InferenceStatus.SCHEMATIC,
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str, cwd: Path) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@dataclass(frozen=True)
class ProvenanceRecord:
    """Everything needed to decide whether a figure can be regenerated.

    `content_source` says which hash determines the rendering:
      - "data"   the figure plots a serialized result; `input_hash` covers it
      - "script" the figure is a schematic; `script_hash` is the only anchor
    """

    generated_by: str
    content_source: str
    script_hash: Optional[str] = None
    input_paths: Sequence[str] = ()
    input_hash: Optional[str] = None
    git_commit: Optional[str] = None
    dirty: Optional[bool] = None
    created: str = ""
    figure_standard: str = FIGURE_STANDARD_VERSION
    schema_version: str = FIGURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.content_source not in {"data", "script"}:
            raise ValueError("content_source must be 'data' or 'script'")
        if self.content_source == "data" and not self.input_paths:
            raise ValueError(
                "content_source='data' requires input_paths; use 'script' for schematics"
            )

    @property
    def trustworthy(self) -> bool:
        """Provenance is trustworthy only if the tree was clean and a commit is known."""
        return bool(self.git_commit) and self.dirty is False

    @property
    def untrustworthy_reason(self) -> Optional[str]:
        if self.git_commit is None:
            return "no git commit recorded; the figure cannot be tied to a revision"
        if self.dirty is None:
            return "working tree state unknown"
        if self.dirty:
            return (
                "generated from a dirty working tree, so the recorded commit does "
                "not describe this figure"
            )
        return None

    @classmethod
    def capture(
        cls,
        *,
        generated_by: str,
        repo_root: Path,
        input_paths: Sequence[Path] = (),
        script_path: Optional[Path] = None,
    ) -> "ProvenanceRecord":
        """Capture provenance at generation time."""
        commit = _git("rev-parse", "HEAD", cwd=repo_root)
        status = _git("status", "--porcelain", cwd=repo_root)
        dirty = None if status is None else bool(status.strip())

        inputs = [Path(p) for p in input_paths]
        if inputs:
            digest = hashlib.sha256()
            for p in sorted(inputs, key=lambda q: q.name):
                digest.update(p.name.encode())
                digest.update(_sha256_file(p).encode())
            content_source, input_hash = "data", digest.hexdigest()
        else:
            content_source, input_hash = "script", None

        script_hash = None
        if script_path is not None and Path(script_path).is_file():
            script_hash = _sha256_file(Path(script_path))

        return cls(
            generated_by=generated_by,
            content_source=content_source,
            script_hash=script_hash,
            input_paths=[p.name for p in inputs],
            input_hash=input_hash,
            git_commit=commit,
            dirty=dirty,
            created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )


@dataclass(frozen=True)
class FigureResult:
    """A figure together with the claim it makes and the warrant for that claim."""

    figure: str
    question: str
    observation: str
    interpretation: str
    inference_status: InferenceStatus
    lifecycle: Lifecycle
    provenance: ProvenanceRecord
    #: Stable identifier of the ScientificResult or serialized result this renders.
    result_ref: Optional[str] = None
    #: Declared scale departures: logarithmic, inverted, truncated, broken.
    scale_declarations: Sequence[str] = ()
    limitation: str = ""
    notes: Sequence[str] = field(default_factory=tuple)

    # -- publication gate ------------------------------------------------

    @property
    def blocking_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.inference_status not in _INCLUDABLE_STATUS:
            reasons.append(f"inference_status={self.inference_status.value}")
        if self.lifecycle is not Lifecycle.PUBLICATION_READY:
            reasons.append(f"lifecycle={self.lifecycle.value}")
        if not self.provenance.trustworthy:
            reasons.append(self.provenance.untrustworthy_reason or "provenance unusable")
        for name in ("question", "observation", "interpretation"):
            if not getattr(self, name).strip():
                reasons.append(f"{name} is empty")
        if (
            self.inference_status is not InferenceStatus.SCHEMATIC
            and self.result_ref is None
        ):
            reasons.append("no result_ref: the figure cannot be traced to a result")
        return reasons

    @property
    def publishable(self) -> bool:
        return not self.blocking_reasons

    def strict_include(self) -> dict[str, Any]:
        """Return the release payload, or refuse.

        The analogue of `strict_publish` for numerical results: a figure that
        cannot carry its own warrant does not enter a release bundle.
        """
        if not self.publishable:
            raise ValueError(
                f"figure {self.figure!r} is not publication-ready: "
                + "; ".join(self.blocking_reasons)
            )
        return self.to_dict()

    # -- serialization ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "figure": self.figure,
            "question": self.question,
            "observation": self.observation,
            "interpretation": self.interpretation,
            "inference_status": self.inference_status.value,
            "lifecycle": self.lifecycle.value,
            "result_ref": self.result_ref,
            "scale_declarations": list(self.scale_declarations),
            "limitation": self.limitation,
            "publishable": self.publishable,
            "blocking_reasons": self.blocking_reasons,
            "notes": list(self.notes),
            "provenance": asdict(self.provenance),
        }
        d["provenance"]["input_paths"] = list(self.provenance.input_paths)
        return d

    def write_sidecar(self, results_dir: Path) -> Path:
        """Write `<figure stem>.figure.json` beside the image."""
        out = Path(results_dir) / (Path(self.figure).stem + ".figure.json")
        out.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return out

    @classmethod
    def from_sidecar(cls, path: Path) -> "FigureResult":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        prov = dict(d["provenance"])
        prov.pop("schema_version", None) if "schema_version" not in ProvenanceRecord.__dataclass_fields__ else None
        return cls(
            figure=d["figure"],
            question=d["question"],
            observation=d["observation"],
            interpretation=d["interpretation"],
            inference_status=InferenceStatus(d["inference_status"]),
            lifecycle=Lifecycle(d["lifecycle"]),
            provenance=ProvenanceRecord(**prov),
            result_ref=d.get("result_ref"),
            scale_declarations=tuple(d.get("scale_declarations", ())),
            limitation=d.get("limitation", ""),
            notes=tuple(d.get("notes", ())),
        )


# -- render-time structural guard ---------------------------------------


def check_no_text_overlap(fig, *, tol: float = 0.0) -> list[str]:
    """Report text artists whose bounding boxes intersect a patch or each other.

    This runs before `savefig`, which is where the defect is cheap to fix. The
    subtitle overlap in `inferential_fidelity.png` was exactly this: a text
    artist and a rectangle occupying the same region, invisible to any check
    that inspects the saved PNG.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    problems: list[str] = []

    texts = []
    patches = []
    for ax in fig.get_axes():
        for t in ax.texts:
            if t.get_text().strip():
                texts.append((t, t.get_window_extent(renderer)))
        for p in ax.patches:
            patches.append((p, p.get_window_extent(renderer)))

    def overlaps(a, b) -> bool:
        return not (
            a.x1 - tol <= b.x0 or b.x1 - tol <= a.x0
            or a.y1 - tol <= b.y0 or b.y1 - tol <= a.y0
        )

    for t, tb in texts:
        for p, pb in patches:
            if not overlaps(tb, pb):
                continue
            # A legitimate box label is *fully contained* by its box. Centre
            # containment is too weak a test: a sentence crossing a box can
            # have its centre a pixel inside the edge and still be unreadable.
            if (pb.x0 <= tb.x0 and tb.x1 <= pb.x1
                    and pb.y0 <= tb.y0 and tb.y1 <= pb.y1):
                continue
            problems.append(
                f"text {t.get_text()[:40]!r} overlaps a patch without being "
                f"contained by it"
            )
    return problems


def check_render_properties(
    path: Path,
    *,
    min_width: int = 900,
    min_dpi: float = 100.0,
) -> list[str]:
    """Structural checks on a saved image: size and resolution.

    Not pixel regression. These catch a figure saved at a size that will not
    survive reduction, which the standard requires be verified.
    """
    problems: list[str] = []
    try:
        from PIL import Image
    except ImportError:
        return ["Pillow not installed; render properties unchecked"]
    with Image.open(path) as im:
        w, h = im.size
        dpi = im.info.get("dpi", (None, None))[0]
    if w < min_width:
        problems.append(f"width {w}px below {min_width}px; labels may not survive reduction")
    if dpi is not None and dpi < min_dpi:
        problems.append(f"dpi {dpi} below {min_dpi}")
    return problems
