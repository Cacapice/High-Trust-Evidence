"""Compatibility alias for `high_trust_evidence`.

The platform outgrew the name `qualification-contract`: it now carries release
policy, minimization metrics, disclosure accounting, figure governance and the
release signer, not only the publication contract. The package was renamed and
this alias kept, so the 4 dependent repositories do not need a coordinated
import change to adopt the split.

Deprecated. New code should import `high_trust_evidence`.
"""
import warnings as _warnings

from high_trust_evidence import *  # noqa: F401,F403
from high_trust_evidence import __all__, __version__  # noqa: F401
from high_trust_evidence.sovereign import *  # noqa: F401,F403

_warnings.warn(
    "qualification_contract is an alias for high_trust_evidence and will be "
    "removed in 2.0; update the import",
    DeprecationWarning,
    stacklevel=2,
)
