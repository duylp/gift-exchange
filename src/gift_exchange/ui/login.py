"""Login: the /login email form, the /auth magic-link route, and /logout."""

import functools
import logging
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app, ui

from gift_exchange.config import get_settings
from gift_exchange.core.auth import (
    Cooldown,
    LinkExpired,
    LinkInvalid,
    make_login_token,
    read_login_token,
    safe_next,
)
from gift_exchange.core.email import EmailError, EmailSender, login_email, make_sender
from gift_exchange.ui.layout import page_frame
from gift_exchange.ui.session import clear_session_cookie, current_email, set_session_cookie

log = logging.getLogger(__name__)

# One login email per address per minute (protects inboxes and Resend's daily quota).
_cooldown = Cooldown(seconds=60)

# Fixed messages for /login?error=…, so a crafted link can't put arbitrary text on our page.
_LINK_ERRORS = {
    "expired": "That login link has expired. Enter your email to get a new one.",
    "invalid": "That login link isn't valid. Enter your email to get a new one.",
}


@functools.cache
def _sender() -> EmailSender:
    s = get_settings()
    return make_sender(s.dev, s.resend_api_key, s.email_from)


def login_url(next_path: str) -> str:
    """The /login URL that returns to `next_path` afterwards."""
    return "/login?" + urlencode({"next": safe_next(next_path)})


@app.get("/auth")
def auth(token: str = "", next: str = "/") -> RedirectResponse:
    """Magic-link target: verify the token, set the session cookie, go back to `next`."""
    target = safe_next(next)
    try:
        email = read_login_token(get_settings().secret_key, token)
    except (LinkExpired, LinkInvalid) as exc:
        error = "expired" if isinstance(exc, LinkExpired) else "invalid"
        return RedirectResponse("/login?" + urlencode({"next": target, "error": error}), 303)
    response = RedirectResponse(target, 303)
    set_session_cookie(response, email)
    return response


@app.get("/logout")
def logout() -> RedirectResponse:
    """Clear the session cookie and go to the home page."""
    response = RedirectResponse("/", 303)
    clear_session_cookie(response)
    return response


@ui.page("/login")
def login_page(request: Request, next: str = "/", error: str = "") -> RedirectResponse | None:
    """The /login page: email form that sends a magic link.

    Args:
        request: The incoming request (injected by NiceGUI), for the session cookie.
        next: Where to go after logging in (same-site paths only).
        error: "expired" or "invalid" when sent here by a bad /auth link.

    Returns:
        A redirect to `next` if already logged in, otherwise None (render the form).
    """
    target = safe_next(next)
    if current_email(request):
        return RedirectResponse(target, 303)

    with page_frame("max-w-sm"):
        ui.label("Log in 🎁").classes("text-2xl font-bold")
        if error in _LINK_ERRORS:
            ui.label(_LINK_ERRORS[error]).classes("text-red-700")
        login_form(target)
    return None


def login_form(next_path: str) -> None:
    """Email form that sends a magic link returning to `next_path`. Used by /login and pages.

    Args:
        next_path: Where the login link should land afterwards (made same-site-only).
    """
    target = safe_next(next_path)
    form = ui.column().classes("w-full gap-3")
    sent = ui.column().classes("w-full gap-2")
    sent.set_visibility(False)

    with form:
        ui.label("Enter your email and we'll send you a login link. No password needed.")
        email_input = ui.input("Email").props("type=email autofocus outlined").classes("w-full")
        button = ui.button("Send me a link").classes("w-full")

    async def submit() -> None:
        email = (email_input.value or "").strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            ui.notify("Please enter a valid email address.", type="warning")
            return
        if not _cooldown.allow(email):
            ui.notify("A link was just sent to that address. Wait a minute and try again.")
            return
        settings = get_settings()
        token = make_login_token(settings.secret_key, email)
        link = f"{settings.base_url}/auth?" + urlencode({"token": token, "next": target})
        button.disable()
        button.props("loading")
        try:
            await _sender().send(login_email(email, link))
        except EmailError:
            log.exception("Login email to %s failed", email)
            _cooldown.forget(email)  # nothing was sent, so let them retry right away
            ui.notify("Sorry, we couldn't send the email. Try again later.", type="negative")
            return
        finally:
            button.props(remove="loading")
            button.enable()
        form.set_visibility(False)
        with sent:
            sent.clear()
            ui.label(f"Check your email ({email}) 📬").classes("text-lg font-semibold")
            ui.label(
                "Tap the link in it to log in. It works for 15 minutes. "
                "Not there? Check your spam folder, or check the address and try again."
            )
            ui.button("Use a different email", on_click=lambda: _reset()).props("flat")
        sent.set_visibility(True)

    def _reset() -> None:
        sent.set_visibility(False)
        form.set_visibility(True)

    button.on_click(submit)
    email_input.on("keydown.enter", submit)
