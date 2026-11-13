"""Small authorisation and safety checks around login."""

import time
from collections.abc import Callable


def is_admin(email: str | None, admin_emails: frozenset[str]) -> bool:
    """Whether a logged-in email is an organiser.

    Args:
        email: The logged-in email, or None if not logged in.
        admin_emails: Lowercased admin emails from settings (ADMIN_EMAILS).
    """
    return email is not None and email.strip().lower() in admin_emails


def safe_next(path: str | None) -> str:
    """Where to send someone after login: only a path on this site, never another site.

    Prevents an "open redirect", where a crafted login link bounces people to a phishing
    page after logging in.

    Args:
        path: The `next` value from the link, e.g. "/e/xmas-2026".

    Returns:
        `path` if it is a same-site path (a single leading "/"), otherwise "/".
    """
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return "/"
    # Browsers drop tabs and newlines from URLs, so "/\t/evil.example" would become
    # "//evil.example" (another site). Refuse any control character.
    if any(c < " " or c == "\x7f" for c in path):
        return "/"
    return path


class Cooldown:
    """Allows one action per key per `seconds` (e.g. one login email per address per minute).

    In memory, so it resets on restart — fine for a single-process app.

    Args:
        seconds: Minimum gap between allowed actions for the same key.
        clock: Time source in seconds; override only in tests.
    """

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._seconds = seconds
        self._clock = clock
        self._last: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        """Record an attempt for `key`; return False if the last allowed one was too recent."""
        now = self._clock()
        last = self._last.get(key)
        if last is not None and now - last < self._seconds:
            return False
        self._last[key] = now
        if len(self._last) > 1000:  # drop stale entries so this can't grow forever
            self._last = {k: t for k, t in self._last.items() if now - t < self._seconds}
        return True

    def forget(self, key: str) -> None:
        """Undo the last allowed attempt for `key` (e.g. the email failed to send)."""
        self._last.pop(key, None)
