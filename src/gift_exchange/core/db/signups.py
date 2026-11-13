"""Sign-ups: joining an event, editing, listing and removing participants."""

import sqlite3
from collections.abc import Sequence

from gift_exchange.core.db._util import encode_list, require
from gift_exchange.core.db.connection import transaction
from gift_exchange.core.db.errors import (
    AlreadyJoined,
    DbError,
    EventClosed,
    NicknameTaken,
    NotFound,
)
from gift_exchange.core.db.events import get_event
from gift_exchange.core.db.models import (
    PARTICIPANT_SELECT,
    Event,
    Participant,
    participant_from_row,
)


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
    name, nickname, answers = check_signup(event, name, nickname, answers)
    try:
        with transaction(conn):
            conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
            cur = conn.execute(
                "INSERT INTO participants (event_id, user_id, nickname, answers) "
                "VALUES (?, ?, ?, ?)",
                (event_id, user_id, nickname, encode_list(answers)),
            )
    except sqlite3.IntegrityError as exc:
        raise signup_error(exc) from exc
    return get_participant_by_id(conn, cur.lastrowid)


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
    name, nickname, answers = check_signup(event, name, nickname, answers)
    try:
        with transaction(conn):
            conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
            cur = conn.execute(
                "UPDATE participants SET nickname = ?, answers = ? "
                "WHERE event_id = ? AND user_id = ?",
                (nickname, encode_list(answers), event_id, user_id),
            )
            if cur.rowcount == 0:
                raise NotFound("You haven't joined this event.")
    except sqlite3.IntegrityError as exc:
        raise signup_error(exc) from exc
    return get_participant(conn, event_id, user_id)


def get_participant(conn: sqlite3.Connection, event_id: int, user_id: int) -> Participant:
    """A user's sign-up for an event.

    Raises:
        NotFound: If the user hasn't joined the event.
    """
    row = conn.execute(
        f"{PARTICIPANT_SELECT} WHERE p.event_id = ? AND p.user_id = ?", (event_id, user_id)
    ).fetchone()
    if row is None:
        raise NotFound("You haven't joined this event.")
    return participant_from_row(row)


def list_participants(conn: sqlite3.Connection, event_id: int) -> list[Participant]:
    """Everyone signed up for an event, in sign-up order (organiser view)."""
    rows = conn.execute(f"{PARTICIPANT_SELECT} WHERE p.event_id = ? ORDER BY p.id", (event_id,))
    return [participant_from_row(r) for r in rows]


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
    event: Event, name: str, nickname: str, answers: Sequence[str]
) -> tuple[str, str, list[str]]:
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
    if "participants.user_id" in message:
        return AlreadyJoined("You've already joined this event.")
    raise exc
