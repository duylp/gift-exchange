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
    """No valid assignment could be made.

    Args:
        message: Human-readable reason, suitable to show the organiser.
        people: The people causing the problem (e.g. those with too few allowed
            partners), so the UI can name them. Empty if no one in particular.

    Attributes:
        people: Same as the `people` argument, as a tuple.
    """

    def __init__(self, message: str, people: Sequence[Hashable] = ()) -> None:
        super().__init__(message)
        self.people = tuple(people)


class Verdict(Enum):
    """Outcome of `check_feasibility`."""

    IMPOSSIBLE = "impossible"  # provably no valid assignment
    GUARANTEED = "guaranteed"  # provably at least one valid assignment
    UNCERTAIN = "uncertain"  # neither check applies; shuffling will tell


@dataclass(frozen=True)
class Feasibility:
    """Result of `check_feasibility`.

    Attributes:
        verdict: Whether a valid assignment is impossible, guaranteed, or uncertain.
        stuck: People with fewer than 2 allowed partners (only set when the verdict is
            IMPOSSIBLE because of them; empty otherwise).
    """

    verdict: Verdict
    stuck: tuple[Hashable, ...] = ()


def allowed_partners(
    people: Sequence[Hashable], exclusions: Iterable[tuple[Hashable, Hashable]]
) -> dict[Hashable, set[Hashable]]:
    """For each person, the others they may be matched with (in either direction).

    Args:
        people: Everyone in the event, as unique hashable IDs.
        exclusions: Pairs (a, b) who must not be matched with each other in either
            direction, e.g. couples. Order within a pair does not matter.

    Returns:
        Mapping from each person to the set of people they may give to (and, since
        exclusions are two-way, receive from). Never includes the person themselves.

    Raises:
        ValueError: If `people` has duplicates, or an exclusion pairs someone with
            themselves or mentions someone not in `people`.
    """
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
    - Uncertain: neither applies; `find_matching` will either succeed or give up.

    Args:
        people: Everyone in the event, as unique hashable IDs.
        exclusions: Pairs who must not be matched with each other (two-way).

    Returns:
        A `Feasibility` with the verdict and, if impossible, the people who are stuck.

    Raises:
        ValueError: On invalid input (see `allowed_partners`).
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
    """Pick a uniformly random valid assignment of giftees.

    Args:
        people: Everyone in the event, as unique hashable IDs (e.g. participant row IDs).
        exclusions: Pairs who must not be matched with each other in either direction,
            e.g. couples. Defaults to none.
        rng: Random number generator used for shuffling. Pass a seeded
            `random.Random(seed)` for reproducible results — tests only. Defaults to
            `random.SystemRandom()`, which is unpredictable and has no seed that could
            leak the matches.
        max_attempts: How many shuffles to try before giving up. The default (10,000)
            is far more than any realistic group needs; lower it only in tests.

    Returns:
        A {giver: giftee} dict covering every person exactly once as giver and once as
        giftee, with no self-gifts, no reciprocal pairs and no excluded pairs. Keys are
        in the same order as `people`.

    Raises:
        MatchingError: If the setup is provably impossible (fewer than 3 people, or
            someone with fewer than 2 allowed partners), or no valid assignment was
            found within `max_attempts`. `.people` names who to look at.
        ValueError: On invalid input (see `allowed_partners`).
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
    """Check an assignment against the rules.

    Args:
        assignment: A {giver: giftee} dict. Assumed to be a full permutation of the
            people (every person appears once as a key and once as a value).
        allowed: Output of `allowed_partners` for the same people and exclusions.

    Returns:
        True if every giver gives to someone in their allowed set (which rules out
        self-gifts and excluded pairs) and no two people give to each other.
    """
    return all(
        giftee in allowed[giver] and assignment[giftee] != giver
        for giver, giftee in assignment.items()
    )


def loops(assignment: dict[Hashable, Hashable]) -> list[list[Hashable]]:
    """Split an assignment into gift loops for the chain-style reveal.

    Args:
        assignment: A {giver: giftee} dict that is a full permutation of the people,
            e.g. the result of `find_matching`.

    Returns:
        A list of loops, e.g. [[A, B, C], [D, E, F, G]]. Each loop is in giving order
        (A gives to B, B to C, and the last person gives back to the first). Loops are
        ordered by, and each starts from, whoever comes first in `assignment`.
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
