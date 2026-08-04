"""Status is derived, and the adapter's stated expectation is verified against it.

The derivation already existed: `__post_init__` computes `publication_status`
from the base status and the qualifications, so an adapter cannot assert a
status the algebra does not support.

What did not exist was verification. The adapter's `publication_status`
argument was silently discarded, so an adapter writing "publishable" and
receiving "qualified" produced no signal. Silent agreement and silent
disagreement were indistinguishable, which meant an adapter could drift from
its own stated intent with nothing to notice.
"""
import pytest

from high_trust_evidence import EPISTEMIC_STRENGTH, Qualification, ScientificResult

WEAKEN = Qualification(kind="monte_carlo", effect="weaken")
BLOCK = Qualification(kind="identifiability", effect="block")


def _r(asserted, base, quals=()):
    return ScientificResult(
        repository="r", estimand="e", estimate=1.0, estimate_kind="exact",
        publication_status=asserted, base_publication_status=base,
        qualifications=quals)


def test_status_is_derived_not_taken_from_the_argument():
    r = _r("publishable", "publishable", (WEAKEN,))
    assert r.publication_status == "qualified"


def test_placeholder_expectation_is_not_a_mismatch():
    """All 4 shipped adapters pass base as the status; that means 'no expectation'."""
    assert _r("publishable", "publishable", (WEAKEN,)).status_expectation_mismatch is None


def test_genuine_disagreement_is_recorded():
    r = _r("exploratory", "publishable", (WEAKEN,))
    assert r.publication_status == "qualified"
    assert r.status_expectation_mismatch
    assert "expected 'exploratory'" in r.status_expectation_mismatch
    assert "derived 'qualified'" in r.status_expectation_mismatch


def test_an_adapter_expecting_too_strong_a_status_is_flagged():
    r = _r("publishable", "qualified", (WEAKEN,))
    assert EPISTEMIC_STRENGTH[r.publication_status] < EPISTEMIC_STRENGTH["publishable"]
    assert r.status_expectation_mismatch


def test_blocking_qualification_overrides_any_expectation_and_flags_it():
    r = _r("qualified", "publishable", (BLOCK,))
    assert r.publication_status == "blocked"
    assert r.status_expectation_mismatch


def test_agreement_leaves_no_mismatch():
    assert _r("publishable", "publishable").status_expectation_mismatch is None


def test_mismatch_is_serialized_so_a_reader_sees_it():
    d = _r("exploratory", "publishable", (WEAKEN,)).to_dict()
    assert d["status_expectation_mismatch"]
    assert d["publication_status"] == "qualified"


def test_shipped_adapters_do_not_currently_disagree():
    """A regression guard: today every adapter agrees, so any flag is new drift."""
    for base, quals in (("publishable", ()), ("publishable", (WEAKEN,)),
                        ("publishable", (WEAKEN, WEAKEN))):
        assert _r(base, base, quals).status_expectation_mismatch is None
