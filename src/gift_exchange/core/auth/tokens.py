"""Signed login links and session cookies (itsdangerous). Nothing is stored server-side.

Both carry the person's email, signed with SECRET_KEY: anyone can read it, nobody can
change or forge it without the key. Rotating SECRET_KEY invalidates every link and session.
"""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

LOGIN_LINK_MAX_AGE = 15 * 60  # seconds a login link stays valid (reusable within it)
SESSION_MAX_AGE = 30 * 24 * 60 * 60  # seconds a login session lasts

# Different salts make a login token useless as a session cookie and vice versa.
_LOGIN_SALT = "login-link"
_SESSION_SALT = "session"


class LinkExpired(Exception):
    """The login link is genuine but older than LOGIN_LINK_MAX_AGE."""


class LinkInvalid(Exception):
    """The login link was tampered with, truncated, or signed with another key."""


def make_login_token(secret_key: str, email: str) -> str:
    """Create the token that goes in a login link.

    Args:
        secret_key: The app's SECRET_KEY.
        email: The address the link is emailed to; lowercased and trimmed.

    Returns:
        A URL-safe token, valid for LOGIN_LINK_MAX_AGE seconds.
    """
    return _serializer(secret_key, _LOGIN_SALT).dumps(email.strip().lower())


def read_login_token(secret_key: str, token: str, max_age: int = LOGIN_LINK_MAX_AGE) -> str:
    """Check a login token and return the email it was issued for.

    Args:
        secret_key: The app's SECRET_KEY.
        token: The `token` query parameter from the link.
        max_age: Maximum age in seconds (override only in tests).

    Returns:
        The email address.

    Raises:
        LinkExpired: If the token is genuine but too old.
        LinkInvalid: If the token is not genuine.
    """
    try:
        return _serializer(secret_key, _LOGIN_SALT).loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise LinkExpired("This login link has expired. Please request a new one.") from exc
    except BadSignature as exc:
        raise LinkInvalid("This login link isn't valid. Please request a new one.") from exc


def make_session(secret_key: str, email: str) -> str:
    """Create the session cookie value for a logged-in person.

    Args:
        secret_key: The app's SECRET_KEY.
        email: The verified email from a login link.

    Returns:
        The cookie value, valid for SESSION_MAX_AGE seconds.
    """
    return _serializer(secret_key, _SESSION_SALT).dumps(email.strip().lower())


def read_session(secret_key: str, cookie: str | None, max_age: int = SESSION_MAX_AGE) -> str | None:
    """Return the logged-in email from a session cookie, or None if not logged in.

    Args:
        secret_key: The app's SECRET_KEY.
        cookie: The session cookie value, or None if the browser sent none.
        max_age: Maximum age in seconds (override only in tests).

    Returns:
        The email, or None if the cookie is missing, expired, or not genuine.
    """
    if not cookie:
        return None
    try:
        return _serializer(secret_key, _SESSION_SALT).loads(cookie, max_age=max_age)
    except BadSignature:  # also covers SignatureExpired
        return None


def _serializer(secret_key: str, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=salt)
