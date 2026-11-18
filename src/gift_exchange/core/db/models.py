"""Dataclasses returned by the db functions, and row → dataclass mappers."""

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

THEMES = ("christmas", "plain")
"""Theme names an event can use (each is styled in `ui/themes.py`)."""
DEFAULT_THEME = THEMES[0]
"""Theme for new events, and for pages not tied to one event."""


@dataclass(frozen=True)
class Section:
    """A group of clue questions, e.g. "About you", "The gift", "For the reveal".

    Attributes:
        title: Heading shown above the questions ("" for none).
        questions: The questions, in order.
        hidden: If True, the answers are kept for the party reveal and never shown to the
            Santa (e.g. "What should your Santa say when handing you the gift?").
    """

    title: str
    questions: tuple[str, ...]
    hidden: bool = False


@dataclass(frozen=True)
class Event:
    """A gift exchange.

    Attributes:
        id: Row ID.
        slug: URL part, e.g. "xmas-2026" for /e/xmas-2026.
        title: Display title.
        budget: Gift budget in whole S$.
        sections: Clue question groups asked at sign-up, in order.
        status: "open" (sign-ups open) or "matched" (final).
        matched_at: UTC ISO-8601 time matching ran, or None.
        theme: Look of the event page, one of `THEMES`.
        guesses_closed_at: UTC ISO-8601 time the organiser closed giftee guessing, or
            None while it's open (or before matching).
    """

    id: int
    slug: str
    title: str
    budget: int
    sections: tuple[Section, ...]
    status: str
    matched_at: str | None
    theme: str = DEFAULT_THEME
    guesses_closed_at: str | None = None

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    @property
    def guessing_open(self) -> bool:
        """True if Santas can guess their giftee now: matched, and not closed yet."""
        return self.status == "matched" and self.guesses_closed_at is None

    @property
    def questions(self) -> tuple[str, ...]:
        """Every question across the sections, in order (answers line up with these)."""
        return tuple(q for s in self.sections for q in s.questions)


@dataclass(frozen=True)
class Participant:
    """A person's sign-up for one event.

    Attributes:
        id: Row ID (the ID used for exclusions and matching).
        event_id: The event.
        email: Lowercased email; identifies the person (they log in with it).
        name: Real name (organiser view and reveal only).
        nickname: Anonymous name shown to their Santa.
        answers: Answers in the same order as the event's questions (all sections).
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
        clues: (section title, ((question, answer), ...)) per visible section, in order.
            Hidden (reveal-only) sections are left out.
        budget: The event's gift budget in whole S$.
    """

    nickname: str
    clues: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    budget: int


@dataclass(frozen=True)
class GuessOption:
    """A person a Santa can pick when guessing who their giftee really is.

    Attributes:
        id: The participant's row ID (what a guess stores).
        name: Their real name.
    """

    id: int
    name: str


PARTICIPANT_SELECT = """
    SELECT p.id, p.event_id, p.email, p.name, p.nickname, p.answers FROM participants AS p
"""


def event_from_row(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        budget=row["budget"],
        sections=decode_sections(row["questions"]),
        status=row["status"],
        matched_at=row["matched_at"],
        theme=row["theme"],
        guesses_closed_at=row["guesses_closed_at"],
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


def decode_sections(text: str) -> tuple[Section, ...]:
    """Parse the `events.questions` JSON: [{"title", "questions", "hidden"}, ...]."""
    return tuple(
        Section(s["title"], tuple(s["questions"]), bool(s.get("hidden", False)))
        for s in json.loads(text)
    )


def encode_sections(sections: Sequence[Section]) -> str:
    """The `events.questions` JSON for these sections (see `decode_sections`)."""
    return json.dumps(
        [{"title": s.title, "questions": list(s.questions), "hidden": s.hidden} for s in sections],
        ensure_ascii=False,
    )


def clean_sections(sections: Sequence[Section]) -> list[Section]:
    """Strip text, drop blank questions, and drop sections left with no questions."""
    cleaned = []
    for s in sections:
        questions = tuple(q.strip() for q in s.questions if q.strip())
        if questions:
            cleaned.append(Section(s.title.strip(), questions, s.hidden))
    return cleaned


def pair_answers(
    sections: Sequence[Section], answers: Sequence[str]
) -> list[tuple[Section, tuple[tuple[str, str], ...]]]:
    """Split a flat answer list back into (section, ((question, answer), ...)) groups."""
    groups, i = [], 0
    for s in sections:
        n = len(s.questions)
        groups.append((s, tuple(zip(s.questions, answers[i : i + n], strict=False))))
        i += n
    return groups
