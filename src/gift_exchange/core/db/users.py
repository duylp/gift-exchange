"""Users: one per email, across all events."""

import sqlite3

from gift_exchange.core.db.errors import NotFound
from gift_exchange.core.db.models import User


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
