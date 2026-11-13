"""Fill the local database with a sample event for UI work.

    uv run python -m gift_exchange.seed

Creates event `xmas-2026` (a visible and a hidden reveal-only question section) with 8
fake participants (emails @example.com) and one couple exclusion, left open (not matched)
so the admin page can be tried. Alex Tan (alex.tan@example.com) is meant to be the admin:
put that email in ADMIN_EMAILS (as `.env.example` does) to be both organiser and participant. Does nothing if the event already exists. For development
only — refuses to run unless DEV=1.
"""

import sys

from sqlite_migrate import migrate_database

from gift_exchange.config import load_settings
from gift_exchange.core import db

SLUG = "xmas-2026"
SECTIONS = [
    db.Section(
        "About you",
        (
            "What do you do for fun?",
            "Favourite colour?",
            "Something you'd love but would never buy yourself?",
            "Anything you dislike or are allergic to?",
        ),
    ),
    db.Section(
        "For the reveal",
        ("When your Santa hands you the gift, what should they say?",),
        hidden=True,
    ),
]
PEOPLE = [
    # (name, nickname, answers: the 4 clues, then the hidden reveal prompt)
    ("Alex Tan", "Rudolph", ["Bouldering", "Green", "A good chef's knife", "Nuts", "Ho ho ho!"]),
    ("Bea Lim", "Snowflake", ["Baking", "Pink", "Fancy tea", "Nothing", "Surprise!"]),
    (
        "Chen Wei",
        "Tinsel",
        ["Board games", "Blue", "Noise-cancelling earbuds", "Scented things", "Merry Xmas"],
    ),
    ("Dana Ng", "Comet", ["Running", "Orange", "Running socks", "Chocolate", "Catch!"]),
    ("Eli Koh", "Pinecone", ["Photography", "Black", "Film rolls", "Mugs", "Say cheese"]),
    ("Fiona Goh", "Mistletoe", ["Gardening", "Yellow", "A bonsai kit", "Candles", "Grow up!"]),
    ("Gabe Ong", "Jingle", ["Gaming", "Purple", "A mechanical keyboard", "Clothes", "GG"]),
    ("Hana Yeo", "Cocoa", ["Reading", "Red", "A Kindle cover", "Perfume", "The end"]),
]
COUPLE = ("Alex Tan", "Bea Lim")
ADMIN = "Alex Tan"


def _email(name: str) -> str:
    return name.lower().replace(" ", ".") + "@example.com"


def main() -> int:
    settings = load_settings()
    if not settings.dev:
        print("Refusing to seed: DEV is not 1.", file=sys.stderr)
        return 1
    migrate_database(settings.db_path, db.MIGRATIONS_DIR)
    conn = db.connect(settings.db_path)
    try:
        try:
            db.get_event_by_slug(conn, SLUG)
            print(f"Event '{SLUG}' already exists; nothing to do.")
            return 0
        except db.NotFound:
            pass

        event = db.create_event(conn, SLUG, "Christmas 2026 🎄", 30, SECTIONS, theme="christmas")
        try:
            ids = {}
            for name, nickname, answers in PEOPLE:
                ids[name] = db.join_event(conn, event.id, _email(name), name, nickname, answers).id
            db.add_exclusion(conn, event.id, ids[COUPLE[0]], ids[COUPLE[1]])
        except BaseException:
            db.delete_event(conn, event.id)  # all-or-nothing: next run starts clean
            raise
        print(
            f"Created '{SLUG}' with {len(PEOPLE)} participants and "
            f"{COUPLE[0]} ✕ {COUPLE[1]} excluded, in {settings.db_path}."
        )
        admin = _email(ADMIN)
        if admin in settings.admin_emails:
            print(f"Log in as {admin} (admin and participant).")
        else:
            print(f"Tip: set ADMIN_EMAILS={admin} in .env to log in as admin {ADMIN}.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
