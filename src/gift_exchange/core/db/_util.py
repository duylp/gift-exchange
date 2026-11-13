"""Small helpers shared by the db modules."""

import json
from collections.abc import Sequence


def clean_list(items: Sequence[str]) -> list[str]:
    return [s.strip() for s in items if s.strip()]


def encode_list(items: Sequence[str]) -> str:
    return json.dumps(list(items), ensure_ascii=False)


def require(value: str, message: str) -> None:
    if not value:
        raise ValueError(message)
