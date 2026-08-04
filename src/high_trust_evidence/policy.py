"""Declarative release policy, minimization metrics, and disclosure accounting.

Three additions, and 1 deliberate refusal.

**Declarative policy.** Release rules were expressed as procedural branches
inside `evaluate`. They are now a specification loaded from a file and evaluated
against a request. A rule that lives in a document can be diffed, reviewed by
someone who does not read Python, and versioned independently of the code that
applies it.

**Minimization metrics.** Publication depended on authorization alone, so
minimization was asserted by a boolean. `MinimizationRecord` reports the source
record count, the aggregation level, what was suppressed and the transformation
chain, which makes minimization visible rather than implicit.

**Disclosure accounting, not a privacy budget.** A ledger records what has been
released, over which source population, and where releases overlap. It is
explicitly *not* a differential privacy budget. See `DisclosureLedger` for why
that distinction is kept.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

POLICY_SCHEMA_VERSION = "1.0"


# --------------------------------------------------------------------------
# Declarative policy
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyRule:
    """One rule: a set of requirements attached to a data classification."""

    classification: str
    signature: str = "optional"          # required | optional | prohibited
    external_release: str = "permitted"  # permitted | prohibited
    max_aggregation_level: str | None = None   # e.g. "individual" forbids row level
    min_source_records: int | None = None
    require_purposes: tuple[str, ...] = ()
    forbid_purposes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.signature not in {"required", "optional", "prohibited"}:
            raise ValueError(f"unknown signature requirement: {self.signature!r}")
        if self.external_release not in {"permitted", "prohibited"}:
            raise ValueError(f"unknown external_release value: {self.external_release!r}")


@dataclass(frozen=True)
class ReleasePolicy:
    """A versioned, file-backed set of rules.

    Loaded from JSON or from a small YAML subset, so the specification can be
    reviewed by a governance reader who does not read the implementation.
    """

    version: str
    rules: Mapping[str, PolicyRule]
    source: str = "inline"
    schema_version: str = POLICY_SCHEMA_VERSION

    # -- loading ----------------------------------------------------------

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, source: str = "inline") -> "ReleasePolicy":
        release = data.get("release") or {}
        rules = {
            name: PolicyRule(
                classification=name,
                signature=spec.get("signature", "optional"),
                external_release=spec.get("external_release", "permitted"),
                max_aggregation_level=spec.get("max_aggregation_level"),
                min_source_records=spec.get("min_source_records"),
                require_purposes=tuple(spec.get("require_purposes", ())),
                forbid_purposes=tuple(spec.get("forbid_purposes", ())),
            )
            for name, spec in release.items()
        }
        return cls(version=str(data.get("version", "0")), rules=rules, source=source)

    @classmethod
    def from_file(cls, path: str | Path) -> "ReleasePolicy":
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix in {".json"}:
            data = json.loads(text)
        else:
            data = _parse_simple_yaml(text)
        return cls.from_mapping(data, source=str(p))

    def digest(self) -> str:
        """Stable hash of the policy, so a decision can name the rules it applied."""
        payload = json.dumps(
            {"version": self.version,
             "rules": {k: asdict(v) for k, v in sorted(self.rules.items())}},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    # -- evaluation -------------------------------------------------------

    def evaluate(
        self,
        *,
        classification: str,
        purpose: str,
        external: bool = False,
        signed: bool = False,
        minimization: "MinimizationRecord | None" = None,
    ) -> "PolicyDecision":
        """Apply the specification to a request. Nothing procedural decides here."""
        violations: list[str] = []
        rule = self.rules.get(classification)
        if rule is None:
            violations.append(
                f"no rule for classification {classification!r}; the policy does not "
                "cover this request, which is refused rather than defaulted"
            )
            return PolicyDecision(allowed=False, violations=tuple(violations),
                                  policy_version=self.version, policy_digest=self.digest(),
                                  rule_applied=None)

        if rule.signature == "required" and not signed:
            violations.append(f"{classification}: signature required")
        if rule.signature == "prohibited" and signed:
            violations.append(f"{classification}: signature prohibited")
        if external and rule.external_release == "prohibited":
            violations.append(f"{classification}: external release prohibited")
        if rule.forbid_purposes and purpose in rule.forbid_purposes:
            violations.append(f"{classification}: purpose {purpose!r} is forbidden")
        if rule.require_purposes and purpose not in rule.require_purposes:
            violations.append(
                f"{classification}: purpose {purpose!r} is not among "
                f"{list(rule.require_purposes)}"
            )
        if minimization is not None:
            if rule.max_aggregation_level and minimization.aggregation_level == "individual" \
                    and rule.max_aggregation_level != "individual":
                violations.append(f"{classification}: individual-level aggregation not permitted")
            if rule.min_source_records is not None \
                    and minimization.source_record_count < rule.min_source_records:
                violations.append(
                    f"{classification}: {minimization.source_record_count} source records "
                    f"is below the minimum of {rule.min_source_records}"
                )
        elif rule.min_source_records is not None or rule.max_aggregation_level:
            violations.append(
                f"{classification}: the rule constrains minimization but no "
                "MinimizationRecord was supplied"
            )

        return PolicyDecision(
            allowed=not violations,
            violations=tuple(violations),
            policy_version=self.version,
            policy_digest=self.digest(),
            rule_applied=classification,
        )


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    violations: tuple[str, ...]
    policy_version: str
    policy_digest: str
    rule_applied: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the 2-level indented mapping subset the policy files use.

    A dependency-free parser rather than a YAML library, because the policy
    grammar is deliberately small: version, release, classification, key/value.
    Anything more complex belongs in JSON.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        key, _, value = raw.strip().partition(":")
        key, value = key.strip(), value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if value.lower() in {"true", "false"}:
                parent[key] = value.lower() == "true"
            elif value.lstrip("-").isdigit():
                parent[key] = int(value)
            else:
                parent[key] = value.strip("'\"")
    return root


# --------------------------------------------------------------------------
# Minimization metrics
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimizationRecord:
    """Quantitative account of what was reduced, and how.

    `data_minimized: True` asserted that minimization happened. It did not say
    how much, over how many records, or what was removed. These fields make the
    claim inspectable.
    """

    source_record_count: int
    aggregation_level: str            # individual | group | population
    suppressed_fields: tuple[str, ...] = ()
    suppressed_cells: int = 0
    transformation_chain: tuple[str, ...] = ()
    smallest_reported_cell: int | None = None

    def __post_init__(self) -> None:
        if self.aggregation_level not in {"individual", "group", "population"}:
            raise ValueError(f"unknown aggregation_level: {self.aggregation_level!r}")
        if self.source_record_count < 0:
            raise ValueError("source_record_count cannot be negative")

    @property
    def concerns(self) -> tuple[str, ...]:
        """Conditions a reviewer should see, stated rather than scored."""
        out: list[str] = []
        if self.aggregation_level == "individual":
            out.append("reported at individual level")
        if self.smallest_reported_cell is not None and self.smallest_reported_cell < 5:
            out.append(f"smallest reported cell is {self.smallest_reported_cell}")
        if not self.transformation_chain:
            out.append("no transformation chain recorded")
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["concerns"] = list(self.concerns)
        return d


# --------------------------------------------------------------------------
# Disclosure accounting
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DisclosureEntry:
    release_id: str
    purpose: str
    classification: str
    source_population: str
    source_record_count: int
    aggregation_level: str
    released_at: str


class DisclosureLedger:
    """Cumulative record of what has been released over a source population.

    **This is not a differential privacy budget, and it is important not to
    call it one.** A privacy budget in the formal sense accounts for a quantity
    epsilon that is spent by mechanisms which add calibrated noise, and it
    yields a proof about the worst-case information gain of an adversary. This
    platform adds no such noise, so there is no epsilon to spend and no
    guarantee to derive. Reporting a number called a "privacy budget" here
    would be a formal-sounding figure with nothing behind it, which is the
    failure mode this whole architecture exists to avoid.

    What can be recorded honestly is an audit ledger: which releases were made,
    over which population, at what aggregation level, and where they overlap.
    That supports the judgement a reviewer has to make about cumulative
    disclosure. It does not make that judgement for them, and it does not
    pretend to be a bound.

    If formal accounting is ever wanted, the route is to add differentially
    private mechanisms at the aggregation step and account for epsilon there.
    The ledger would then record real budget draws instead of release events.
    """

    def __init__(self, entries: Iterable[DisclosureEntry] = ()) -> None:
        self._entries: list[DisclosureEntry] = list(entries)

    def record(
        self, *, release_id: str, purpose: str, classification: str,
        source_population: str, minimization: MinimizationRecord,
    ) -> DisclosureEntry:
        entry = DisclosureEntry(
            release_id=release_id, purpose=purpose, classification=classification,
            source_population=source_population,
            source_record_count=minimization.source_record_count,
            aggregation_level=minimization.aggregation_level,
            released_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self._entries.append(entry)
        return entry

    def population_summary(self, source_population: str) -> dict[str, Any]:
        rel = [e for e in self._entries if e.source_population == source_population]
        levels = sorted({e.aggregation_level for e in rel})
        purposes = sorted({e.purpose for e in rel})
        return {
            "source_population": source_population,
            "release_count": len(rel),
            "distinct_purposes": purposes,
            "aggregation_levels": levels,
            "finest_aggregation": (
                "individual" if "individual" in levels
                else "group" if "group" in levels
                else "population" if levels else None
            ),
            "review_flags": self._flags(rel),
            "accounting_kind": "audit_ledger",
            "not_a_privacy_budget": (
                "no calibrated noise is added, so no epsilon is spent and no "
                "formal disclosure bound is implied"
            ),
        }

    @staticmethod
    def _flags(entries: Sequence[DisclosureEntry]) -> list[str]:
        flags: list[str] = []
        if len(entries) >= 2 and any(e.aggregation_level == "individual" for e in entries):
            flags.append("repeated release over the same population includes individual level")
        if len({e.purpose for e in entries}) > 1 and len(entries) >= 3:
            flags.append("the same population has been released for several distinct purposes")
        counts = {e.source_record_count for e in entries}
        if len(entries) >= 2 and len(counts) > 1:
            flags.append(
                "releases over the same population report differing record counts, so "
                "differencing between them may be possible"
            )
        return flags

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [asdict(e) for e in self._entries],
                "accounting_kind": "audit_ledger"}
