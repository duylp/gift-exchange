"""Expected, user-facing database errors. Messages are safe to show users."""


class DbError(Exception):
    """Base class for expected, user-facing database errors. The message is UI-safe."""


class NotFound(DbError):
    """The requested event, participant or user doesn't exist."""


class SlugTaken(DbError):
    """Another event already uses this slug."""


class AlreadyJoined(DbError):
    """The user has already signed up for this event."""


class NicknameTaken(DbError):
    """Someone else in the event already uses this nickname (case-insensitive)."""


class EventClosed(DbError):
    """The event has been matched, so sign-ups, edits and exclusions are fixed."""


class QuestionsChanged(DbError):
    """The event's questions changed after the sign-up form was shown (answers would
    otherwise be saved against the wrong questions)."""


class QuestionsLocked(DbError):
    """The event's questions can't change because someone has already signed up."""


class GuessingClosed(DbError):
    """Giftee guesses can't be made or changed: the event isn't matched yet, or the
    organiser has closed guessing."""
