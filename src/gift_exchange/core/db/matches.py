"""Matching: feasibility, drawing the matches, and the giftee lookup.

Match secrecy: `get_giftee` is the only function that reads the `matches` table, and it
only answers "who does this user give to". Do not add a function that lists matches.
"""

import json
import random
import sqlite3

from gift_exchange.core.db.connection import transaction
from gift_exchange.core.db.errors import EventClosed
from gift_exchange.core.db.events import get_event
from gift_exchange.core.db.exclusions import list_exclusions
from gift_exchange.core.db.models import Giftee, decode_sections, pair_answers
from gift_exchange.core.db.signups import list_participants
from gift_exchange.core.matching import Feasibility, check_feasibility, find_matching


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


def get_giftee(conn: sqlite3.Connection, event_id: int, email: str) -> Giftee | None:
    """Who this person gives a gift to. The only function that reads matches.

    Args:
        conn: Database connection.
        event_id: The event.
        email: The signed-in person's email (from the session), asking about their own
            giftee. Case and surrounding spaces are ignored.

    Returns:
        The giftee's nickname, clues (hidden reveal-only sections left out) and the
        budget; or None if the event isn't matched
        yet or this email isn't in it.
    """
    row = conn.execute(
        """
        SELECT g.nickname, g.answers, e.questions, e.budget
        FROM participants AS me
        JOIN matches AS m ON m.giver_id = me.id
        JOIN participants AS g ON g.id = m.giftee_id
        JOIN events AS e ON e.id = me.event_id
        WHERE me.event_id = ? AND me.email = ?
        """,
        (event_id, email.strip().lower()),
    ).fetchone()
    if row is None:
        return None
    groups = pair_answers(decode_sections(row["questions"]), json.loads(row["answers"]))
    clues = tuple((section.title, pairs) for section, pairs in groups if not section.hidden)
    return Giftee(row["nickname"], clues, row["budget"])
