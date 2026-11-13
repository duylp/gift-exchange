import random
import sqlite3

import pytest
from sqlite_migrate import apply_migrations

from gift_exchange.core import db as q
from gift_exchange.core.matching import MatchingError, Verdict

QUESTIONS = ["Hobbies?", "Favourite colour?"]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = q.connect(":memory:")
    apply_migrations(c, q.MIGRATIONS_DIR)
    return c


@pytest.fixture
def event(conn: sqlite3.Connection) -> q.Event:
    return q.create_event(conn, "xmas-2026", "Xmas 2026", 30, QUESTIONS)


def signup(conn: sqlite3.Connection, event: q.Event, who: str) -> q.Participant:
    user = q.get_or_create_user(conn, f"{who}@example.com")
    return q.join_event(conn, event.id, user.id, who.title(), f"{who}-nick", ["a", "b"])


# --- users ------------------------------------------------------------------------------


def test_get_or_create_user_normalises_and_is_idempotent(conn: sqlite3.Connection) -> None:
    u1 = q.get_or_create_user(conn, "  Ann@Example.COM ")
    u2 = q.get_or_create_user(conn, "ann@example.com")
    assert u1 == u2 and u1.email == "ann@example.com" and u1.name is None
    assert q.get_user(conn, u1.id) == u1


def test_invalid_email(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        q.get_or_create_user(conn, "not-an-email")


def test_get_user_missing(conn: sqlite3.Connection) -> None:
    with pytest.raises(q.NotFound):
        q.get_user(conn, 999)


# --- events -----------------------------------------------------------------------------


def test_create_and_get_event(conn: sqlite3.Connection) -> None:
    e = q.create_event(conn, "xmas-2026", " Xmas ", 30, [" Hobbies? ", "", "Colour?"])
    assert e.title == "Xmas" and e.questions == ("Hobbies?", "Colour?") and e.is_open
    assert q.get_event_by_slug(conn, "xmas-2026") == e
    assert q.list_events(conn) == [e]


def test_slug_taken(conn: sqlite3.Connection, event: q.Event) -> None:
    with pytest.raises(q.SlugTaken):
        q.create_event(conn, "xmas-2026", "Again", 30, [])


@pytest.mark.parametrize(
    ("slug", "title", "budget"), [("Bad Slug", "T", 30), ("ok", "", 30), ("ok", "T", 0)]
)
def test_invalid_event(conn: sqlite3.Connection, slug: str, title: str, budget: int) -> None:
    with pytest.raises(ValueError):
        q.create_event(conn, slug, title, budget, [])


def test_event_not_found(conn: sqlite3.Connection) -> None:
    with pytest.raises(q.NotFound):
        q.get_event_by_slug(conn, "nope")
    with pytest.raises(q.NotFound):
        q.update_event(conn, 999, "T", 30, [])


def test_update_event_questions_locked_after_signup(
    conn: sqlite3.Connection, event: q.Event
) -> None:
    q.update_event(conn, event.id, "New title", 40, ["Only one?", "Two?"])
    signup(conn, event, "ann")
    # Same questions + other changes: fine.
    e = q.update_event(conn, event.id, "Newer", 50, ["Only one?", "Two?"])
    assert (e.title, e.budget) == ("Newer", 50)
    with pytest.raises(q.QuestionsLocked):
        q.update_event(conn, event.id, "Newer", 50, ["Changed?", "Two?"])


# --- sign-ups --------------------------------------------------------------------------


def test_join_sets_user_name_and_returns_participant(
    conn: sqlite3.Connection, event: q.Event
) -> None:
    user = q.get_or_create_user(conn, "ann@example.com")
    p = q.join_event(conn, event.id, user.id, " Ann Tan ", " Rudolph ", [" ski ", "red"])
    assert (p.name, p.nickname, p.answers, p.email) == (
        "Ann Tan",
        "Rudolph",
        ("ski", "red"),
        "ann@example.com",
    )
    assert q.get_user(conn, user.id).name == "Ann Tan"
    assert q.get_participant(conn, event.id, user.id) == p


def test_join_errors(conn: sqlite3.Connection, event: q.Event) -> None:
    ann = signup(conn, event, "ann")
    bob = q.get_or_create_user(conn, "bob@example.com")
    with pytest.raises(q.AlreadyJoined):
        q.join_event(conn, event.id, ann.user_id, "Ann", "other", ["a", "b"])
    with pytest.raises(q.NicknameTaken):
        q.join_event(conn, event.id, bob.id, "Bob", "ANN-NICK", ["a", "b"])
    with pytest.raises(ValueError, match="answers"):
        q.join_event(conn, event.id, bob.id, "Bob", "bob", ["only one"])
    with pytest.raises(ValueError, match="name"):
        q.join_event(conn, event.id, bob.id, "  ", "bob", ["a", "b"])
    # Failed joins changed nothing.
    assert q.get_user(conn, bob.id).name is None
    assert len(q.list_participants(conn, event.id)) == 1


def test_update_signup(conn: sqlite3.Connection, event: q.Event) -> None:
    ann = signup(conn, event, "ann")
    p = q.update_signup(conn, event.id, ann.user_id, "Ann T", "Comet", ["x", "y"])
    assert (p.name, p.nickname, p.answers) == ("Ann T", "Comet", ("x", "y"))
    stranger = q.get_or_create_user(conn, "zed@example.com")
    with pytest.raises(q.NotFound):
        q.update_signup(conn, event.id, stranger.id, "Zed", "zed", ["a", "b"])
    assert q.get_user(conn, stranger.id).name is None  # rolled back


def test_remove_participant(conn: sqlite3.Connection, event: q.Event) -> None:
    ann, bob = signup(conn, event, "ann"), signup(conn, event, "bob")
    q.add_exclusion(conn, event.id, ann.id, bob.id)
    q.remove_participant(conn, ann.id)
    assert [p.id for p in q.list_participants(conn, event.id)] == [bob.id]
    assert q.list_exclusions(conn, event.id) == []


# --- exclusions -------------------------------------------------------------------------


def test_exclusions_are_unordered_and_idempotent(conn: sqlite3.Connection, event: q.Event) -> None:
    ann, bob = signup(conn, event, "ann"), signup(conn, event, "bob")
    q.add_exclusion(conn, event.id, bob.id, ann.id)
    q.add_exclusion(conn, event.id, ann.id, bob.id)
    assert q.list_exclusions(conn, event.id) == [(ann.id, bob.id)]
    q.remove_exclusion(conn, event.id, bob.id, ann.id)
    assert q.list_exclusions(conn, event.id) == []


def test_exclusion_errors(conn: sqlite3.Connection, event: q.Event) -> None:
    ann = signup(conn, event, "ann")
    with pytest.raises(ValueError, match="different"):
        q.add_exclusion(conn, event.id, ann.id, ann.id)
    other = q.create_event(conn, "other", "Other", 10, ["a?", "b?"])
    zed = signup(conn, other, "zed")
    with pytest.raises(ValueError, match="this event"):
        q.add_exclusion(conn, event.id, ann.id, zed.id)


# --- matching ---------------------------------------------------------------------------


def test_feasibility(conn: sqlite3.Connection, event: q.Event) -> None:
    a, b, _ = (signup(conn, event, n) for n in ("ann", "bob", "cat"))
    assert q.event_feasibility(conn, event.id).verdict is Verdict.GUARANTEED
    q.add_exclusion(conn, event.id, a.id, b.id)
    feas = q.event_feasibility(conn, event.id)
    assert feas.verdict is Verdict.IMPOSSIBLE and set(feas.stuck) == {a.id, b.id}


def test_full_flow(conn: sqlite3.Connection, event: q.Event) -> None:
    people = [signup(conn, event, n) for n in ("ann", "bob", "cat", "dan", "eve", "fay")]
    q.add_exclusion(conn, event.id, people[0].id, people[1].id)

    assert q.get_giftee(conn, event.id, people[0].user_id) is None  # not matched yet
    assert q.run_matching(conn, event.id, random.Random(1)) == 6

    event = q.get_event(conn, event.id)
    assert event.status == "matched" and event.matched_at
    nicknames = {p.nickname for p in people}
    received = []
    for p in people:
        g = q.get_giftee(conn, event.id, p.user_id)
        assert g is not None and g.nickname != p.nickname and g.budget == 30
        assert g.clues == (("Hobbies?", "a"), ("Favourite colour?", "b"))
        received.append(g.nickname)
    assert sorted(received) == sorted(nicknames)  # everyone receives exactly once
    # The excluded pair never gives to each other.
    assert q.get_giftee(conn, event.id, people[0].user_id).nickname != people[1].nickname
    assert q.get_giftee(conn, event.id, people[1].user_id).nickname != people[0].nickname


def test_after_matching_everything_is_closed(conn: sqlite3.Connection, event: q.Event) -> None:
    a, b, _ = (signup(conn, event, n) for n in ("ann", "bob", "cat"))
    q.run_matching(conn, event.id)
    with pytest.raises(q.EventClosed):
        q.run_matching(conn, event.id)
    with pytest.raises(q.EventClosed):
        signup(conn, event, "late")
    with pytest.raises(q.EventClosed):
        q.update_signup(conn, event.id, a.user_id, "Ann", "new", ["a", "b"])
    with pytest.raises(q.EventClosed):
        q.remove_participant(conn, a.id)
    with pytest.raises(q.EventClosed):
        q.add_exclusion(conn, event.id, a.id, b.id)
    with pytest.raises(q.EventClosed):
        q.remove_exclusion(conn, event.id, a.id, b.id)


def test_impossible_matching_saves_nothing(conn: sqlite3.Connection, event: q.Event) -> None:
    a, b, _ = (signup(conn, event, n) for n in ("ann", "bob", "cat"))
    q.add_exclusion(conn, event.id, a.id, b.id)
    with pytest.raises(MatchingError) as exc:
        q.run_matching(conn, event.id)
    assert set(exc.value.people) == {a.id, b.id}
    assert q.get_event(conn, event.id).is_open
    assert conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0
    assert not conn.in_transaction


def test_get_giftee_for_non_participant_is_none(conn: sqlite3.Connection, event: q.Event) -> None:
    for n in ("ann", "bob", "cat"):
        signup(conn, event, n)
    q.run_matching(conn, event.id)
    outsider = q.get_or_create_user(conn, "out@example.com")
    assert q.get_giftee(conn, event.id, outsider.id) is None


def test_only_get_giftee_reads_matches() -> None:
    # Secrecy guard: no query in the db package except get_giftee may read the matches table.
    import re
    from pathlib import Path

    readers = []
    for path in sorted(Path(q.__file__).parent.glob("*.py")):
        for line in path.read_text().splitlines():
            if re.search(r"\b(FROM|JOIN)\s+matches\b", line):
                readers.append((path.name, line.strip()))
    assert readers == [("matches.py", "JOIN matches AS m ON m.giver_id = me.id")]
