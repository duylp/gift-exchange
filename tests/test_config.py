import pytest

from gift_exchange.config import load_settings


def test_requires_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gift_exchange.config.load_dotenv", lambda: None)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_settings()


def test_parses_admin_emails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gift_exchange.config.load_dotenv", lambda: None)
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("DEV", "1")
    monkeypatch.setenv("ADMIN_EMAILS", " A@x.com, b@y.com ,")
    assert load_settings().admin_emails == {"a@x.com", "b@y.com"}
