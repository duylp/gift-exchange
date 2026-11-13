"""Database access: every query the app runs, returning dataclasses.

All SQL lives in this package; the UI calls these functions. Import the package and use
its names (`from gift_exchange.core import db; db.join_event(...)`).

Modules: `connection` (connect, transactions, migrations folder), `errors`, `models`,
`users`, `events`, `signups`, `exclusions`, `matches`. The schema is in `migrations/`.

Match secrecy: `matches.get_giftee` is the only function that reads the `matches` table.
"""

from gift_exchange.core.db.connection import MIGRATIONS_DIR, connect, transaction
from gift_exchange.core.db.errors import (
    AlreadyJoined,
    DbError,
    EventClosed,
    NicknameTaken,
    NotFound,
    QuestionsLocked,
    SlugTaken,
)
from gift_exchange.core.db.events import (
    create_event,
    get_event,
    get_event_by_slug,
    list_events,
    update_event,
)
from gift_exchange.core.db.exclusions import add_exclusion, list_exclusions, remove_exclusion
from gift_exchange.core.db.matches import event_feasibility, get_giftee, run_matching
from gift_exchange.core.db.models import Event, Giftee, Participant, User
from gift_exchange.core.db.signups import (
    get_participant,
    join_event,
    list_participants,
    remove_participant,
    update_signup,
)
from gift_exchange.core.db.users import get_or_create_user, get_user

__all__ = [
    "MIGRATIONS_DIR",
    "AlreadyJoined",
    "DbError",
    "Event",
    "EventClosed",
    "Giftee",
    "NicknameTaken",
    "NotFound",
    "Participant",
    "QuestionsLocked",
    "SlugTaken",
    "User",
    "add_exclusion",
    "connect",
    "create_event",
    "event_feasibility",
    "get_event",
    "get_event_by_slug",
    "get_giftee",
    "get_or_create_user",
    "get_participant",
    "get_user",
    "join_event",
    "list_events",
    "list_exclusions",
    "list_participants",
    "remove_exclusion",
    "remove_participant",
    "run_matching",
    "transaction",
    "update_event",
    "update_signup",
]
