"""Sending email. Modules: `senders` (console for dev, Resend for prod), `messages` (content).

Plain Python: no NiceGUI imports.
"""

from gift_exchange.core.email.messages import login_email
from gift_exchange.core.email.senders import (
    ConsoleSender,
    Email,
    EmailError,
    EmailSender,
    ResendSender,
    make_sender,
)

__all__ = [
    "ConsoleSender",
    "Email",
    "EmailError",
    "EmailSender",
    "ResendSender",
    "login_email",
    "make_sender",
]
