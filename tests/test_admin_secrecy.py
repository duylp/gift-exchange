"""Secrecy guard: the admin pages never show nicknames.

The admin may also be a participant. Their giftee's nickname is on their event page, so a
nickname → name list on the admin page would tell them who their giftee is.
"""

import io
import tokenize
from pathlib import Path

import gift_exchange


def _code_without_comments(path: Path) -> str:
    tokens = tokenize.generate_tokens(io.StringIO(path.read_text()).readline)
    return " ".join(t.string for t in tokens if t.type != tokenize.COMMENT)


def test_admin_pages_never_mention_nicknames() -> None:
    admin_page = Path(gift_exchange.__file__).parent / "ui" / "admin_page.py"
    assert "nickname" not in _code_without_comments(admin_page).lower()
