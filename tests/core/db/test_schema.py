import sqlite3

import pytest
from sqlite_migrate import apply_migrations, load_migrations

from gift_exchange.core.db import MIGRATIONS_DIR, connect


def test_app_migrations_apply_cleanly_and_are_idempotent() -> None:
    conn = connect(":memory:")
    expected = [m.version for m in load_migrations(MIGRATIONS_DIR)]
    assert apply_migrations(conn, MIGRATIONS_DIR) == expected
    assert apply_migrations(conn, MIGRATIONS_DIR) == []


# --- schema constraints (0001_initial) ---------------------------------------------


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = connect(":memory:")
    apply_migrations(conn, MIGRATIONS_DIR)
    return conn


def add_event(db: sqlite3.Connection, slug: str = "xmas-2026", questions: str = '["Q1?"]') -> int:
    return db.execute(
        "INSERT INTO events (slug, title, budget, questions) VALUES (?, 'Xmas', 30, ?)",
        (slug, questions),
    ).lastrowid


def join(db: sqlite3.Connection, event_id: int, email: str, nickname: str) -> int:
    return db.execute(
        "INSERT INTO participants (event_id, email, name, nickname, answers) "
        "VALUES (?, ?, 'Name', ?, ?)",
        (event_id, email, nickname, '["A"]'),
    ).lastrowid


def setup_three(db: sqlite3.Connection) -> tuple[int, list[int]]:
    event = add_event(db)
    people = [join(db, event, f"{n}@x.com", n) for n in ("ann", "bob", "cat")]
    return event, people


def match(db: sqlite3.Connection, event: int, people: list[int]) -> None:
    a, b, c = people
    db.executemany(
        "INSERT INTO matches (event_id, giver_id, giftee_id) VALUES (?, ?, ?)",
        [(event, a, b), (event, b, c), (event, c, a)],
    )
    db.execute("UPDATE events SET status = 'matched' WHERE id = ?", (event,))


def test_email_joins_once_per_event_case_insensitive(db: sqlite3.Connection) -> None:
    event, other = add_event(db), add_event(db, "other")
    join(db, event, "Ann@X.com", "a")
    with pytest.raises(sqlite3.IntegrityError):
        join(db, event, "ann@x.com", "b")
    join(db, other, "ann@x.com", "a")  # same person, another event: fine


@pytest.mark.parametrize("slug", ["Xmas", "-xmas", "xmas 2026", "xmas_2026", ""])
def test_bad_slug_rejected(db: sqlite3.Connection, slug: str) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        add_event(db, slug)


def test_good_slug_accepted(db: sqlite3.Connection) -> None:
    add_event(db, "xmas-2026")


def test_budget_must_be_positive_integer(db: sqlite3.Connection) -> None:
    for budget in (0, 12.5, "thirty"):
        with pytest.raises(sqlite3.Error):
            db.execute("INSERT INTO events (slug, title, budget) VALUES ('e', 'E', ?)", (budget,))


def test_questions_must_be_json_array(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        add_event(db, questions='{"q": 1}')


def test_unique_nickname_per_event(db: sqlite3.Connection) -> None:
    event = add_event(db)
    join(db, event, "a@x.com", "Rudolph")
    with pytest.raises(sqlite3.IntegrityError):
        join(db, event, "b@x.com", "rudolph")


def test_exclusion_pair_ordered_and_same_event(db: sqlite3.Connection) -> None:
    event, (a, b, _) = setup_three(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO exclusions VALUES (?, ?, ?)", (event, b, a))  # not a < b
    other = add_event(db, "other")
    x = join(db, other, "x@x.com", "x")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO exclusions VALUES (?, ?, ?)", (event, a, x))  # cross-event


def test_removing_participant_removes_their_exclusions(db: sqlite3.Connection) -> None:
    event, (a, b, _) = setup_three(db)
    db.execute("INSERT INTO exclusions VALUES (?, ?, ?)", (event, a, b))
    db.execute("DELETE FROM participants WHERE id = ?", (a,))
    assert db.execute("SELECT COUNT(*) FROM exclusions").fetchone()[0] == 0


def test_matched_participant_cannot_be_deleted(db: sqlite3.Connection) -> None:
    event, people = setup_three(db)
    match(db, event, people)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM participants WHERE id = ?", (people[0],))


def test_questions_locked_after_first_signup(db: sqlite3.Connection) -> None:
    event = add_event(db)
    db.execute("UPDATE events SET questions = '[\"New?\"]' WHERE id = ?", (event,))  # ok
    join(db, event, "a@x.com", "a")
    with pytest.raises(sqlite3.IntegrityError, match="locked"):
        db.execute("UPDATE events SET questions = '[\"Other?\"]' WHERE id = ?", (event,))
    db.execute("UPDATE events SET title = 'Renamed' WHERE id = ?", (event,))  # other fields ok


def test_signup_editable_until_matched(db: sqlite3.Connection) -> None:
    event, people = setup_three(db)
    db.execute("UPDATE participants SET nickname = 'Ann2' WHERE id = ?", (people[0],))
    match(db, event, people)
    with pytest.raises(sqlite3.IntegrityError, match="closed"):
        db.execute("UPDATE participants SET nickname = 'Ann3' WHERE id = ?", (people[0],))
    with pytest.raises(sqlite3.IntegrityError, match="closed"):
        join(db, event, "late@x.com", "late")


def test_exclusions_fixed_after_match(db: sqlite3.Connection) -> None:
    event, people = setup_three(db)
    db.execute("INSERT INTO exclusions VALUES (?, ?, ?)", (event, people[0], people[1]))
    match(db, event, people)
    with pytest.raises(sqlite3.IntegrityError, match="fixed"):
        db.execute("DELETE FROM exclusions")
    with pytest.raises(sqlite3.IntegrityError, match="fixed"):
        db.execute("INSERT INTO exclusions VALUES (?, ?, ?)", (event, people[1], people[2]))


def test_matched_event_cannot_reopen(db: sqlite3.Connection) -> None:
    event, people = setup_three(db)
    match(db, event, people)
    with pytest.raises(sqlite3.IntegrityError, match="reopened"):
        db.execute("UPDATE events SET status = 'open' WHERE id = ?", (event,))


def test_match_rows_are_one_to_one(db: sqlite3.Connection) -> None:
    event, (a, b, c) = setup_three(db)
    db.execute("INSERT INTO matches VALUES (?, ?, ?)", (event, a, b))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO matches VALUES (?, ?, ?)", (event, c, b))  # b twice as giftee
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO matches VALUES (?, ?, ?)", (event, c, c))  # self


def test_budget_fixed_after_match(db: sqlite3.Connection) -> None:
    event, people = setup_three(db)
    db.execute("UPDATE events SET budget = 40 WHERE id = ?", (event,))  # ok while open
    match(db, event, people)
    with pytest.raises(sqlite3.IntegrityError, match="budget is fixed"):
        db.execute("UPDATE events SET budget = 50 WHERE id = ?", (event,))
    db.execute(
        "UPDATE events SET budget = 40, title = 'New' WHERE id = ?", (event,)
    )  # unchanged ok
