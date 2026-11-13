"""Database access: connection setup and every query the app runs.

All SQL lives in this module; the UI calls these functions and gets dataclasses back.

Match secrecy: `get_giftee` is the only function that reads the `matches` table, and it
only answers "who does this user give to". Do not add a function that lists matches.
"""

import json
import random
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from gift_exchange.core.matching import Feasibility, check_feasibility, find_matching

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
"""The app's SQL migration files, run by the `sqlite_migrate` engine."""


# --- errors --------------------------------------------------------------------------


class DbError(Exception):
    """Base class for expected, user-facing database errors. The message is UI-safe."""


class NotFound(DbError):
    """The requested event, participant or user doesn't exist."""


class SlugTaken(DbError):
    """Another event already uses this slug."""


class AlreadyJoined(DbError):
    """The user has already signed up for this event."""


class NicknameTaken(DbError):
    """Someone else in the event already uses this nickname (case-insensitive)."""


class EventClosed(DbError):
    """The event has been matched, so sign-ups, edits and exclusions are fixed."""


class QuestionsLocked(DbError):
    """The event's questions can't change because someone has already signed up."""


# --- data -----------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    """A person, identified by email, across all events.

    Attributes:
        id: Row ID.
        email: Lowercased email address.
        name: Real name, or None until their first sign-up.
    """

    id: int
    email: str
    name: str | None


@dataclass(frozen=True)
class Event:
    """A gift exchange.

    Attributes:
        id: Row ID.
        slug: URL part, e.g. "xmas-2026" for /e/xmas-2026.
        title: Display title.
        budget: Gift budget in whole S$.
        questions: Clue questions asked at sign-up, in order.
        status: "open" (sign-ups open) or "matched" (final).
        matched_at: UTC ISO-8601 time matching ran, or None.
    """

    id: int
    slug: str
    title: str
    budget: int
    questions: tuple[str, ...]
    status: str
    matched_at: str | None

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True)
class Participant:
    """A user's sign-up for one event.

    Attributes:
        id: Row ID (the ID used for exclusions and matching).
        event_id: The event.
        user_id: The user.
        name: The user's real name (organiser / reveal only).
        email: The user's email (organiser only).
        nickname: Anonymous name shown to their Santa.
        answers: Answers in the same order as the event's questions.
    """

    id: int
    event_id: int
    user_id: int
    name: str
    email: str
    nickname: str
    answers: tuple[str, ...]


@dataclass(frozen=True)
class Giftee:
    """What a Santa sees about the person they give to.

    Attributes:
        nickname: The giftee's anonymous nickname (never their real name).
        clues: (question, answer) pairs, in question order.
        budget: The event's gift budget in whole S$.
    """

    nickname: str
    clues: tuple[tuple[str, str], ...]
    budget: int


# --- connection -------------------------------------------------------------------------


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a connection configured the way the whole app expects.

    Args:
        db_path: Path to the SQLite file, or ":memory:" for a throwaway database (tests).
            The parent directory is created if it doesn't exist.

    Returns:
        A connection in autocommit mode (`isolation_level=None`): nothing is wrapped in a
        transaction implicitly; functions here that need one use `transaction()`.
        Foreign keys are enforced and rows come back as `sqlite3.Row`.
    """
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block in one write transaction: commit on success, roll back on any error.

    Args:
        conn: Connection from `connect`, not already inside a transaction.

    Yields:
        The same connection.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


# --- users ----------------------------------------------------------------------------


def get_or_create_user(conn: sqlite3.Connection, email: str) -> User:
    """Find a user by email, creating them if new. Called when a login link is used.

    Args:
        conn: Database connection.
        email: Email address; surrounding spaces and case are ignored.

    Returns:
        The existing or newly created user.

    Raises:
        ValueError: If `email` is blank or has no "@".
    """
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("Not a valid email address.")
    conn.execute("INSERT INTO users (email) VALUES (?) ON CONFLICT (email) DO NOTHING", (email,))
    row = conn.execute("SELECT id, email, name FROM users WHERE email = ?", (email,)).fetchone()
    return User(row["id"], row["email"], row["name"])


def get_user(conn: sqlite3.Connection, user_id: int) -> User:
    """Look up a user by ID.

    Args:
        conn: Database connection.
        user_id: The user's row ID (e.g. from the session cookie).

    Returns:
        The user.

    Raises:
        NotFound: If there is no such user.
    """
    row = conn.execute("SELECT id, email, name FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFound("No such user.")
    return User(row["id"], row["email"], row["name"])


# --- events ---------------------------------------------------------------------------


def create_event(
    conn: sqlite3.Connection, slug: str, title: str, budget: int, questions: Sequence[str]
) -> Event:
    """Create an event, open for sign-ups.

    Args:
        conn: Database connection.
        slug: URL part: lowercase letters, digits and hyphens, e.g. "xmas-2026".
        title: Display title.
        budget: Gift budget in whole S$ (> 0).
        questions: Clue questions; blank entries are dropped, the rest are stripped.

    Returns:
        The new event.

    Raises:
        SlugTaken: If another event already uses `slug`.
        ValueError: If the slug, title or budget is invalid.
    """
    _require(title.strip(), "Title is required.")
    try:
        cur = conn.execute(
            "INSERT INTO events (slug, title, budget, questions) VALUES (?, ?, ?, ?)",
            (slug, title.strip(), budget, _encode(_clean(questions))),
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc):
            raise SlugTaken(f"An event with the link '{slug}' already exists.") from exc
        raise ValueError(
            "Invalid event: the link must be lowercase letters, digits and hyphens, "
            "and the budget a whole number above 0."
        ) from exc
    return get_event(conn, cur.lastrowid)


def get_event(conn: sqlite3.Connection, event_id: int) -> Event:
    """Look up an event by ID.

    Raises:
        NotFound: If there is no such event.
    """
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise NotFound("No such event.")
    return _event(row)


def get_event_by_slug(conn: sqlite3.Connection, slug: str) -> Event:
    """Look up an event by its URL slug.

    Raises:
        NotFound: If there is no such event.
    """
    row = conn.execute("SELECT * FROM events WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise NotFound("No such event.")
    return _event(row)


def list_events(conn: sqlite3.Connection) -> list[Event]:
    """All events, newest first."""
    return [_event(r) for r in conn.execute("SELECT * FROM events ORDER BY id DESC")]


def update_event(
    conn: sqlite3.Connection, event_id: int, title: str, budget: int, questions: Sequence[str]
) -> Event:
    """Change an event's title, budget and questions.

    Args:
        conn: Database connection.
        event_id: The event.
        title: New title.
        budget: New budget in whole S$ (> 0).
        questions: New questions (cleaned like `create_event`). Passing the current
            questions unchanged is always fine, even after people have signed up.

    Returns:
        The updated event.

    Raises:
        QuestionsLocked: If the questions differ and someone has already signed up.
        NotFound: If there is no such event.
        ValueError: If the title or budget is invalid.
    """
    _require(title.strip(), "Title is required.")
    try:
        cur = conn.execute(
            "UPDATE events SET title = ?, budget = ?, questions = ? WHERE id = ?",
            (title.strip(), budget, _encode(_clean(questions)), event_id),
        )
    except sqlite3.IntegrityError as exc:
        if "locked" in str(exc):
            raise QuestionsLocked("Questions can't be changed once someone has signed up.") from exc
        raise ValueError("The budget must be a whole number above 0.") from exc
    if cur.rowcount == 0:
        raise NotFound("No such event.")
    return get_event(conn, event_id)


# --- sign-ups ---------------------------------------------------------------------------


def join_event(
    conn: sqlite3.Connection,
    event_id: int,
    user_id: int,
    name: str,
    nickname: str,
    answers: Sequence[str],
) -> Participant:
    """Sign a user up for an event, saving their real name on their user record.

    Args:
        conn: Database connection.
        event_id: The event to join.
        user_id: The signed-in user.
        name: Their real name (required; updates the user record for future events).
        nickname: Anonymous name shown to their Santa (required, unique in the event).
        answers: One answer per event question, in order.

    Returns:
        The new participant.

    Raises:
        AlreadyJoined: If the user has already joined this event.
        NicknameTaken: If the nickname is in use in this event.
        EventClosed: If the event has been matched.
        NotFound: If the event doesn't exist.
        ValueError: If the name or nickname is blank, or the number of answers is wrong.
    """
    event = get_event(conn, event_id)
    name, nickname, answers = _check_signup(event, name, nickname, answers)
    try:
        with transaction(conn):
            conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
            cur = conn.execute(
                "INSERT INTO participants (event_id, user_id, nickname, answers) "
                "VALUES (?, ?, ?, ?)",
                (event_id, user_id, nickname, _encode(answers)),
            )
    except sqlite3.IntegrityError as exc:
        raise _signup_error(exc) from exc
    return _get_participant_by_id(conn, cur.lastrowid)


def update_signup(
    conn: sqlite3.Connection,
    event_id: int,
    user_id: int,
    name: str,
    nickname: str,
    answers: Sequence[str],
) -> Participant:
    """Change a user's sign-up (allowed until the event is matched).

    Args and Raises: as `join_event`, except it raises `NotFound` if the user hasn't
    joined, instead of `AlreadyJoined`.

    Returns:
        The updated participant.
    """
    event = get_event(conn, event_id)
    name, nickname, answers = _check_signup(event, name, nickname, answers)
    try:
        with transaction(conn):
            conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
            cur = conn.execute(
                "UPDATE participants SET nickname = ?, answers = ? "
                "WHERE event_id = ? AND user_id = ?",
                (nickname, _encode(answers), event_id, user_id),
            )
            if cur.rowcount == 0:
                raise NotFound("You haven't joined this event.")
    except sqlite3.IntegrityError as exc:
        raise _signup_error(exc) from exc
    return get_participant(conn, event_id, user_id)


def get_participant(conn: sqlite3.Connection, event_id: int, user_id: int) -> Participant:
    """A user's sign-up for an event.

    Raises:
        NotFound: If the user hasn't joined the event.
    """
    row = conn.execute(
        f"{_PARTICIPANT_SELECT} WHERE p.event_id = ? AND p.user_id = ?", (event_id, user_id)
    ).fetchone()
    if row is None:
        raise NotFound("You haven't joined this event.")
    return _participant(row)


def list_participants(conn: sqlite3.Connection, event_id: int) -> list[Participant]:
    """Everyone signed up for an event, in sign-up order (organiser view)."""
    rows = conn.execute(f"{_PARTICIPANT_SELECT} WHERE p.event_id = ? ORDER BY p.id", (event_id,))
    return [_participant(r) for r in rows]


def remove_participant(conn: sqlite3.Connection, participant_id: int) -> None:
    """Remove someone from an event before matching. Their exclusions go too.

    Raises:
        EventClosed: If the event has been matched.
    """
    try:
        conn.execute("DELETE FROM participants WHERE id = ?", (participant_id,))
    except sqlite3.IntegrityError as exc:
        raise EventClosed("The event has been matched; people can't be removed.") from exc


# --- exclusions ---------------------------------------------------------------------------


def add_exclusion(conn: sqlite3.Connection, event_id: int, a_id: int, b_id: int) -> None:
    """Forbid two participants from being matched with each other (either direction).

    Adding a pair that already exists does nothing.

    Args:
        conn: Database connection.
        event_id: The event both participants belong to.
        a_id: One participant's ID.
        b_id: The other participant's ID (order doesn't matter).

    Raises:
        EventClosed: If the event has been matched.
        ValueError: If `a_id == b_id` or either isn't in the event.
    """
    if a_id == b_id:
        raise ValueError("Pick two different people.")
    a_id, b_id = sorted((a_id, b_id))
    try:
        conn.execute(
            "INSERT INTO exclusions (event_id, a_id, b_id) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (event_id, a_id, b_id),
        )
    except sqlite3.IntegrityError as exc:
        if "fixed" in str(exc):
            raise EventClosed("The event has been matched; exclusions are fixed.") from exc
        raise ValueError("Both people must be in this event.") from exc


def remove_exclusion(conn: sqlite3.Connection, event_id: int, a_id: int, b_id: int) -> None:
    """Remove an exclusion (order of `a_id` / `b_id` doesn't matter; missing is fine).

    Raises:
        EventClosed: If the event has been matched (even if the pair doesn't exist).
        NotFound: If there is no such event.
    """
    if not get_event(conn, event_id).is_open:
        raise EventClosed("The event has been matched; exclusions are fixed.")
    a_id, b_id = sorted((a_id, b_id))
    conn.execute(
        "DELETE FROM exclusions WHERE event_id = ? AND a_id = ? AND b_id = ?",
        (event_id, a_id, b_id),
    )


def list_exclusions(conn: sqlite3.Connection, event_id: int) -> list[tuple[int, int]]:
    """An event's exclusions as (a_id, b_id) participant-ID pairs with a_id < b_id."""
    rows = conn.execute(
        "SELECT a_id, b_id FROM exclusions WHERE event_id = ? ORDER BY a_id, b_id", (event_id,)
    )
    return [(r["a_id"], r["b_id"]) for r in rows]


# --- matching -----------------------------------------------------------------------------


def event_feasibility(conn: sqlite3.Connection, event_id: int) -> Feasibility:
    """Quick check whether the event can be matched, for live admin-page warnings.

    Returns:
        A `Feasibility`; its `stuck` holds participant IDs.
    """
    people = [p.id for p in list_participants(conn, event_id)]
    return check_feasibility(people, list_exclusions(conn, event_id))


def run_matching(conn: sqlite3.Connection, event_id: int, rng: random.Random | None = None) -> int:
    """Draw the matches and close the event, all in one transaction.

    Deliberately returns only a count, never the pairs, so callers can't show them.

    Args:
        conn: Database connection.
        event_id: The event to match.
        rng: Random generator for `find_matching`. Leave as None in the app (unpredictable
            system randomness); pass a seeded one in tests only.

    Returns:
        The number of participants matched.

    Raises:
        EventClosed: If the event has already been matched.
        MatchingError: If no valid matching exists (see `matching.find_matching`); its
            `.people` are participant IDs. Nothing is saved.
        NotFound: If there is no such event.
    """
    with transaction(conn):
        if not get_event(conn, event_id).is_open:
            raise EventClosed("This event has already been matched.")
        people = [p.id for p in list_participants(conn, event_id)]
        assignment = find_matching(people, list_exclusions(conn, event_id), rng)
        conn.executemany(
            "INSERT INTO matches (event_id, giver_id, giftee_id) VALUES (?, ?, ?)",
            [(event_id, giver, giftee) for giver, giftee in assignment.items()],
        )
        conn.execute(
            "UPDATE events SET status = 'matched', "
            "matched_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (event_id,),
        )
    return len(assignment)


def get_giftee(conn: sqlite3.Connection, event_id: int, user_id: int) -> Giftee | None:
    """Who this user gives a gift to. The only function that reads matches.

    Args:
        conn: Database connection.
        event_id: The event.
        user_id: The signed-in user asking about their own giftee.

    Returns:
        The giftee's nickname, clues and the budget; or None if the event isn't matched
        yet or the user isn't in it.
    """
    row = conn.execute(
        """
        SELECT g.nickname, g.answers, e.questions, e.budget
        FROM participants AS me
        JOIN matches AS m ON m.giver_id = me.id
        JOIN participants AS g ON g.id = m.giftee_id
        JOIN events AS e ON e.id = me.event_id
        WHERE me.event_id = ? AND me.user_id = ?
        """,
        (event_id, user_id),
    ).fetchone()
    if row is None:
        return None
    clues = tuple(zip(json.loads(row["questions"]), json.loads(row["answers"]), strict=False))
    return Giftee(row["nickname"], clues, row["budget"])


# --- helpers ------------------------------------------------------------------------------

_PARTICIPANT_SELECT = """
    SELECT p.id, p.event_id, p.user_id, u.name, u.email, p.nickname, p.answers
    FROM participants AS p JOIN users AS u ON u.id = p.user_id
"""


def _event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        budget=row["budget"],
        questions=tuple(json.loads(row["questions"])),
        status=row["status"],
        matched_at=row["matched_at"],
    )


def _participant(row: sqlite3.Row) -> Participant:
    return Participant(
        id=row["id"],
        event_id=row["event_id"],
        user_id=row["user_id"],
        name=row["name"] or "",
        email=row["email"],
        nickname=row["nickname"],
        answers=tuple(json.loads(row["answers"])),
    )


def _get_participant_by_id(conn: sqlite3.Connection, participant_id: int) -> Participant:
    row = conn.execute(f"{_PARTICIPANT_SELECT} WHERE p.id = ?", (participant_id,)).fetchone()
    return _participant(row)


def _check_signup(
    event: Event, name: str, nickname: str, answers: Sequence[str]
) -> tuple[str, str, list[str]]:
    name, nickname = name.strip(), nickname.strip()
    _require(name, "Your name is required.")
    _require(nickname, "A nickname is required.")
    if len(answers) != len(event.questions):
        raise ValueError(f"Expected {len(event.questions)} answers, got {len(answers)}.")
    return name, nickname, [a.strip() for a in answers]


def _signup_error(exc: sqlite3.IntegrityError) -> DbError:
    message = str(exc)
    if "closed" in message:
        return EventClosed("Sign-ups are closed: this event has been matched.")
    if "participants.nickname" in message:
        return NicknameTaken("That nickname is taken in this event; pick another.")
    if "participants.user_id" in message:
        return AlreadyJoined("You've already joined this event.")
    raise exc


def _clean(items: Sequence[str]) -> list[str]:
    return [s.strip() for s in items if s.strip()]


def _encode(items: Sequence[str]) -> str:
    return json.dumps(list(items), ensure_ascii=False)


def _require(value: str, message: str) -> None:
    if not value:
        raise ValueError(message)
