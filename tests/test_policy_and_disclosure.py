"""Release policy, minimization metrics, and disclosure accounting."""
import pytest

from high_trust_evidence import (
    DisclosureLedger, MinimizationRecord, ReleasePolicy,
)

SPEC = {
    "version": "1.0",
    "release": {
        "unrestricted": {"signature": "optional", "external_release": "permitted"},
        "owner_data": {
            "signature": "required", "external_release": "prohibited",
            "max_aggregation_level": "group", "min_source_records": 50,
            "forbid_purposes": ("marketing",),
        },
    },
}


@pytest.fixture
def policy():
    return ReleasePolicy.from_mapping(SPEC)


@pytest.fixture
def minimal():
    return MinimizationRecord(
        source_record_count=120, aggregation_level="group",
        suppressed_fields=("mmsi",), suppressed_cells=14,
        transformation_chain=("drop identifiers", "bin", "aggregate"),
        smallest_reported_cell=11)


def test_signed_internal_owner_data_is_permitted(policy, minimal):
    assert policy.evaluate(classification="owner_data", purpose="research",
                           signed=True, minimization=minimal).allowed


def test_unsigned_owner_data_is_refused(policy, minimal):
    d = policy.evaluate(classification="owner_data", purpose="research",
                        signed=False, minimization=minimal)
    assert not d.allowed and any("signature required" in v for v in d.violations)


def test_external_release_is_refused(policy, minimal):
    d = policy.evaluate(classification="owner_data", purpose="research",
                        signed=True, external=True, minimization=minimal)
    assert any("external release prohibited" in v for v in d.violations)


def test_forbidden_purpose_is_refused(policy, minimal):
    d = policy.evaluate(classification="owner_data", purpose="marketing",
                        signed=True, minimization=minimal)
    assert not d.allowed


def test_unknown_classification_is_refused_not_defaulted(policy, minimal):
    """A policy that does not cover a request has not permitted it."""
    d = policy.evaluate(classification="public", purpose="research",
                        signed=True, minimization=minimal)
    assert not d.allowed and any("no rule for classification" in v for v in d.violations)


def test_sub_minimum_record_count_is_refused(policy):
    m = MinimizationRecord(source_record_count=12, aggregation_level="group",
                           transformation_chain=("bin",))
    d = policy.evaluate(classification="owner_data", purpose="research",
                        signed=True, minimization=m)
    assert any("below the minimum" in v for v in d.violations)


def test_individual_aggregation_is_refused(policy):
    m = MinimizationRecord(source_record_count=120, aggregation_level="individual",
                           transformation_chain=("none",))
    d = policy.evaluate(classification="owner_data", purpose="research",
                        signed=True, minimization=m)
    assert any("individual-level aggregation" in v for v in d.violations)


def test_decision_names_the_policy_it_applied(policy, minimal):
    d = policy.evaluate(classification="owner_data", purpose="research",
                        signed=True, minimization=minimal)
    assert d.policy_version == "1.0" and len(d.policy_digest) == 64


def test_minimization_surfaces_concerns_without_scoring_them():
    m = MinimizationRecord(source_record_count=120, aggregation_level="group",
                           transformation_chain=(), smallest_reported_cell=3)
    assert "smallest reported cell is 3" in m.concerns
    assert "no transformation chain recorded" in m.concerns


def test_ledger_is_not_a_privacy_budget_and_says_so():
    """The distinction is load-bearing: no noise is added, so no epsilon is spent."""
    led = DisclosureLedger()
    for n, level, purpose in ((120, "group", "research"), (118, "group", "research"),
                              (120, "individual", "operations")):
        led.record(release_id=f"r{n}{level}", purpose=purpose, classification="owner_data",
                   source_population="fleet-A",
                   minimization=MinimizationRecord(n, level, transformation_chain=("agg",)))
    s = led.population_summary("fleet-A")
    assert s["accounting_kind"] == "audit_ledger"
    assert "no epsilon is spent" in s["not_a_privacy_budget"]
    assert s["release_count"] == 3


def test_ledger_flags_differencing_risk():
    led = DisclosureLedger()
    for n in (120, 118):
        led.record(release_id=f"r{n}", purpose="research", classification="owner_data",
                   source_population="fleet-A",
                   minimization=MinimizationRecord(n, "group", transformation_chain=("agg",)))
    flags = led.population_summary("fleet-A")["review_flags"]
    assert any("differencing" in f for f in flags)
