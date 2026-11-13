import asyncio
import json

import httpx
import pytest

from gift_exchange.core.email import (
    ConsoleSender,
    EmailError,
    ResendSender,
    login_email,
    make_sender,
)

LINK = "https://santa.example/auth?token=abc&next=%2Fe%2Fxmas-2026"


def test_login_email_contains_link_in_both_bodies() -> None:
    email = login_email("ann@example.com", LINK)
    assert email.to == "ann@example.com"
    assert LINK in email.text
    assert "token=abc&amp;next=%2Fe%2Fxmas-2026" in email.html  # HTML-escaped
    assert "15 minutes" in email.text


def test_login_email_escapes_html() -> None:
    email = login_email("a@example.com", 'https://x/"><script>')
    assert "<script>" not in email.html


def test_console_sender_prints(capsys: pytest.CaptureFixture[str]) -> None:
    asyncio.run(ConsoleSender().send(login_email("ann@example.com", LINK)))
    out = capsys.readouterr().out
    assert "ann@example.com" in out and LINK in out


def test_resend_sender_posts_expected_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "abc-123"})

    sender = ResendSender(
        "re_key", "Santa <santa@mail.example>", transport=httpx.MockTransport(handler)
    )
    asyncio.run(sender.send(login_email("ann@example.com", LINK)))

    (req,) = seen
    assert req.method == "POST" and str(req.url) == "https://api.resend.com/emails"
    assert req.headers["authorization"] == "Bearer re_key"
    assert req.headers["user-agent"] == "gift-exchange/0.1"
    body = json.loads(req.content)
    assert body["from"] == "Santa <santa@mail.example>"
    assert body["to"] == ["ann@example.com"]
    assert body["subject"] and LINK in body["text"] and body["html"]


def test_resend_error_status_raises() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(403, json={"message": "domain not verified"})
    )
    with pytest.raises(EmailError, match="403"):
        asyncio.run(
            ResendSender("k", "s@x", transport=transport).send(login_email("a@x.com", LINK))
        )


def test_resend_network_error_raises() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(EmailError, match="reach Resend"):
        sender = ResendSender("k", "s@x", transport=httpx.MockTransport(boom))
        asyncio.run(sender.send(login_email("a@x.com", LINK)))


def test_make_sender() -> None:
    assert isinstance(make_sender(True, "", ""), ConsoleSender)
    assert isinstance(make_sender(False, "re_key", "s@x"), ResendSender)
