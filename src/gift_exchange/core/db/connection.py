"""Connection setup, transactions, and where the schema migrations live."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import sqlite_migrate

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
"""The app's SQL migration files, run by the `sqlite_migrate` engine."""


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
    conn = sqlite_migrate.connect(db_path)  # autocommit + foreign keys; one shared setup
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block in one write transaction: commit on success, roll back on any error.

    If COMMIT itself fails (e.g. database locked, deferred constraint), the transaction is
    rolled back too, so the connection is never left stuck inside an open transaction.

    Args:
        conn: Connection from `connect`, not already inside a transaction.

    Yields:
        The same connection.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:  # SQLite may already have rolled back by itself
            conn.execute("ROLLBACK")
        raise
