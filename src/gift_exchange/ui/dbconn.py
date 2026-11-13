"""Short-lived database connections for UI code."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from gift_exchange.config import get_settings
from gift_exchange.core import db


@contextmanager
def open_db() -> Iterator[sqlite3.Connection]:
    """Open a connection for one page build or one action, then close it.

    Each page load and each button click gets its own connection, so nothing is shared
    between users or kept open while a phone is idle.
    """
    conn = db.connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()
