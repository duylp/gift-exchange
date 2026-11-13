"""Ways to send an email: print it (development) or send it through Resend (production)."""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
USER_AGENT = "gift-exchange/0.1"  # Resend rejects requests without a User-Agent (403)


class EmailError(Exception):
    """An email could not be sent. The message is for logs, not for users."""


@dataclass(frozen=True)
class Email:
    """One message to send.

    Attributes:
        to: Recipient address.
        subject: Subject line.
        text: Plain-text body.
        html: HTML body.
    """

    to: str
    subject: str
    text: str
    html: str


class EmailSender(Protocol):
    """Anything that can send an `Email`."""

    async def send(self, email: Email) -> None:
        """Send `email`, raising EmailError on failure."""
        ...


class ConsoleSender:
    """Development sender: prints the email (including any login link) to the terminal."""

    async def send(self, email: Email) -> None:
        print(f"\n--- email to {email.to}: {email.subject} ---\n{email.text}\n---\n", flush=True)


class ResendSender:
    """Production sender using Resend's HTTP API (https://resend.com/docs/api-reference).

    Args:
        api_key: Resend API key (RESEND_API_KEY).
        sender: The `from` address, e.g. "Santa <santa@mail.duylp.dev>"; its domain must be
            verified in Resend.
        timeout: Seconds to wait for Resend before giving up.
        transport: httpx transport override, for tests only.
    """

    def __init__(
        self,
        api_key: str,
        sender: str,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout = timeout
        self._transport = transport

    async def send(self, email: Email) -> None:
        """Send `email` through Resend.

        Raises:
            EmailError: On a network error or any non-2xx response (e.g. unverified domain,
                bad key, rate or daily quota exceeded).
        """
        payload = {
            "from": self._sender,
            "to": [email.to],
            "subject": email.subject,
            "text": email.text,
            "html": email.html,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "User-Agent": USER_AGENT}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as c:
                response = await c.post(RESEND_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise EmailError(f"Could not reach Resend: {exc}") from exc
        if response.is_error:
            raise EmailError(f"Resend returned {response.status_code}: {response.text[:300]}")
        log.info("Sent email %r via Resend (id %s)", email.subject, response.json().get("id"))


def make_sender(dev: bool, resend_api_key: str, email_from: str) -> EmailSender:
    """Pick the sender for the environment.

    Args:
        dev: True in development (DEV=1): print emails instead of sending.
        resend_api_key: Resend API key (required when not dev).
        email_from: The `from` address (required when not dev).
    """
    if dev:
        return ConsoleSender()
    return ResendSender(resend_api_key, email_from)
