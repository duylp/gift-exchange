import itsdangerous.timed
import pytest

from gift_exchange.core.auth import (
    LOGIN_LINK_MAX_AGE,
    SESSION_MAX_AGE,
    Cooldown,
    LinkExpired,
    LinkInvalid,
    is_admin,
    make_login_token,
    make_session,
    read_login_token,
    read_session,
    safe_next,
)

KEY = "test-secret"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Controls the time itsdangerous sees: set clock[0] to move time."""
    now = [1_800_000_000.0]
    monkeypatch.setattr(itsdangerous.timed.time, "time", lambda: now[0])
    return now


# --- login links ----------------------------------------------------------------------


def test_login_token_round_trip_normalises_email() -> None:
    assert read_login_token(KEY, make_login_token(KEY, " Ann@Example.COM ")) == "ann@example.com"


def test_login_token_reusable_within_window(clock: list[float]) -> None:
    token = make_login_token(KEY, "ann@example.com")
    clock[0] += LOGIN_LINK_MAX_AGE - 1
    assert read_login_token(KEY, token) == "ann@example.com"
    assert read_login_token(KEY, token) == "ann@example.com"  # second use still fine


def test_login_token_expires(clock: list[float]) -> None:
    token = make_login_token(KEY, "ann@example.com")
    clock[0] += LOGIN_LINK_MAX_AGE + 1
    with pytest.raises(LinkExpired):
        read_login_token(KEY, token)


@pytest.mark.parametrize("mangle", [lambda t: t[:-2] + "xx", lambda t: t[:10], lambda t: ""])
def test_login_token_tampered_is_invalid(mangle) -> None:
    with pytest.raises(LinkInvalid):
        read_login_token(KEY, mangle(make_login_token(KEY, "ann@example.com")))


def test_login_token_from_other_key_is_invalid() -> None:
    with pytest.raises(LinkInvalid):
        read_login_token(KEY, make_login_token("other-key", "ann@example.com"))


# --- sessions ----------------------------------------------------------------------------


def test_session_round_trip() -> None:
    assert read_session(KEY, make_session(KEY, "Ann@Example.com")) == "ann@example.com"


def test_session_missing_or_bad_is_none() -> None:
    assert read_session(KEY, None) is None
    assert read_session(KEY, "") is None
    assert read_session(KEY, "garbage") is None
    assert read_session("other-key", make_session(KEY, "ann@example.com")) is None


def test_session_expires_after_30_days(clock: list[float]) -> None:
    cookie = make_session(KEY, "ann@example.com")
    clock[0] += SESSION_MAX_AGE - 1
    assert read_session(KEY, cookie) == "ann@example.com"
    clock[0] += 2
    assert read_session(KEY, cookie) is None


def test_login_token_and_session_are_not_interchangeable() -> None:
    assert read_session(KEY, make_login_token(KEY, "ann@example.com")) is None
    with pytest.raises(LinkInvalid):
        read_login_token(KEY, make_session(KEY, "ann@example.com"))


# --- guards -----------------------------------------------------------------------------


def test_is_admin() -> None:
    admins = frozenset({"admin@example.com"})
    assert is_admin("Admin@Example.com", admins)
    assert not is_admin("ann@example.com", admins)
    assert not is_admin(None, admins)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("/e/xmas-2026", "/e/xmas-2026"),
        ("/admin?tab=1", "/admin?tab=1"),
        (None, "/"),
        ("", "/"),
        ("https://evil.example", "/"),
        ("//evil.example", "/"),
        ("/\\evil.example", "/"),
        ("javascript:alert(1)", "/"),
        ("e/xmas", "/"),
        ("/\t/evil.example", "/"),
        ("/\n/evil.example", "/"),
        ("/\r/evil.example", "/"),
        ("/e/x\x7f", "/"),
    ],
)
def test_safe_next(given: str | None, expected: str) -> None:
    assert safe_next(given) == expected


def test_cooldown() -> None:
    now = [0.0]
    cd = Cooldown(60, clock=lambda: now[0])
    assert cd.allow("a")
    assert not cd.allow("a")
    assert cd.allow("b")  # per key
    now[0] = 59
    assert not cd.allow("a")
    now[0] = 60
    assert cd.allow("a")


def test_cooldown_forget_allows_retry() -> None:
    cd = Cooldown(60, clock=lambda: 0.0)
    assert cd.allow("a")
    cd.forget("a")
    assert cd.allow("a")
    cd.forget("never-seen")  # no error
