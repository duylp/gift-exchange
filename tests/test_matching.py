import random
from collections import Counter

import pytest

from gift_exchange.core.matching import (
    MatchingError,
    Verdict,
    allowed_partners,
    check_feasibility,
    find_matching,
    is_valid,
    loops,
)


def couples(n_couples: int) -> list[tuple[int, int]]:
    return [(2 * k, 2 * k + 1) for k in range(n_couples)]


def assert_valid(people, exclusions, assignment) -> None:
    assert sorted(assignment) == sorted(people)
    assert sorted(assignment.values()) == sorted(people)
    for giver, giftee in assignment.items():
        assert giver != giftee
        assert assignment[giftee] != giver
        assert (giver, giftee) not in exclusions and (giftee, giver) not in exclusions


# --- the rules always hold ---------------------------------------------------------


@pytest.mark.parametrize("n", range(3, 21))
@pytest.mark.parametrize("n_couples", [0, 1, 3])
def test_matching_obeys_rules(n: int, n_couples: int) -> None:
    if 2 * n_couples > n or (n == 3 and n_couples):
        pytest.skip("not a valid setup")
    people = list(range(n))
    excl = couples(n_couples)
    for seed in range(20):
        assert_valid(people, excl, find_matching(people, excl, random.Random(seed)))


def test_works_with_any_hashable_ids() -> None:
    people = ["alice", "bob", "cara", "dan"]
    m = find_matching(people, [("alice", "bob")], random.Random(0))
    assert_valid(people, [("alice", "bob")], m)


def test_default_rng_works() -> None:
    assert_valid(list(range(6)), [], find_matching(list(range(6))))


def test_same_seed_same_result() -> None:
    people = list(range(10))
    a = find_matching(people, couples(2), random.Random(42))
    b = find_matching(people, couples(2), random.Random(42))
    assert a == b


# --- fairness --------------------------------------------------------------------


def test_every_valid_assignment_equally_likely() -> None:
    # 5 people, one couple: 12 valid assignments (counted exhaustively).
    people, excl = list(range(5)), couples(1)
    rng = random.Random(1)
    n = 24_000
    counts = Counter(tuple(find_matching(people, excl, rng).values()) for _ in range(n))
    assert len(counts) == 12
    expected = n / 12
    chi2 = sum((c - expected) ** 2 / expected for c in counts.values())
    assert chi2 < 35  # df=11; p < 0.001 for a fair sampler. Seeded, so not flaky.


# --- feasibility -------------------------------------------------------------------


@pytest.mark.parametrize("n", [0, 1, 2])
def test_fewer_than_three_people_is_impossible(n: int) -> None:
    people = list(range(n))
    assert check_feasibility(people, []).verdict is Verdict.IMPOSSIBLE
    with pytest.raises(MatchingError, match="at least 3"):
        find_matching(people)


def test_three_people_with_a_couple_is_impossible() -> None:
    feas = check_feasibility([0, 1, 2], [(0, 1)])
    assert feas.verdict is Verdict.IMPOSSIBLE
    assert set(feas.stuck) == {0, 1}
    with pytest.raises(MatchingError) as exc:
        find_matching([0, 1, 2], [(0, 1)])
    assert set(exc.value.people) == {0, 1}


def test_person_excluded_from_almost_everyone_is_named() -> None:
    people = list(range(6))
    excl = [(0, 1), (0, 2), (0, 3), (0, 4)]  # 0 may only pair with 5
    feas = check_feasibility(people, excl)
    assert feas.verdict is Verdict.IMPOSSIBLE
    assert feas.stuck == (0,)
    with pytest.raises(MatchingError) as exc:
        find_matching(people, excl)
    assert exc.value.people == (0,)


@pytest.mark.parametrize("n", range(4, 31))
def test_couples_only_is_always_guaranteed(n: int) -> None:
    assert check_feasibility(list(range(n)), couples(n // 2)).verdict is Verdict.GUARANTEED


def test_tight_but_possible_is_uncertain_and_still_solved() -> None:
    # 6 people; 0 is excluded from 1, 2, 3 -> only 2 allowed partners (< n/2 = 3).
    people, excl = list(range(6)), [(0, 1), (0, 2), (0, 3)]
    assert check_feasibility(people, excl).verdict is Verdict.UNCERTAIN
    assert_valid(people, excl, find_matching(people, excl, random.Random(0)))


def test_hidden_impossible_case_fails_after_attempts() -> None:
    # Groups {0,1} and {2,3,4}; everyone excluded from their own group. Everyone has
    # >= 2 allowed partners, but the allowed graph is bipartite with an odd number of
    # people, so no set of loops can cover everyone.
    people = list(range(5))
    excl = [(0, 1), (2, 3), (2, 4), (3, 4)]
    assert check_feasibility(people, excl).verdict is Verdict.UNCERTAIN
    with pytest.raises(MatchingError, match="probably"):
        find_matching(people, excl, random.Random(0), max_attempts=2_000)


# --- input validation -------------------------------------------------------------


def test_duplicate_people_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        find_matching([1, 2, 2, 3])


def test_unknown_person_in_exclusion_rejected() -> None:
    with pytest.raises(ValueError, match="not in the event"):
        find_matching([1, 2, 3, 4], [(1, 99)])


def test_self_exclusion_rejected() -> None:
    with pytest.raises(ValueError, match="themselves"):
        find_matching([1, 2, 3, 4], [(1, 1)])


# --- helpers ----------------------------------------------------------------------


def test_is_valid_rejects_reciprocal_pair() -> None:
    allowed = allowed_partners([0, 1, 2, 3], [])
    assert not is_valid({0: 1, 1: 0, 2: 3, 3: 2}, allowed)
    assert is_valid({0: 1, 1: 2, 2: 3, 3: 0}, allowed)


def test_loops_split_assignment() -> None:
    assignment = {"a": "b", "b": "c", "c": "a", "d": "e", "e": "f", "f": "g", "g": "d"}
    assert loops(assignment) == [["a", "b", "c"], ["d", "e", "f", "g"]]


def test_loops_of_real_matching_cover_everyone_and_have_length_at_least_3() -> None:
    people = list(range(12))
    result = loops(find_matching(people, couples(3), random.Random(5)))
    assert sorted(p for loop in result for p in loop) == people
    assert all(len(loop) >= 3 for loop in result)
