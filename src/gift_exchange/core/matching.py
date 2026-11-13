"""Secret Santa matching.

Rules: nobody gives to themselves, no reciprocal pairs (A→B and B→A), and no pair that
is excluded (exclusions are two-way: "A ✕ B" forbids both A→B and B→A).

Algorithm: shuffle until valid (rejection sampling). Every valid assignment is equally
likely. Before shuffling, a cheap feasibility check catches setups that can never work.

People are any hashable IDs (e.g. participant row IDs); the UI maps them to names.
"""

import random
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

MAX_ATTEMPTS = 10_000


class MatchingError(ValueError):
    """No valid assignment could be made. `people` are the ones to look at, if known."""

    def __init__(self, message: str, people: Sequence[Hashable] = ()) -> None:
        super().__init__(message)
        self.people = tuple(people)


class Verdict(Enum):
    IMPOSSIBLE = "impossible"  # provably no valid assignment
    GUARANTEED = "guaranteed"  # provably at least one valid assignment
    UNCERTAIN = "uncertain"  # neither check applies; shuffling will tell


@dataclass(frozen=True)
class Feasibility:
    verdict: Verdict
    stuck: tuple[Hashable, ...] = ()  # people with fewer than 2 allowed partners


def allowed_partners(
    people: Sequence[Hashable], exclusions: Iterable[tuple[Hashable, Hashable]]
) -> dict[Hashable, set[Hashable]]:
    """For each person, the others they may be matched with (in either direction)."""
    exclusions = list(exclusions)
    _validate(people, exclusions)
    allowed = {p: set(people) - {p} for p in people}
    for a, b in exclusions:
        allowed[a].discard(b)
        allowed[b].discard(a)
    return allowed


def check_feasibility(
    people: Sequence[Hashable], exclusions: Iterable[tuple[Hashable, Hashable]]
) -> Feasibility:
    """Cheap up-front check; safe to call on every admin-page change.

    - Impossible: someone has < 2 allowed partners. With no reciprocal pairs, your giftee
      and your Santa must be two different allowed people.
    - Guaranteed: everyone is allowed with >= n/2 others (n >= 3). By Dirac's theorem the
      "allowed" graph then has a cycle through everyone, which is a valid assignment.
    """
    allowed = allowed_partners(people, exclusions)
    n = len(people)
    stuck = tuple(p for p in people if len(allowed[p]) < 2)
    if n < 3 or stuck:
        return Feasibility(Verdict.IMPOSSIBLE, stuck)
    if all(2 * len(allowed[p]) >= n for p in people):
        return Feasibility(Verdict.GUARANTEED)
    return Feasibility(Verdict.UNCERTAIN)


def find_matching(
    people: Sequence[Hashable],
    exclusions: Iterable[tuple[Hashable, Hashable]] = (),
    rng: random.Random | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict[Hashable, Hashable]:
    """Return a uniformly random valid {giver: giftee} assignment, or raise MatchingError.

    Pass a seeded `rng` for reproducible results (tests only). The default is
    `random.SystemRandom`, which is unpredictable and has no seed to leak.
    """
    exclusions = list(exclusions)
    feasibility = check_feasibility(people, exclusions)
    if feasibility.verdict is Verdict.IMPOSSIBLE:
        if len(people) < 3:
            raise MatchingError("Need at least 3 people to make a matching.", people)
        raise MatchingError(
            "Impossible: these people have fewer than 2 allowed partners; "
            "remove an exclusion involving them.",
            feasibility.stuck,
        )

    rng = rng or random.SystemRandom()
    allowed = allowed_partners(people, exclusions)
    receivers = list(people)
    for _ in range(max_attempts):
        rng.shuffle(receivers)
        assignment = dict(zip(people, receivers))
        if is_valid(assignment, allowed):
            return assignment

    most_constrained = min(people, key=lambda p: len(allowed[p]))
    raise MatchingError(
        f"No valid matching found in {max_attempts} attempts; the exclusions are probably "
        "too tight. Try removing an exclusion involving the person shown.",
        [most_constrained],
    )


def is_valid(assignment: dict[Hashable, Hashable], allowed: dict[Hashable, set[Hashable]]) -> bool:
    """True if every giver gives to an allowed person and no pair is reciprocal."""
    return all(
        giftee in allowed[giver] and assignment[giftee] != giver
        for giver, giftee in assignment.items()
    )


def loops(assignment: dict[Hashable, Hashable]) -> list[list[Hashable]]:
    """Split an assignment into gift loops, e.g. [[A, B, C], [D, E, F, G]] for the reveal.

    Each loop is listed in giving order (A gives to B, ..., last gives to first), starting
    from whoever comes first in the assignment.
    """
    seen: set[Hashable] = set()
    result = []
    for start in assignment:
        if start in seen:
            continue
        loop = []
        person = start
        while person not in seen:
            seen.add(person)
            loop.append(person)
            person = assignment[person]
        result.append(loop)
    return result


def _validate(people: Sequence[Hashable], exclusions: list[tuple[Hashable, Hashable]]) -> None:
    if len(set(people)) != len(people):
        raise ValueError("Duplicate people in the list.")
    known = set(people)
    for a, b in exclusions:
        if a == b:
            raise ValueError(f"Exclusion pairs {a!r} with themselves.")
        if a not in known or b not in known:
            raise ValueError(f"Exclusion ({a!r}, {b!r}) mentions someone not in the event.")
