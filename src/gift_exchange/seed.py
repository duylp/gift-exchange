"""Fill the local database with a sample event for UI work.

    uv run python -m gift_exchange.seed

Creates event `xmas-2026` with 8 fake participants (emails @example.com) and one couple
exclusion, left open (not matched) so the admin page can be tried. Does nothing if the
event already exists. For development only — refuses to run unless DEV=1.
"""

import sys

from sqlite_migrate import migrate_database

from gift_exchange.config import load_settings
from gift_exchange.core import db

SLUG = "xmas-2026"
QUESTIONS = [
    "What do you do for fun?",
    "Favourite colour?",
    "Something you'd love but would never buy yourself?",
    "Anything you dislike or are allergic to?",
]
PEOPLE = [
    # (name, nickname, answers)
    ("Alex Tan", "Rudolph", ["Bouldering", "Green", "A good chef's knife", "Nuts"]),
    ("Bea Lim", "Snowflake", ["Baking", "Pink", "Fancy tea", "Nothing"]),
    ("Chen Wei", "Tinsel", ["Board games", "Blue", "Noise-cancelling earbuds", "Scented things"]),
    ("Dana Ng", "Comet", ["Running", "Orange", "Running socks", "Chocolate"]),
    ("Eli Koh", "Pinecone", ["Photography", "Black", "Film rolls", "Mugs"]),
    ("Fiona Goh", "Mistletoe", ["Gardening", "Yellow", "A bonsai kit", "Candles"]),
    ("Gabe Ong", "Jingle", ["Gaming", "Purple", "A mechanical keyboard", "Clothes"]),
    ("Hana Yeo", "Cocoa", ["Reading", "Red", "A Kindle cover", "Perfume"]),
]
COUPLE = ("Alex Tan", "Bea Lim")


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

        event = db.create_event(conn, SLUG, "Christmas 2026 🎄", 30, QUESTIONS)
        ids = {}
        for name, nickname, answers in PEOPLE:
            email = name.lower().replace(" ", ".") + "@example.com"
            user = db.get_or_create_user(conn, email)
            ids[name] = db.join_event(conn, event.id, user.id, name, nickname, answers).id
        db.add_exclusion(conn, event.id, ids[COUPLE[0]], ids[COUPLE[1]])
        print(
            f"Created '{SLUG}' with {len(PEOPLE)} participants and "
            f"{COUPLE[0]} ✕ {COUPLE[1]} excluded, in {settings.db_path}."
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
