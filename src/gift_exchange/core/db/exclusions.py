"""Exclusions: pairs who must not be matched with each other (two-way)."""

import sqlite3

from gift_exchange.core.db.errors import EventClosed
from gift_exchange.core.db.events import get_event


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
