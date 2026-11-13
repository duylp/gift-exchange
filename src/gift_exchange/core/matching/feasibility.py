"""Rules input (people, two-way exclusions) and the cheap up-front feasibility check."""

from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum


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


def _validate(people: Sequence[Hashable], exclusions: list[tuple[Hashable, Hashable]]) -> None:
    if len(set(people)) != len(people):
        raise ValueError("Duplicate people in the list.")
    known = set(people)
    for a, b in exclusions:
        if a == b:
            raise ValueError(f"Exclusion pairs {a!r} with themselves.")
        if a not in known or b not in known:
            raise ValueError(f"Exclusion ({a!r}, {b!r}) mentions someone not in the event.")
