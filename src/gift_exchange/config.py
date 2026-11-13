"""Deployment settings, read from environment variables (and `.env` in development)."""

import functools
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
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
    admins = os.environ.get("ADMIN_EMAILS", "")
    return Settings(
        dev=dev,
        secret_key=secret_key,
        admin_emails=frozenset(e.strip().lower() for e in admins.split(",") if e.strip()),
        base_url=os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/"),
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
