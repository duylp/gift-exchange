"""Events: create, look up and edit."""

import sqlite3
from collections.abc import Sequence

from gift_exchange.core.db._util import clean_list, encode_list, require
from gift_exchange.core.db.errors import EventClosed, NotFound, QuestionsLocked, SlugTaken
from gift_exchange.core.db.models import Event, event_from_row


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
    require(title.strip(), "Title is required.")
    try:
        cur = conn.execute(
            "INSERT INTO events (slug, title, budget, questions) VALUES (?, ?, ?, ?)",
            (slug, title.strip(), budget, encode_list(clean_list(questions))),
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
    return event_from_row(row)


def get_event_by_slug(conn: sqlite3.Connection, slug: str) -> Event:
    """Look up an event by its URL slug.

    Raises:
        NotFound: If there is no such event.
    """
    row = conn.execute("SELECT * FROM events WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise NotFound("No such event.")
    return event_from_row(row)


def list_events(conn: sqlite3.Connection) -> list[Event]:
    """All events, newest first."""
    return [event_from_row(r) for r in conn.execute("SELECT * FROM events ORDER BY id DESC")]


def list_events_joined_by(conn: sqlite3.Connection, email: str) -> list[Event]:
    """Events this email has signed up for, newest first (for the person's home page).

    Args:
        conn: Database connection.
        email: The logged-in email (case and surrounding spaces are ignored).

    Returns:
        Only events this email joined — never other events.
    """
    rows = conn.execute(
        "SELECT e.* FROM events AS e JOIN participants AS p ON p.event_id = e.id "
        "WHERE p.email = ? ORDER BY e.id DESC",
        (email.strip().lower(),),
    )
    return [event_from_row(r) for r in rows]


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
        EventClosed: If the budget differs and the event has been matched (Santas may
            already have bought gifts). The title can always change.
        NotFound: If there is no such event.
        ValueError: If the title or budget is invalid.
    """
    require(title.strip(), "Title is required.")
    try:
        cur = conn.execute(
            "UPDATE events SET title = ?, budget = ?, questions = ? WHERE id = ?",
            (title.strip(), budget, encode_list(clean_list(questions)), event_id),
        )
    except sqlite3.IntegrityError as exc:
        if "locked" in str(exc):
            raise QuestionsLocked("Questions can't be changed once someone has signed up.") from exc
        if "budget is fixed" in str(exc):
            raise EventClosed("The budget can't change after matching.") from exc
        raise ValueError("The budget must be a whole number above 0.") from exc
    if cur.rowcount == 0:
        raise NotFound("No such event.")
    return get_event(conn, event_id)


def delete_event(conn: sqlite3.Connection, event_id: int) -> None:
    """Delete an event that hasn't been matched, with its sign-ups and exclusions.

    Users are kept (they may be in other events). Deleting a missing event does nothing.

    Raises:
        EventClosed: If the event has been matched (matches are never deleted).
    """
    try:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    except sqlite3.IntegrityError as exc:
        raise EventClosed("A matched event can't be deleted.") from exc
