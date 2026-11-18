"""Database access: every query the app runs, returning dataclasses.

All SQL lives in this package; the UI calls these functions. Import the package and use
its names (`from gift_exchange.core import db; db.join_event(...)`).

Modules: `connection` (connect, transactions, migrations folder), `errors`, `models`,
`events`, `signups`, `exclusions`, `matches`, `guesses`. The schema is in `migrations/`.

Match secrecy: `matches.get_giftee` is the only function that reads the `matches` table.
"""

from gift_exchange.core.db.connection import MIGRATIONS_DIR, connect, transaction
from gift_exchange.core.db.errors import (
    AlreadyJoined,
    DbError,
    EventClosed,
    GuessingClosed,
    NicknameTaken,
    NotFound,
    QuestionsChanged,
    QuestionsLocked,
    SlugTaken,
)
from gift_exchange.core.db.events import (
    create_event,
    delete_event,
    get_event,
    get_event_by_slug,
    list_events,
    list_events_joined_by,
    update_event,
)
from gift_exchange.core.db.exclusions import add_exclusion, list_exclusions, remove_exclusion
from gift_exchange.core.db.guesses import (
    close_guessing,
    count_guesses,
    get_my_guess,
    guess_options,
    save_guess,
)
from gift_exchange.core.db.matches import event_feasibility, get_giftee, run_matching
from gift_exchange.core.db.models import (
    DEFAULT_THEME,
    THEMES,
    Event,
    Giftee,
    GuessOption,
    Participant,
    Section,
    pair_answers,
)
from gift_exchange.core.db.signups import (
    count_participants,
    get_participant,
    join_event,
    list_participants,
    remove_participant,
    update_signup,
)

__all__ = [
    "DEFAULT_THEME",
    "MIGRATIONS_DIR",
    "THEMES",
    "AlreadyJoined",
    "DbError",
    "Event",
    "EventClosed",
    "Giftee",
    "GuessOption",
    "GuessingClosed",
    "NicknameTaken",
    "NotFound",
    "Participant",
    "QuestionsChanged",
    "QuestionsLocked",
    "Section",
    "SlugTaken",
    "add_exclusion",
    "close_guessing",
    "connect",
    "count_guesses",
    "count_participants",
    "create_event",
    "delete_event",
    "event_feasibility",
    "get_event",
    "get_event_by_slug",
    "get_giftee",
    "get_my_guess",
    "get_participant",
    "guess_options",
    "join_event",
    "list_events",
    "list_events_joined_by",
    "list_exclusions",
    "list_participants",
    "pair_answers",
    "remove_exclusion",
    "remove_participant",
    "run_matching",
    "save_guess",
    "transaction",
    "update_event",
    "update_signup",
]
