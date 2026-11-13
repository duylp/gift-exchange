"""Reading and writing the login session cookie (see core/auth for the signing)."""

from fastapi import Request
from fastapi.responses import Response

from gift_exchange.config import get_settings
from gift_exchange.core.auth import SESSION_MAX_AGE, is_admin, make_session, read_session

SESSION_COOKIE = "session"


def current_email(request: Request) -> str | None:
    """The logged-in email for this request, or None.

    In a page, take `request: Request` as a parameter (NiceGUI injects it) and call this
    while building the page; keep the result in a variable for event handlers.
    """
    return read_session(get_settings().secret_key, request.cookies.get(SESSION_COOKIE))


def current_admin(request: Request) -> bool:
    """Whether this request comes from a logged-in organiser (email in ADMIN_EMAILS)."""
    return is_admin(current_email(request), get_settings().admin_emails)


def set_session_cookie(response: Response, email: str) -> None:
    """Log `email` in on this response: HttpOnly, Secure on HTTPS, SameSite=Lax, 30 days."""
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        make_session(settings.secret_key, email),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.base_url.startswith("https://"),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Log out on this response by deleting the cookie."""
    response.delete_cookie(SESSION_COOKIE, path="/")
