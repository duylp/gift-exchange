"""Sign-ups: joining an event, editing, listing and removing participants.

A person is identified by their email within each event (there is no users table); the
email comes from the signed login cookie, never from a form field.
"""

import sqlite3
from collections.abc import Sequence

from gift_exchange.core.auth import normalize_email
from gift_exchange.core.db._util import encode_list, require
from gift_exchange.core.db.connection import transaction
from gift_exchange.core.db.errors import (
    AlreadyJoined,
    DbError,
    EventClosed,
    NicknameTaken,
    NotFound,
    QuestionsChanged,
)
from gift_exchange.core.db.events import get_event
from gift_exchange.core.db.models import (
    PARTICIPANT_SELECT,
    Event,
    Participant,
    Section,
    participant_from_row,
)


def join_event(
    conn: sqlite3.Connection,
    event_id: int,
    email: str,
    name: str,
    nickname: str,
    answers: Sequence[str],
    *,
    shown_sections: Sequence[Section] | None = None,
) -> Participant:
    """Sign a person up for an event.

    Args:
        conn: Database connection.
        event_id: The event to join.
        email: The signed-in person's email (from the session). Case and surrounding
            spaces are ignored.
        name: Their real name (required).
        nickname: Anonymous name shown to their Santa (required, unique in the event).
        answers: One answer per event question, in order.
        shown_sections: The question sections the form showed (`event.sections` when it
            was built). If given and the event's sections differ now, nothing is saved.
            The UI always passes it; None skips the check (scripts, tests).

    Returns:
        The new participant.

    Raises:
        AlreadyJoined: If this email has already joined the event.
        NicknameTaken: If the nickname is in use in this event.
        EventClosed: If the event has been matched.
        NotFound: If the event doesn't exist.
        QuestionsChanged: If `shown_sections` no longer matches the event.
        ValueError: If the email is invalid, the name or nickname is blank, or the number
            of answers is wrong.
    """
    email = normalize_email(email)
    try:
        with transaction(conn):
            # Validate inside the transaction so the questions can't change under us.
            event = get_event(conn, event_id)
            name, nickname, answers = check_signup(event, name, nickname, answers, shown_sections)
            cur = conn.execute(
                "INSERT INTO participants (event_id, email, name, nickname, answers) "
                "VALUES (?, ?, ?, ?, ?)",
                (event_id, email, name, nickname, encode_list(answers)),
            )
    except sqlite3.IntegrityError as exc:
        raise signup_error(exc) from exc
    return get_participant_by_id(conn, cur.lastrowid)


def update_signup(
    conn: sqlite3.Connection,
    event_id: int,
    email: str,
    name: str,
    nickname: str,
    answers: Sequence[str],
    *,
    shown_sections: Sequence[Section] | None = None,
) -> Participant:
    """Change a person's sign-up (allowed until the event is matched).

    Args and Raises: as `join_event`, except it raises `NotFound` if this email hasn't
    joined, instead of `AlreadyJoined`.

    Returns:
        The updated participant.
    """
    email = normalize_email(email)
    try:
        with transaction(conn):
            event = get_event(conn, event_id)
            name, nickname, answers = check_signup(event, name, nickname, answers, shown_sections)
            cur = conn.execute(
                "UPDATE participants SET name = ?, nickname = ?, answers = ? "
                "WHERE event_id = ? AND email = ?",
                (name, nickname, encode_list(answers), event_id, email),
            )
            if cur.rowcount == 0:
                raise NotFound("You haven't joined this event.")
    except sqlite3.IntegrityError as exc:
        raise signup_error(exc) from exc
    return get_participant(conn, event_id, email)


def get_participant(conn: sqlite3.Connection, event_id: int, email: str) -> Participant:
    """A person's sign-up for an event.

    Args:
        conn: Database connection.
        event_id: The event.
        email: The person's email (case and surrounding spaces are ignored).

    Raises:
        NotFound: If this email hasn't joined the event.
    """
    row = conn.execute(
        f"{PARTICIPANT_SELECT} WHERE p.event_id = ? AND p.email = ?",
        (event_id, email.strip().lower()),
    ).fetchone()
    if row is None:
        raise NotFound("You haven't joined this event.")
    return participant_from_row(row)


def list_participants(conn: sqlite3.Connection, event_id: int) -> list[Participant]:
    """Everyone signed up for an event, in sign-up order (organiser view)."""
    rows = conn.execute(f"{PARTICIPANT_SELECT} WHERE p.event_id = ? ORDER BY p.id", (event_id,))
    return [participant_from_row(r) for r in rows]


def count_participants(conn: sqlite3.Connection, event_id: int) -> int:
    """How many people have joined an event (safe to show publicly: just a number)."""
    return conn.execute(
        "SELECT COUNT(*) FROM participants WHERE event_id = ?", (event_id,)
    ).fetchone()[0]


def remove_participant(conn: sqlite3.Connection, participant_id: int) -> None:
    """Remove someone from an event before matching. Their exclusions go too.

    Raises:
        EventClosed: If the event has been matched.
    """
    try:
        conn.execute("DELETE FROM participants WHERE id = ?", (participant_id,))
    except sqlite3.IntegrityError as exc:
        raise EventClosed("The event has been matched; people can't be removed.") from exc


def get_participant_by_id(conn: sqlite3.Connection, participant_id: int) -> Participant:
    row = conn.execute(f"{PARTICIPANT_SELECT} WHERE p.id = ?", (participant_id,)).fetchone()
    return participant_from_row(row)


def check_signup(
    event: Event,
    name: str,
    nickname: str,
    answers: Sequence[str],
    shown_sections: Sequence[Section] | None = None,
) -> tuple[str, str, list[str]]:
    """Validate and clean a sign-up against the event (see `join_event` for the args).

    Returns:
        The stripped name, nickname and answers.

    Raises:
        QuestionsChanged: If `shown_sections` is given and differs from the event's.
        ValueError: If the name or nickname is blank or the number of answers is wrong.
    """
    if shown_sections is not None and tuple(shown_sections) != event.sections:
        raise QuestionsChanged(
            "The questions changed while you were filling in the form. "
            "Reload the page and check your answers."
        )
    name, nickname = name.strip(), nickname.strip()
    require(name, "Your name is required.")
    require(nickname, "A nickname is required.")
    if len(answers) != len(event.questions):
        raise ValueError(f"Expected {len(event.questions)} answers, got {len(answers)}.")
    return name, nickname, [a.strip() for a in answers]


def signup_error(exc: sqlite3.IntegrityError) -> DbError:
    message = str(exc)
    if "closed" in message:
        return EventClosed("Sign-ups are closed: this event has been matched.")
    if "participants.nickname" in message:
        return NicknameTaken("That nickname is taken in this event; pick another.")
    if "participants.email" in message:
        return AlreadyJoined("You've already joined this event.")
    raise exc
