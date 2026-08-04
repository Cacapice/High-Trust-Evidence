"""Sign the portfolio manifest at the release layer.

Hashes establish that files have not changed since the manifest was written.
They do not establish who wrote it: anyone able to modify a file can recompute
the manifest. Signing closes that, and the machinery already existed 1 layer
down for scientific bundles. This lifts it to the release.

HMAC-SHA256 over the canonical manifest bytes, with the key held outside the
tree. This is a managed-key scheme, not public-key: it authenticates a release
to a holder of the same key, which matches the "managed signing key" the
sovereign release model already requires. A detached public-key signature would
be the next step if third-party verification is needed, and the signature block
is shaped to accommodate that without a format change.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "portfolio-manifest.json"
SIGNATURE = ROOT / "manifests" / "portfolio-manifest.sig.json"
KEY_ENV = "PORTFOLIO_SIGNING_KEY"


def canonical_bytes(manifest: dict) -> bytes:
    """Sign the manifest without its own signature block, deterministically."""
    payload = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign(manifest: dict, key: bytes) -> dict:
    digest = hmac.new(key, canonical_bytes(manifest), hashlib.sha256).hexdigest()
    return {
        "algorithm": "hmac-sha256",
        "scheme": "managed-key",
        "signature": digest,
        "manifest_digest": hashlib.sha256(canonical_bytes(manifest)).hexdigest(),
        "signs": "manifests/portfolio-manifest.json",
    }


def verify(manifest: dict, signature: dict, key: bytes) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if signature.get("algorithm") != "hmac-sha256":
        errors.append(f"unexpected algorithm: {signature.get('algorithm')!r}")
    expected = hmac.new(key, canonical_bytes(manifest), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.get("signature", "")):
        errors.append("signature does not match the manifest contents")
    return (not errors), errors


def main() -> int:
    key = os.environ.get(KEY_ENV)
    if not key:
        print(f"no signing key: set {KEY_ENV}", file=sys.stderr)
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    block = sign(manifest, key.encode())
    SIGNATURE.write_text(json.dumps(block, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"signed: {block['signature'][:16]}... -> {SIGNATURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
