"""Portfolio verification across separate repositories.

Splitting the platform out changes what a portfolio manifest can assert. When
everything lived in 1 tree the manifest hashed repository zips, which fixed an
exact snapshot. Across repositories that is no longer available, and hashing a
zip would be worse than useless: it would pin a packaging artifact rather than a
revision.

The manifest therefore records versions and compatibility ranges, and this tool
checks the property a hash could never check: that every repository's declared
platform requirement is satisfied by 1 single installed platform version.

Version skew is the failure mode a split introduces. Co-location made it
impossible and made coordinated change mandatory. Separation reverses both.
"""
from __future__ import annotations

import importlib.metadata as md
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "portfolio-manifest.json"


def _parse_range(spec: str) -> tuple[tuple[int, ...] | None, tuple[int, ...] | None]:
    lo = hi = None
    for part in spec.split(","):
        part = part.strip()
        m = re.match(r"(>=|<)\s*([\d.]+)", part)
        if not m:
            continue
        v = tuple(int(x) for x in m.group(2).split("."))
        if m.group(1) == ">=":
            lo = v
        else:
            hi = v
    return lo, hi


def _satisfies(version: str, spec: str) -> bool:
    v = tuple(int(x) for x in version.split(".")[:3])
    lo, hi = _parse_range(spec)
    if lo and v[: len(lo)] < lo:
        return False
    if hi and v[: len(hi)] >= hi:
        return False
    return True


def verify() -> dict:
    errors: list[str] = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    platform = manifest["platform"]

    try:
        installed = md.version(platform["distribution"])
    except md.PackageNotFoundError:
        return {"valid": False, "errors": [f"{platform['distribution']} is not installed"],
                "mode": "unavailable"}

    if installed != platform["version"]:
        errors.append(
            f"manifest declares platform {platform['version']} but {installed} is installed"
        )
    if not _satisfies(installed, platform["compatible_range"]):
        errors.append(
            f"installed platform {installed} is outside the portfolio range "
            f"{platform['compatible_range']}"
        )

    # The property that matters after a split: 1 platform satisfies every dependent.
    ranges: dict[str, str] = {}
    for key, entry in manifest["repositories"].items():
        req = entry["platform_requirement"]
        ranges[key] = req
        if not _satisfies(installed, req):
            errors.append(
                f"{key} requires platform {req}, which the installed {installed} does not satisfy"
            )

    distinct = sorted(set(ranges.values()))
    if len(distinct) > 1:
        errors.append(
            "repositories declare divergent platform requirements, so no single "
            f"platform version can serve them all: {distinct}"
        )

    return {
        "valid": not errors,
        "errors": errors,
        "mode": "split-repositories",
        "platform_installed": installed,
        "platform_declared": platform["version"],
        "repositories": len(manifest["repositories"]),
        "requirement_ranges": distinct,
        "single_platform_serves_all": len(distinct) == 1 and not errors,
    }


def main() -> int:
    report = verify()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
