"""Dataclasses returned by the db functions, and row → dataclass mappers."""

import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    """A gift exchange.

    Attributes:
        id: Row ID.
        slug: URL part, e.g. "xmas-2026" for /e/xmas-2026.
        title: Display title.
        budget: Gift budget in whole S$.
        questions: Clue questions asked at sign-up, in order.
        status: "open" (sign-ups open) or "matched" (final).
        matched_at: UTC ISO-8601 time matching ran, or None.
    """

    id: int
    slug: str
    title: str
    budget: int
    questions: tuple[str, ...]
    status: str
    matched_at: str | None

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True)
class Participant:
    """A person's sign-up for one event.

    Attributes:
        id: Row ID (the ID used for exclusions and matching).
        event_id: The event.
        email: Lowercased email; identifies the person (they log in with it).
        name: Real name (organiser view and reveal only).
        nickname: Anonymous name shown to their Santa.
        answers: Answers in the same order as the event's questions.
    """

    id: int
    event_id: int
    email: str
    name: str
    nickname: str
    answers: tuple[str, ...]


@dataclass(frozen=True)
class Giftee:
    """What a Santa sees about the person they give to.

    Attributes:
        nickname: The giftee's anonymous nickname (never their real name).
        clues: (question, answer) pairs, in question order.
        budget: The event's gift budget in whole S$.
    """

    nickname: str
    clues: tuple[tuple[str, str], ...]
    budget: int


PARTICIPANT_SELECT = """
    SELECT p.id, p.event_id, p.email, p.name, p.nickname, p.answers FROM participants AS p
"""


def event_from_row(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        budget=row["budget"],
        questions=tuple(json.loads(row["questions"])),
        status=row["status"],
        matched_at=row["matched_at"],
    )


def participant_from_row(row: sqlite3.Row) -> Participant:
    return Participant(
        id=row["id"],
        event_id=row["event_id"],
        email=row["email"],
        name=row["name"],
        nickname=row["nickname"],
        answers=tuple(json.loads(row["answers"])),
    )
