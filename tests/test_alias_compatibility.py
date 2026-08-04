"""The deprecation alias must work and must warn.

The 4 dependent repositories adopt the rename on their own schedule. The alias
is what makes that possible, and the warning is the migration signal. Both are
tested, because an alias that silently works is one nobody migrates off, and an
alias that breaks is a coordinated change across 4 repositories.
"""
import importlib
import warnings


def test_alias_resolves_to_the_same_types():
    import high_trust_evidence as new
    import qualification_contract as old
    assert old.ScientificResult is new.ScientificResult
    assert old.Qualification is new.Qualification
    assert old.__version__ == new.__version__


def test_alias_emits_a_deprecation_warning():
    import sys
    for mod in [m for m in sys.modules if m.startswith("qualification_contract")]:
        del sys.modules[mod]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("qualification_contract")
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_sovereign_submodule_is_aliased_too():
    from qualification_contract.sovereign import SovereignEvidenceEnvelope as old
    from high_trust_evidence.sovereign import SovereignEvidenceEnvelope as new
    assert old is new
