"""Deployment settings, read from environment variables (and `.env` in development)."""

import functools
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Deployment settings (see .env.example).

    Attributes:
        dev: DEV=1: auto-reload, emails printed instead of sent, relaxed requirements.
        secret_key: SECRET_KEY, signs login links and session cookies.
        admin_emails: ADMIN_EMAILS, lowercased; these people get the admin pages.
        base_url: BASE_URL without trailing slash, used to build links in emails.
        db_path: DB_PATH, the SQLite file.
        resend_api_key: RESEND_API_KEY (required when not dev).
        email_from: EMAIL_FROM, the sender address (required when not dev).
        host: HOST to listen on.
        port: PORT to listen on.
    """

    dev: bool
    secret_key: str
    admin_emails: frozenset[str]
    base_url: str
    db_path: Path
    resend_api_key: str
    email_from: str
    host: str
    port: int


def load_settings() -> Settings:
    """Read settings from the environment, loading `.env` first if present.

    Returns:
        The settings.

    Raises:
        RuntimeError: If SECRET_KEY is missing, or (when DEV is not 1) RESEND_API_KEY,
            EMAIL_FROM or BASE_URL is missing, or BASE_URL doesn't start with https://.
    """
    load_dotenv()
    secret_key = os.environ.get("SECRET_KEY", "")
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not set (copy .env.example to .env)")
    dev = os.environ.get("DEV", "0") == "1"
    resend_api_key = os.environ.get("RESEND_API_KEY", "")
    email_from = os.environ.get("EMAIL_FROM", "").strip()
    if not dev and not resend_api_key:
        raise RuntimeError("RESEND_API_KEY is required when DEV is not 1")
    if not dev and not email_from:
        raise RuntimeError("EMAIL_FROM is required when DEV is not 1")
    base_url = os.environ.get("BASE_URL", "").strip().rstrip("/")
    if not dev and not base_url.startswith("https://"):
        raise RuntimeError("BASE_URL must be set to an https:// URL when DEV is not 1")
    admins = os.environ.get("ADMIN_EMAILS", "")
    return Settings(
        dev=dev,
        secret_key=secret_key,
        admin_emails=frozenset(e.strip().lower() for e in admins.split(",") if e.strip()),
        base_url=base_url or "http://localhost:8080",
        db_path=Path(os.environ.get("DB_PATH", "data/gift.db")),
        resend_api_key=resend_api_key,
        email_from=email_from,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
    )


@functools.cache
def get_settings() -> Settings:
    """The app's settings, loaded once per process (use this from UI code)."""
    return load_settings()
