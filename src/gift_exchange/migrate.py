"""Migration CLI for this app, using DB_PATH from settings and the app's SQL files.

uv run python -m gift_exchange.migrate status   # current version, applied & pending
uv run python -m gift_exchange.migrate up       # snapshot + apply all pending
"""

import argparse
import sys

from sqlite_migrate.cli import run

from gift_exchange.config import load_settings
from gift_exchange.core.db import MIGRATIONS_DIR

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m gift_exchange.migrate")
    parser.add_argument("command", choices=["status", "up"])
    args = parser.parse_args()
    sys.exit(run(args.command, load_settings().db_path, MIGRATIONS_DIR))
