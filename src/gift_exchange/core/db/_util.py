"""Small helpers shared by the db modules."""

import json
from collections.abc import Sequence


def encode_list(items: Sequence[str]) -> str:
    return json.dumps(list(items), ensure_ascii=False)


def normalize_email(email: str) -> str:
    """Lowercase and strip an email address.

    Raises:
        ValueError: If it is blank or has no "@".
    """
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("Not a valid email address.")
    return email


def require(value: str, message: str) -> None:
    if not value:
        raise ValueError(message)
