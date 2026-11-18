"""Giftee guesses: after matching, each Santa guesses which participant (by real name) is
behind their giftee's nickname. The organiser closes guessing at the party.

Match secrecy: nothing here reads the `matches` table or checks a guess against it, so a
guess can't reveal anything: every participant except yourself is a valid guess, and
saving never says whether it's right. Scoring comes later, with the reveal page.
"""

import sqlite3

from gift_exchange.core.db.connection import transaction
from gift_exchange.core.db.errors import GuessingClosed, NotFound
from gift_exchange.core.db.events import get_event
from gift_exchange.core.db.models import Event, GuessOption
from gift_exchange.core.db.signups import get_participant


def guess_options(conn: sqlite3.Connection, event_id: int, email: str) -> list[GuessOption]:
    """Who this person can pick as their guess: everyone else in the event, by name.

    Args:
        conn: Database connection.
        event_id: The event.
        email: The signed-in Santa's email (from the session). Case and surrounding spaces
            are ignored.

    Returns:
        Every other participant's ID and real name, sorted by name (never by anything that
        could hint at the matches).

    Raises:
        NotFound: If this email hasn't joined the event.
    """
    me = get_participant(conn, event_id, email)
    rows = conn.execute(
        "SELECT id, name FROM participants WHERE event_id = ? AND id <> ? "
        "ORDER BY name COLLATE NOCASE, id",
        (event_id, me.id),
    )
    return [GuessOption(r["id"], r["name"]) for r in rows]


def get_my_guess(conn: sqlite3.Connection, event_id: int, email: str) -> int | None:
    """This person's current guess.

    Args:
        conn: Database connection.
        event_id: The event.
        email: The signed-in Santa's email (case and surrounding spaces are ignored).

    Returns:
        The participant ID they guessed, or None if they haven't guessed (or haven't
        joined the event).
    """
    row = conn.execute(
        "SELECT g.guessed_id FROM guesses AS g JOIN participants AS me ON me.id = g.guesser_id "
        "WHERE me.event_id = ? AND me.email = ?",
        (event_id, email.strip().lower()),
    ).fetchone()
    return None if row is None else row["guessed_id"]


def save_guess(conn: sqlite3.Connection, event_id: int, email: str, guessed_id: int) -> None:
    """Save (or change) this person's guess of who their giftee really is.

    Never checks the guess against the matches: any other participant is accepted.

    Args:
        conn: Database connection.
        event_id: The event.
        email: The signed-in Santa's email (from the session; case and surrounding spaces
            are ignored).
        guessed_id: The participant they think their giftee is (from `guess_options`).

    Raises:
        GuessingClosed: If the event isn't matched yet or the organiser closed guessing.
        NotFound: If this email hasn't joined the event, or `guessed_id` isn't in it.
        ValueError: If they guessed themselves.
    """
    with transaction(conn):
        event = get_event(conn, event_id)
        _check_guessing_open(event)
        me = get_participant(conn, event_id, email)
        if guessed_id == me.id:
            raise ValueError("You can't be your own giftee.")
        found = conn.execute(
            "SELECT 1 FROM participants WHERE event_id = ? AND id = ?", (event_id, guessed_id)
        ).fetchone()
        if found is None:
            raise NotFound("That person isn't in this event.")
        conn.execute(
            "INSERT INTO guesses (event_id, guesser_id, guessed_id) VALUES (?, ?, ?) "
            "ON CONFLICT (guesser_id) DO UPDATE SET guessed_id = excluded.guessed_id, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
            (event_id, me.id, guessed_id),
        )


def count_guesses(conn: sqlite3.Connection, event_id: int) -> int:
    """How many Santas have guessed (organiser view: just a number, never the guesses).

    Args:
        conn: Database connection.
        event_id: The event.

    Returns:
        The number of participants with a saved guess (0 before matching).
    """
    return conn.execute("SELECT COUNT(*) FROM guesses WHERE event_id = ?", (event_id,)).fetchone()[
        0
    ]


def close_guessing(conn: sqlite3.Connection, event_id: int) -> Event:
    """Close giftee guessing for good (the organiser does this just before the reveal).

    Args:
        conn: Database connection.
        event_id: The event.

    Returns:
        The updated event.

    Raises:
        GuessingClosed: If the event isn't matched yet or guessing is already closed.
        NotFound: If there is no such event.
    """
    with transaction(conn):
        _check_guessing_open(get_event(conn, event_id))
        conn.execute(
            "UPDATE events SET guesses_closed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = ?",
            (event_id,),
        )
    return get_event(conn, event_id)


def _check_guessing_open(event: Event) -> None:
    if event.is_open:
        raise GuessingClosed("Guessing opens after the draw.")
    if not event.guessing_open:
        raise GuessingClosed("Guessing is closed.")
