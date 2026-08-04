from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests" / "portfolio-manifest.json"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def check_signature(manifest: dict) -> list[str]:
    """Verify the release signature before any hash is trusted.

    A hash record says the files are unchanged since the manifest was written.
    It does not say who wrote it. The signature is checked first, because
    verifying hashes against an unauthenticated manifest establishes only
    internal consistency.
    """
    import hmac as _hmac
    sig_path = ROOT / "manifests" / "portfolio-manifest.sig.json"
    key = os.environ.get("PORTFOLIO_SIGNING_KEY")
    if not sig_path.is_file():
        return ["manifest is unsigned: no manifests/portfolio-manifest.sig.json. "
                "Hashes establish integrity, not authenticity"]
    if not key:
        return ["manifest signature present but PORTFOLIO_SIGNING_KEY is unset; "
                "signature unverified"]
    sys.path.insert(0, str(ROOT / "tools"))
    from sign_portfolio import canonical_bytes
    block = json.loads(sig_path.read_text(encoding="utf-8"))
    expected = _hmac.new(key.encode(), canonical_bytes(manifest), hashlib.sha256).hexdigest()
    if not _hmac.compare_digest(expected, block.get("signature", "")):
        return ["release signature does not match the manifest contents"]
    return []


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    signature_errors = check_signature(manifest)
    strict = os.environ.get("PORTFOLIO_REQUIRE_SIGNATURE", "1") != "0"
    if signature_errors:
        (errors if strict else []).extend(signature_errors)
        if not strict:
            print("WARNING: " + "; ".join(signature_errors), file=sys.stderr)

    for relative_name, expected in manifest["files"].items():
        path = ROOT / relative_name
        actual = sha256(path) if path.is_file() else "missing"
        if actual != expected:
            errors.append(f"{relative_name}: {actual} != {expected}")

    required_directories = [
        ROOT / "repositories",
        ROOT / "framework" / "qualification",
        ROOT / "framework" / "distribution",
        ROOT / "architecture",
        ROOT / "tools",
        ROOT / "manifests",
    ]
    for directory in required_directories:
        if not directory.is_dir():
            errors.append(f"missing required directory: {directory.relative_to(ROOT)}")

    # An unlisted file passes silently under a whitelist-only manifest. A
    # release could then carry a stray script, an older document or a
    # credential and still report "portfolio verified". The manifest answers
    # "are the listed files intact?"; it must also answer "is this the release
    # I described?".
    exempt = {
        "manifests/portfolio-manifest.json",      # cannot hash itself
        "manifests/portfolio-manifest.sig.json",  # signs the manifest; covered by the key, not by a hash
    }
    on_disk = {
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    unlisted = sorted(on_disk - set(manifest["files"]) - exempt)
    if unlisted:
        errors.append("files present but absent from the manifest: " + ", ".join(unlisted))

    # The verifier must fall inside the envelope it establishes. Left unlisted,
    # it could be edited to return 0 unconditionally and nothing would notice.
    if "tools/verify_portfolio.py" not in manifest["files"]:
        errors.append("tools/verify_portfolio.py is not covered by the manifest; "
                      "the verifier sits outside the integrity envelope it creates")

    root_contract_docs = {
        "ADAPTER_DISCIPLINE.md",
        "POLICY_MIGRATION.md",
        "QUALIFICATION_ALGEBRA.md",
    }
    crowded = sorted(path.name for path in ROOT.iterdir() if path.name in root_contract_docs)
    if crowded:
        errors.append(
            "contract documents must remain under framework/qualification, not the portfolio root: "
            + ", ".join(crowded)
        )

    if errors:
        print("\n".join(errors))
        return 1

    print(
        f"portfolio verified: {manifest['portfolio_version']} "
        f"({manifest['structure']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
