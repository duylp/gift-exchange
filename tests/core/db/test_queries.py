import random
import sqlite3

import pytest
from sqlite_migrate import apply_migrations

from gift_exchange.core import db as q
from gift_exchange.core.matching import MatchingError, Verdict

QUESTIONS = [q.Section("", ("Hobbies?", "Favourite colour?"))]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = q.connect(":memory:")
    apply_migrations(c, q.MIGRATIONS_DIR)
    return c


@pytest.fixture
def event(conn: sqlite3.Connection) -> q.Event:
    return q.create_event(conn, "xmas-2026", "Xmas 2026", 30, QUESTIONS)


def signup(conn: sqlite3.Connection, event: q.Event, who: str) -> q.Participant:
    return q.join_event(
        conn, event.id, f"{who}@example.com", who.title(), f"{who}-nick", ["a", "b"]
    )


# --- events -----------------------------------------------------------------------------


def test_create_and_get_event(conn: sqlite3.Connection) -> None:
    e = q.create_event(
        conn, "xmas-2026", " Xmas ", 30, [q.Section(" About ", (" Hobbies? ", "", "Colour?"))]
    )
    assert e.title == "Xmas" and e.questions == ("Hobbies?", "Colour?") and e.is_open
    assert e.sections == (q.Section("About", ("Hobbies?", "Colour?")),)
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
    q.update_event(conn, event.id, "New title", 40, [q.Section("", ("Only one?", "Two?"))])
    signup(conn, event, "ann")
    # Same questions + other changes: fine.
    e = q.update_event(conn, event.id, "Newer", 50, [q.Section("", ("Only one?", "Two?"))])
    assert (e.title, e.budget) == ("Newer", 50)
    with pytest.raises(q.QuestionsLocked):
        q.update_event(conn, event.id, "Newer", 50, [q.Section("", ("Changed?", "Two?"))])


def test_event_theme(conn: sqlite3.Connection, event: q.Event) -> None:
    assert event.theme == q.DEFAULT_THEME == "christmas"
    e = q.create_event(conn, "xmas-2027", "Xmas 2027", 30, [], theme="christmas")
    assert e.theme == "christmas"
    assert q.update_event(conn, e.id, "Xmas", 30, []).theme == "christmas"  # None keeps it
    assert q.update_event(conn, e.id, "Xmas", 30, [], theme="plain").theme == "plain"
    with pytest.raises(ValueError, match="theme"):
        q.create_event(conn, "bad", "Bad", 30, [], theme="nope")
    with pytest.raises(ValueError, match="theme"):
        q.update_event(conn, e.id, "Xmas", 30, [], theme="nope")


# --- sign-ups --------------------------------------------------------------------------


def test_join_normalises_and_returns_participant(conn: sqlite3.Connection, event: q.Event) -> None:
    p = q.join_event(
        conn, event.id, " Ann@Example.COM ", " Ann Tan ", " Rudolph ", [" ski ", "red"]
    )
    assert (p.name, p.nickname, p.answers, p.email) == (
        "Ann Tan",
        "Rudolph",
        ("ski", "red"),
        "ann@example.com",
    )
    assert q.get_participant(conn, event.id, "ANN@example.com") == p


def test_join_errors(conn: sqlite3.Connection, event: q.Event) -> None:
    ann = signup(conn, event, "ann")
    bob = "bob@example.com"
    with pytest.raises(q.AlreadyJoined):
        q.join_event(conn, event.id, "ANN@example.com", "Ann", "other", ["a", "b"])
    with pytest.raises(q.NicknameTaken):
        q.join_event(conn, event.id, bob, "Bob", "ANN-NICK", ["a", "b"])
    with pytest.raises(ValueError, match="answers"):
        q.join_event(conn, event.id, bob, "Bob", "bob", ["only one"])
    with pytest.raises(ValueError, match="name"):
        q.join_event(conn, event.id, bob, "  ", "bob", ["a", "b"])
    with pytest.raises(ValueError, match="email"):
        q.join_event(conn, event.id, "not-an-email", "Bob", "bob", ["a", "b"])
    with pytest.raises(q.NotFound):
        q.join_event(conn, 999, bob, "Bob", "bob", ["a", "b"])
    # Failed joins changed nothing.
    assert [p.id for p in q.list_participants(conn, event.id)] == [ann.id]
    assert not conn.in_transaction


def test_signup_refused_if_questions_changed(conn: sqlite3.Connection, event: q.Event) -> None:
    shown = event.sections
    # The organiser reorders the questions while the form is open (allowed: nobody joined).
    q.update_event(
        conn, event.id, event.title, 30, [q.Section("", ("Favourite colour?", "Hobbies?"))]
    )
    with pytest.raises(q.QuestionsChanged):
        q.join_event(
            conn, event.id, "ann@example.com", "Ann", "ann", ["ski", "red"], shown_sections=shown
        )
    assert q.list_participants(conn, event.id) == []
    # A form built from the current questions is accepted.
    current = q.get_event(conn, event.id).sections
    p = q.join_event(
        conn, event.id, "ann@example.com", "Ann", "ann", ["red", "ski"], shown_sections=current
    )
    assert p.answers == ("red", "ski")
    with pytest.raises(q.QuestionsChanged):
        q.update_signup(conn, event.id, p.email, "Ann", "ann", ["a", "b"], shown_sections=shown)


def test_update_signup(conn: sqlite3.Connection, event: q.Event) -> None:
    ann = signup(conn, event, "ann")
    p = q.update_signup(conn, event.id, ann.email, "Ann T", "Comet", ["x", "y"])
    assert (p.id, p.name, p.nickname, p.answers) == (ann.id, "Ann T", "Comet", ("x", "y"))
    with pytest.raises(q.NotFound):
        q.update_signup(conn, event.id, "zed@example.com", "Zed", "zed", ["a", "b"])
    assert not conn.in_transaction


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
    other = q.create_event(conn, "other", "Other", 10, [q.Section("", ("a?", "b?"))])
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

    assert q.get_giftee(conn, event.id, people[0].email) is None  # not matched yet
    assert q.run_matching(conn, event.id, random.Random(1)) == 6

    event = q.get_event(conn, event.id)
    assert event.status == "matched" and event.matched_at
    nicknames = {p.nickname for p in people}
    received = []
    for p in people:
        g = q.get_giftee(conn, event.id, p.email)
        assert g is not None and g.nickname != p.nickname and g.budget == 30
        assert g.clues == (("", (("Hobbies?", "a"), ("Favourite colour?", "b"))),)
        received.append(g.nickname)
    assert sorted(received) == sorted(nicknames)  # everyone receives exactly once
    # The excluded pair never gives to each other.
    assert q.get_giftee(conn, event.id, people[0].email).nickname != people[1].nickname
    assert q.get_giftee(conn, event.id, people[1].email).nickname != people[0].nickname


def test_after_matching_everything_is_closed(conn: sqlite3.Connection, event: q.Event) -> None:
    a, b, _ = (signup(conn, event, n) for n in ("ann", "bob", "cat"))
    q.run_matching(conn, event.id)
    with pytest.raises(q.EventClosed):
        q.run_matching(conn, event.id)
    with pytest.raises(q.EventClosed):
        signup(conn, event, "late")
    with pytest.raises(q.EventClosed):
        q.update_signup(conn, event.id, a.email, "Ann", "new", ["a", "b"])
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
    assert q.get_giftee(conn, event.id, "out@example.com") is None


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


# --- review fixes -------------------------------------------------------------------


def test_failed_commit_rolls_back_and_connection_stays_usable(conn: sqlite3.Connection) -> None:
    # A deferred foreign key is only checked at COMMIT, so COMMIT itself fails.
    conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE child (p INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)"
    )
    with pytest.raises(sqlite3.IntegrityError), q.transaction(conn):
        conn.execute("INSERT INTO child VALUES (42)")
    assert not conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 0
    with q.transaction(conn):  # next transaction works
        conn.execute("INSERT INTO parent VALUES (1)")


def test_budget_fixed_after_match_but_title_editable(
    conn: sqlite3.Connection, event: q.Event
) -> None:
    for n in ("ann", "bob", "cat"):
        signup(conn, event, n)
    q.run_matching(conn, event.id)
    with pytest.raises(q.EventClosed, match="budget"):
        q.update_event(conn, event.id, event.title, 999, QUESTIONS)
    renamed = q.update_event(conn, event.id, "Renamed", event.budget, QUESTIONS, "christmas")
    assert (renamed.title, renamed.budget, renamed.theme) == ("Renamed", 30, "christmas")


def test_delete_event(conn: sqlite3.Connection, event: q.Event) -> None:
    a, b, _ = (signup(conn, event, n) for n in ("ann", "bob", "cat"))
    q.add_exclusion(conn, event.id, a.id, b.id)
    other = q.create_event(conn, "other", "Other", 10, [q.Section("", ("a?", "b?"))])
    signup(conn, other, "ann")  # same person in another event
    q.delete_event(conn, event.id)
    with pytest.raises(q.NotFound):
        q.get_event(conn, event.id)
    assert len(q.list_participants(conn, other.id)) == 1  # other events untouched
    q.delete_event(conn, event.id)  # missing: no-op


def test_matched_event_cannot_be_deleted(conn: sqlite3.Connection, event: q.Event) -> None:
    for n in ("ann", "bob", "cat"):
        signup(conn, event, n)
    q.run_matching(conn, event.id)
    with pytest.raises(q.EventClosed):
        q.delete_event(conn, event.id)


def test_count_participants(conn: sqlite3.Connection, event: q.Event) -> None:
    assert q.count_participants(conn, event.id) == 0
    signup(conn, event, "ann")
    signup(conn, event, "bob")
    assert q.count_participants(conn, event.id) == 2


def test_list_events_joined_by(conn: sqlite3.Connection, event: q.Event) -> None:
    other = q.create_event(conn, "other", "Other", 10, [q.Section("", ("a?", "b?"))])
    q.create_event(conn, "not-joined", "Not joined", 10, [])
    signup(conn, event, "ann")
    signup(conn, other, "ann")
    signup(conn, event, "bob")
    assert [e.slug for e in q.list_events_joined_by(conn, " ANN@example.com ")] == [
        "other",
        "xmas-2026",
    ]
    assert [e.slug for e in q.list_events_joined_by(conn, "bob@example.com")] == ["xmas-2026"]
    assert q.list_events_joined_by(conn, "nobody@example.com") == []


def test_get_event_by_slug_ignores_case(conn: sqlite3.Connection, event: q.Event) -> None:
    assert q.get_event_by_slug(conn, " Xmas-2026 ").id == event.id


def test_sections_cleaned_and_kept_in_order(conn: sqlite3.Connection) -> None:
    e = q.create_event(
        conn,
        "sections",
        "Sections",
        30,
        [
            q.Section("About you", ("Hobbies?",)),
            q.Section("Empty", ("", "  ")),  # dropped: no questions left
            q.Section(" Reveal ", ("Say?", "Pose?"), hidden=True),
        ],
    )
    assert e.sections == (
        q.Section("About you", ("Hobbies?",)),
        q.Section("Reveal", ("Say?", "Pose?"), hidden=True),
    )
    assert e.questions == ("Hobbies?", "Say?", "Pose?")


def test_hidden_sections_never_reach_the_santa(conn: sqlite3.Connection) -> None:
    sections = [
        q.Section("About you", ("Hobbies?",)),
        q.Section("Reveal", ("Say?",), hidden=True),
        q.Section("The gift", ("Colour?",)),
    ]
    event = q.create_event(conn, "hidden", "Hidden", 30, sections)
    people = [
        q.join_event(conn, event.id, f"{n}@x.com", n, f"{n}-nick", ["fun", "SECRET", "red"])
        for n in ("ann", "bob", "cat")
    ]
    q.run_matching(conn, event.id, random.Random(1))
    for p in people:
        g = q.get_giftee(conn, event.id, p.email)
        assert g.clues == (
            ("About you", (("Hobbies?", "fun"),)),
            ("The gift", (("Colour?", "red"),)),
        )
        assert "SECRET" not in repr(g)


def test_pair_answers_splits_by_section() -> None:
    sections = [q.Section("A", ("1?", "2?")), q.Section("B", ("3?",), hidden=True)]
    assert q.pair_answers(sections, ["x", "y", "z"]) == [
        (sections[0], (("1?", "x"), ("2?", "y"))),
        (sections[1], (("3?", "z"),)),
    ]
