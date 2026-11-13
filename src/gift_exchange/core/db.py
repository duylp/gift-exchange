"""SQLite connection handling. Queries will live here too."""

import sqlite3
from pathlib import Path


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a connection configured the way the whole app expects.

    Args:
        db_path: Path to the SQLite file, or ":memory:" for a throwaway database (tests).
            The parent directory is created if it doesn't exist.

    Returns:
        A connection in autocommit mode (`isolation_level=None`): nothing is wrapped in a
        transaction implicitly, so code that needs one issues `BEGIN` / `COMMIT` itself.
        Foreign keys are enforced and rows come back as `sqlite3.Row`.
    """
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
