"""Passwordless login: signed magic links and session cookies. Design: CLAUDE.md **Auth**.

Modules: `tokens` (login links, sessions), `guards` (admin check, safe redirects, cooldown).
Plain Python: no NiceGUI imports.
"""

from gift_exchange.core.auth.guards import Cooldown, is_admin, normalize_email, safe_next
from gift_exchange.core.auth.tokens import (
    LOGIN_LINK_MAX_AGE,
    SESSION_MAX_AGE,
    LinkExpired,
    LinkInvalid,
    make_login_token,
    make_session,
    read_login_token,
    read_session,
)

__all__ = [
    "LOGIN_LINK_MAX_AGE",
    "SESSION_MAX_AGE",
    "Cooldown",
    "LinkExpired",
    "LinkInvalid",
    "is_admin",
    "make_login_token",
    "make_session",
    "normalize_email",
    "read_login_token",
    "read_session",
    "safe_next",
]
