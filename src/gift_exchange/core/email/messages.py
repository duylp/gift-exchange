"""The emails the app sends."""

from html import escape

from gift_exchange.core.auth import LOGIN_LINK_MAX_AGE
from gift_exchange.core.email.senders import Email


def login_email(to: str, link: str) -> Email:
    """The magic-link email.

    Args:
        to: Recipient address.
        link: Full login URL, e.g. "https://santa.mangobello.dev/auth?token=…&next=/e/xmas-2026".
    """
    minutes = LOGIN_LINK_MAX_AGE // 60
    text = (
        "Hi!\n\n"
        f"Tap this link to log in to the gift exchange (it works for {minutes} minutes):\n\n"
        f"{link}\n\n"
        "If you didn't ask for this, you can ignore this email.\n\n— Santa 🎅"
    )
    safe_link = escape(link, quote=True)
    html = (
        "<p>Hi!</p>"
        f"<p>Tap the button to log in to the gift exchange (it works for {minutes} minutes):</p>"
        f'<p><a href="{safe_link}" style="display:inline-block;padding:12px 20px;'
        "background:#b91c1c;color:#fff;border-radius:8px;text-decoration:none;"
        'font-weight:600">Log in</a></p>'
        f'<p style="color:#666;font-size:13px">Or copy this link: {safe_link}</p>'
        "<p>If you didn't ask for this, you can ignore this email.</p><p>— Santa 🎅</p>"
    )
    return Email(to=to, subject="Your gift exchange login link", text=text, html=html)
