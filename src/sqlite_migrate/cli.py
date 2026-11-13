"""Command-line interface: `python -m sqlite_migrate --db PATH --dir PATH status|up`."""

import argparse
import sys
from pathlib import Path

from sqlite_migrate.engine import MigrationError, connect, migrate_database, migration_status


def run(command: str, db_path: Path, migrations_dir: Path) -> int:
    """Run a CLI command and print the result.

    Args:
        command: "status" (show current version, applied and pending migrations) or "up"
            (snapshot + apply all pending).
        db_path: The database file.
        migrations_dir: Folder holding the `NNNN_name.sql` files.

    Returns:
        Process exit code: 0 on success, 1 on a migration error (printed to stderr).
    """
    try:
        if command == "status":
            conn = connect(db_path)
            try:
                status = migration_status(conn, migrations_dir)
            finally:
                conn.close()
            print(f"Database: {db_path}")
            print(f"Current version: {status.current:04d}")
            print(f"Applied: {', '.join(f'{v:04d}' for v in status.applied) or 'none'}")
            print(f"Pending: {', '.join(m.path.name for m in status.pending) or 'none'}")
        elif command == "up":
            applied = migrate_database(db_path, migrations_dir)
            if applied:
                print(f"Applied: {', '.join(f'{v:04d}' for v in applied)}")
            else:
                print("Already up to date.")
        else:
            raise ValueError(f"Unknown command {command!r}")
    except MigrationError as exc:
        print(f"Migration error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sqlite_migrate")
    parser.add_argument("--db", type=Path, required=True, help="SQLite database file")
    parser.add_argument("--dir", type=Path, required=True, help="folder of NNNN_name.sql files")
    parser.add_argument("command", choices=["status", "up"])
    args = parser.parse_args(argv)
    return run(args.command, args.db, args.dir)
