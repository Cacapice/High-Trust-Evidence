# High-Trust Evidence Platform

**Research software should separate 3 things that are usually tangled:**

- **scientific validity** — is the finding sound?
- **epistemic qualification** — what may be claimed from it?
- **publication authority** — who may release it, to whom, for what purpose?

This package provides the second and third as services. Research repositories
supply domain evidence. The platform supplies publication discipline.

The separation is not tidiness. Tangled, a release decision can quietly change a
scientific conclusion: a result gets called "qualified" because it is awkward to
release, or "publishable" because someone needs it to be. Separated, privacy and
authority sit *downstream* of qualification and cannot reach back into it.

## What problem this solves

A result carries a claim. Somewhere between the analysis and the reader, that
claim usually stops being checkable:

- a status field is set by whichever branch of an adapter happened to run
- a caveat is recorded next to the claim without weakening it
- a figure asserts a finding its caption does not support
- a bundle is emitted with no record of who authorised it or on what basis
- a manifest establishes that files are unchanged, but not who wrote them

Each of those is a place where a claim outruns its warrant. The platform closes
them by making the warrant computable and, where it cannot be computed, by
refusing rather than degrading.

## How it works

```text
        Research repository
                │           domain evidence, native result objects
                ▼
        ScientificResult
                │           a claim with its estimand, uncertainty and evidence graph
                ▼
        Adapter obligations
                │           did the adapter emit every qualification it owed?
                ▼
        Qualification algebra
                │           status derived from qualifications, never asserted
                ▼
        Trust decision
                │           classification, purpose, minimization, authority
                ▼
        Publication bundle
                            canonical bytes, hashed manifest, signature
```

Each arrow is a gate that can refuse. Nothing passes by default.

## The 5 services

**Qualification algebra.** A monotone transition system over publication status.
A qualification is a transition on epistemic strength, not an annotation beside
it. Without explicit new evidence, applying a qualification can never raise
strength. Status is derived from the base and the qualifications; an adapter
cannot assert its way to a stronger claim.

**Adapter obligations.** Domain-specific requirements that fail closed. A
repository declares which native fields must be present, how many structured
qualifications are owed, which qualifications must appear when a condition
holds, and what status ceiling each condition imposes. Derivation catches an
adapter that mis-folds its qualifications; obligations catch one that omits a
qualification it owed. Neither catches the other, so the platform runs both.

**Sovereign release.** Purpose boundaries, direct-identifier refusal,
aggregate-only enforcement, residual disclosure risk, and named approvals. An
envelope carrying raw records is refused at construction, not at policy time,
because a type error cannot be overridden by an authorised person.

**Declarative policy.** Release rules live in a file rather than in branches, so
they can be diffed and reviewed by someone who does not read Python. A
classification the policy does not name is refused rather than defaulted.

**Figure governance.** A figure is an inferential claim rendered as an image, and
carries the same contract: question, observation, interpretation, inference
status, provenance, lifecycle, and a publication gate that refuses.

## Using it

    pip install high-trust-evidence

A research repository contributes exactly 1 thing: an **adapter** translating its
native result into a `ScientificResult`, plus the obligations it owes.

```python
from high_trust_evidence import (
    ScientificResult, Qualification, assert_adapter_result,
)

def from_my_result(native) -> ScientificResult:
    result = ScientificResult(
        repository="My Repository",
        estimand="what was estimated",
        estimate=native.value,
        estimate_kind="point_estimate",
        base_publication_status="publishable",
        publication_status="publishable",   # an expectation; see below
        qualifications=(
            Qualification(kind="finite_sample", effect="weaken",
                          rationale="the estimate is a finite-draw approximation"),
        ),
        native_payload=native.to_dict(),
    )
    return assert_adapter_result(result, MY_ADAPTER_POLICY)
```

The adapter stays in the research repository because it encodes domain knowledge
about what a native result *means*. The platform should never need to know what
a Fiedler value or an identifiability gate is.

## On `publication_status`, honestly

The `publication_status` argument is an **expectation, not a setting**.
`__post_init__` derives the status from `base_publication_status` and the
qualifications, and the derived value is authoritative. Whatever the adapter
passes is replaced.

Where the expectation and the derivation disagree, the derivation still wins and
the disagreement is recorded as `status_expectation_mismatch` and serialized
into the payload. An adapter that passes the base as its status, which is what
all current adapters do, is read as declaring no expectation and is not flagged.

This was not always so. The argument used to be discarded in silence, which made
agreement and disagreement indistinguishable and let an adapter drift from its
own stated intent unnoticed. The derived status was already authoritative then
too. What changed is that a disagreement is now visible instead of being
resolved quietly.

## What this platform does not do

It does not do domain science, and it does not know any. It does not add
differentially private noise, so `DisclosureLedger` is an audit record and not a
privacy budget, and it says so in its own output. Its release signature is
HMAC with a managed key, which authenticates a release to a holder of that key
and does not support third-party verification; a detached public-key signature
would, and the signature block is shaped to take one.

Each of those limits is stated in the code that has it, not only here.

## Documentation

| Document | For |
|---|---|
| [`docs/framework/QUALIFICATION_ALGEBRA.md`](docs/framework/QUALIFICATION_ALGEBRA.md) | the formal object, its invariant, and why strengthening is isolated |
| [`docs/framework/ADAPTER_DISCIPLINE.md`](docs/framework/ADAPTER_DISCIPLINE.md) | what a research repository owes |
| [`docs/framework/POLICY_MIGRATION.md`](docs/framework/POLICY_MIGRATION.md) | changing a policy version and re-evaluating under it |
| [`docs/architecture/HIGH_TRUST_EVIDENCE_ARCHITECTURE.md`](docs/architecture/HIGH_TRUST_EVIDENCE_ARCHITECTURE.md) | trust boundaries, where raw data may exist, where signatures become mandatory |
| [`docs/architecture/SOVEREIGN_RELEASE_MODEL.md`](docs/architecture/SOVEREIGN_RELEASE_MODEL.md) | the controlled-release chain |

## Dependents

| Repository | Adapter | Obligation policy |
|---|---|---|
| [Inferential Fidelity Framework](https://github.com/Cacapice/Inferential-Fidelity-Framework) | `from_restricted_modulus_result` | `IFF_ADAPTER_POLICY` |
| [Benchmark Stewardship](https://github.com/Cacapice/Benchmark-Stewardship_NOHARM_MAST) | `from_evidence_profile` | `BENCHMARK_ADAPTER_POLICY` |
| [Bayesian Inferential Fidelity](https://github.com/Cacapice/Bayesian-Inferential-Fidelity) | `from_fidelity_summary` | `BAYESIAN_ADAPTER_POLICY` |
| [Maritime Intent Probe](https://github.com/Cacapice/Maritime-Intent-Probe) | `from_bc1_report` | `MARITIME_PHASE1_ADAPTER_POLICY` |

The platform is generic. The obligations are not: each policy is written by the
repository that knows what its own evidence owes.

## Compatibility

`import qualification_contract` still resolves and emits a `DeprecationWarning`.
The name understated the scope once release policy, minimization metrics,
disclosure accounting, figure governance and the release signer joined the
publication contract. The alias goes in 2.0.

## Licence

AGPL-3.0-only.
