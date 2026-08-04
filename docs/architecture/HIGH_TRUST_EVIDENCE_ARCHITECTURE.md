# High-trust evidence architecture

## On the name

This was described as a privacy architecture, and that framing understates it.
Confidentiality and controlled release are 1 concern among several. The system
also governs provenance, qualification, reproducibility and authority, and it
governs them as stages of a single evidence lifecycle rather than as separate
features that happen to sit in the same repository.

**High-trust evidence architecture** is the accurate name. Privacy is a
property the lifecycle produces, not a module bolted onto it.

## The 3 layers

    Scientific validity
            |
            v
    Qualification            what may be claimed
            |
            v
    Sovereign publication    who may release what, for which purpose

The separation is load-bearing rather than tidy. Privacy controls sit
downstream of qualification, so they cannot alter what the evidence supports. A
result that is scientifically qualified stays qualified whether or not it is
releasable, and a result that is releasable does not thereby become better
supported. Collapsing the layers would let a release decision distort a
scientific conclusion, which is the failure this ordering prevents.

## Trust boundaries

The layer diagram above is conceptual. This one is operational: it says where
raw data may exist, where only qualified summaries may exist, and where a
signature stops being optional.

```text
┌─ SOVEREIGN ZONE ─────────────────────────────────────────────────┐
│  raw records may exist here and nowhere else                     │
│                                                                  │
│   Owner-held data                                                │
│         │                                                        │
│         ▼                                                        │
│   Scientific analysis          computation moves to the data;    │
│         │                      the data does not move to the     │
│         │                      computation                       │
└─────────┼────────────────────────────────────────────────────────┘
          │  ◄── BOUNDARY 1: minimization
          │      only aggregates cross. MinimizationRecord states
          │      record count, aggregation level, suppression and
          │      transformation chain. Raw records crossing here is
          │      a constructor error, not a policy violation.
┌─────────▼─ QUALIFIED ZONE ───────────────────────────────────────┐
│  qualified summaries only; no raw records                        │
│                                                                  │
│   Qualification                qualifications are structured     │
│         │                      and derive the publication        │
│         │                      status; they never annotate it    │
│         ▼                                                        │
│   Derived publication status                                     │
└─────────┼────────────────────────────────────────────────────────┘
          │  ◄── BOUNDARY 2: authority
          │      ReleasePolicy.evaluate against a declared
          │      classification and purpose. An unknown
          │      classification is refused, not defaulted.
┌─────────▼─ RELEASE ZONE ─────────────────────────────────────────┐
│  signature mandatory for any non-unrestricted classification     │
│                                                                  │
│   Trust decision                bound to this payload and this   │
│         │                       purpose; a decision for another  │
│         │                       payload does not transfer        │
│         ▼                                                        │
│   Publication                   canonical-byte emission,         │
│         │                       signed integrity manifest        │
└─────────┼────────────────────────────────────────────────────────┘
          │  ◄── BOUNDARY 3: authenticity
          │      signature verified before any hash. Hashes show
          │      files are unchanged; only the signature shows who
          │      wrote the manifest.
          ▼
    External consumer
```

### What holds at each boundary

| Boundary | What may cross | What is checked | Signature |
|---|---|---|---|
| 1, minimization | aggregates and derived statistics | `MinimizationRecord`: record count, aggregation level, suppressed fields and cells, transformation chain, smallest reported cell | not yet applicable |
| 2, authority | a qualified result with a declared classification and purpose | `ReleasePolicy.evaluate`, returning the policy version, a rules digest and named violations | required by rule for `owner_data` and `derived` |
| 3, authenticity | a signed, canonical-byte bundle and manifest | manifest signature verified **first**, then per-file hashes | mandatory; an unsigned release fails by default |

### Where raw data may exist

Only inside the sovereign zone. `SovereignEvidenceEnvelope` refuses at
construction any payload carrying `raw_records`, `raw_data`,
`direct_identifiers` or `row_level_data`, so a raw record reaching boundary 1 is
a type error rather than a policy decision. The distinction matters: a policy
decision can be overridden by an authorised person, and this cannot.

### Where signatures become mandatory

At boundary 3 for the release manifest, unconditionally. At boundary 2 for the
bundle, by rule: the shipped policy marks `signature: required` for `owner_data`
and `derived`, and `optional` for `unrestricted`. A classification the policy
does not name is refused before the signature question arises.

## Machine-readable policy

Release rules are a specification, not procedural branches:

```yaml
version: "1.0"
release:
  owner_data:
    signature: required
    external_release: prohibited
    max_aggregation_level: group
    min_source_records: 50
    forbid_purposes: marketing
```

`ReleasePolicy.evaluate` applies the specification and returns a
`PolicyDecision` carrying the policy version, a digest of the rules applied, and
the specific violations. A rule in a file can be diffed, reviewed by a
governance reader who does not read Python, and versioned independently of the
code applying it.

An unknown classification is refused rather than defaulted. A policy that does
not cover a request has not permitted it.

## Minimization made visible

`data_minimized: True` asserted that minimization happened without saying how
much. `MinimizationRecord` reports the source record count, the aggregation
level, the suppressed fields and cells, the transformation chain and the
smallest reported cell, and surfaces concerns such as an individual-level report
or a cell below 5.

Policy rules can then constrain minimization quantitatively, so a request with
12 source records against a minimum of 50 is refused by the specification rather
than by a reviewer's attention.

## Disclosure accounting, and what it is not

`DisclosureLedger` records what has been released over a source population, at
what aggregation level, for which purposes, and flags conditions a reviewer
should see: repeated release including individual level, several distinct
purposes over 1 population, and differing record counts between releases that
may permit differencing.

**It is deliberately not called a privacy budget.** A budget in the formal sense
accounts for an epsilon spent by mechanisms adding calibrated noise, and yields
a proof about worst-case adversarial information gain. This platform adds no
such noise, so there is no epsilon to spend and no bound to derive. Publishing a
figure called a privacy budget with nothing behind it would be precisely the
failure mode the rest of this architecture exists to prevent: a formal-sounding
number that does not carry the guarantee its name implies.

If formal accounting is wanted, the route is to add differentially private
mechanisms at the aggregation step and account for epsilon there. The ledger
would then record real budget draws instead of release events. Until that
happens, the honest artifact is an audit ledger, and it says so in its own
output.

## Signing at the release layer

The release model ended at "signed integrity manifest" while the portfolio
manifest carried hashes only. Hashes establish that files have not changed since
the manifest was written. They do not establish who wrote it, and anyone able to
modify a file can recompute the manifest.

`tools/sign_portfolio.py` signs the canonical manifest bytes with a managed key
held outside the tree, and `verify_portfolio.py` checks that signature **before**
it checks any hash, because verifying hashes against an unauthenticated manifest
establishes only internal consistency. An unsigned release now fails by default.

The scheme is HMAC-SHA256 with a managed key, matching the managed signing key
the release model already requires for controlled bundles. It authenticates a
release to a holder of the same key. Third-party verification would need a
detached public-key signature, and the signature block is shaped to take one
without a format change. That limit is stated rather than glossed.
