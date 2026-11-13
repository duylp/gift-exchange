"""Secret Santa matching.

Rules: nobody gives to themselves, no reciprocal pairs (A→B and B→A), and no pair that
is excluded (exclusions are two-way: "A ✕ B" forbids both A→B and B→A).

Algorithm: shuffle until valid (rejection sampling). Every valid assignment is equally
likely. Before shuffling, a cheap feasibility check catches setups that can never work.

People are any hashable IDs (e.g. participant row IDs); the UI maps them to names.

Modules: `feasibility` (allowed partners, up-front check) and `assignment`
(find_matching, validity check, loops).
"""

from gift_exchange.core.matching.assignment import (
    MAX_ATTEMPTS,
    MatchingError,
    find_matching,
    is_valid,
    loops,
)
from gift_exchange.core.matching.feasibility import (
    Feasibility,
    Verdict,
    allowed_partners,
    check_feasibility,
)

__all__ = [
    "MAX_ATTEMPTS",
    "Feasibility",
    "MatchingError",
    "Verdict",
    "allowed_partners",
    "check_feasibility",
    "find_matching",
    "is_valid",
    "loops",
]
