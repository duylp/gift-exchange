"""Migration CLI.

uv run python -m gift_exchange.migrate status   # current version, applied & pending
uv run python -m gift_exchange.migrate up       # snapshot + apply all pending
"""

import argparse
import sys

from gift_exchange.config import load_settings
from gift_exchange.core.db import connect
from gift_exchange.core.migrations import MigrationError, migrate_database, migration_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m gift_exchange.migrate")
    parser.add_argument("command", choices=["status", "up"])
    args = parser.parse_args(argv)
    db_path = load_settings().db_path

    try:
        if args.command == "status":
            conn = connect(db_path)
            try:
                status = migration_status(conn)
            finally:
                conn.close()
            print(f"Database: {db_path}")
            print(f"Current version: {status.current:04d}")
            print(f"Applied: {', '.join(f'{v:04d}' for v in status.applied) or 'none'}")
            print(f"Pending: {', '.join(m.path.name for m in status.pending) or 'none'}")
        else:
            applied = migrate_database(db_path)
            if applied:
                print(f"Applied: {', '.join(f'{v:04d}' for v in applied)}")
            else:
                print("Already up to date.")
    except MigrationError as exc:
        print(f"Migration error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
