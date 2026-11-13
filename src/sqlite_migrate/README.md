# sqlite_migrate

A minimal, forward-only migration engine for SQLite: numbered plain-SQL files, one
transaction per migration, safety checks, and an automatic database snapshot before every
run. Standard library only.

**Standalone by design:** it must not import anything from the app that uses it, so it can
move to its own repo. A test enforces this.

**Forward-only.** Migrations are only ever applied. To roll one back, restore the snapshot
taken automatically before the run (see [Snapshots](#snapshots)).

## Usage

```python
from pathlib import Path
from sqlite_migrate import migrate_database

applied = migrate_database(Path("data/app.db"), Path("my_app/migrations"))  # at app startup
```

```sh
python -m sqlite_migrate --db data/app.db --dir my_app/migrations status
python -m sqlite_migrate --db data/app.db --dir my_app/migrations up
```

## Migration files

```
migrations/
  0001_initial.sql
  0002_add_guesses.sql
```

- Name: `NNNN_short_description.sql` (lowercase, digits, underscores). `NNNN` is a 4-digit
  version starting at `0001`, increasing by 1 with no gaps or duplicates. Non-`.sql` files
  (e.g. a README) are ignored.
- Plain SQL only. Data changes (backfills etc.) are written in SQL in the same file.
- A script must **not** contain `BEGIN;`, `BEGIN TRANSACTION`, `COMMIT`, `ROLLBACK`,
  `END TRANSACTION` or `PRAGMA foreign_keys` — the engine manages transactions and foreign
  keys. These are matched at the start of a line, so a trigger's `BEGIN … END` body is fine.
- **Never edit a migration once it has been applied to a database you care about.** Write a
  new one. The engine detects edits via checksums.

## Tracking table

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,      -- e.g. "initial"
    checksum   TEXT NOT NULL,      -- sha256 of the script
    applied_at TEXT NOT NULL       -- UTC ISO-8601
);
```

Created by the engine itself, not by a migration. The current version is `MAX(version)`
(0 for an empty database).

## Applying one migration

For each pending migration, in order:

1. `PRAGMA foreign_keys = OFF` — must be set outside a transaction. Lets scripts use
   SQLite's table-rebuild pattern (create new table → copy → drop old → rename), which is how
   most column changes are done in SQLite.
2. `BEGIN`, then the script.
3. Insert its row into `schema_migrations`.
4. `PRAGMA foreign_key_check` — if any row now breaks a foreign key, roll back and fail.
5. `COMMIT` (or `ROLLBACK` on any error — SQLite DDL is transactional, so a failed migration
   leaves no trace).
6. `PRAGMA foreign_keys = ON`

Each migration is its own transaction: if `0003` fails, `0001`–`0002` stay applied and the
error names `0003`.

Implementation note: connections must be in autocommit mode (`isolation_level=None`; use
`sqlite_migrate.connect` or check yours). Python's `sqlite3` `executescript()` implicitly
commits any open transaction before running, so `BEGIN` is sent **in the same
`executescript()` call** as the script; the tracking insert, FK check and `COMMIT` then use
plain `execute()`.

## Safety checks (before doing anything)

- **Bad files:** malformed name, gaps, duplicates, or engine-owned statements → error.
- **Edited migration:** an applied version whose file's checksum no longer matches → error
  naming the file. (Fix: undo the edit and write a new migration.)
- **Database ahead of code:** the database has a version with no file (e.g. code was rolled
  back after a migration ran) → error, rather than running against an unknown schema.
  (Fix: deploy the newer code, or restore a snapshot.)
- **Wrong connection:** not in autocommit mode, or inside an open transaction → error.

## Snapshots

`migrate_database` snapshots the database file with SQLite's online backup API before
applying anything, to `<db>.bak-v<current version>-<UTC timestamp>` next to it, keeping the
5 most recent. No snapshot when nothing is pending or the file didn't exist yet.
`apply_migrations` alone never snapshots.

To roll back: stop the app, copy the snapshot over the database file, and run the code
version that matches it.

## API

```python
migrate_database(db_path, migrations_dir) -> list[int]  # checks → snapshot → apply
apply_migrations(conn, migrations_dir) -> list[int]     # versions applied, no snapshot
migration_status(conn, migrations_dir) -> Status        # current, applied, pending + checks
load_migrations(migrations_dir) -> list[Migration]      # read + validate files
snapshot(db_path, version, keep=5) -> Path              # backup file written
connect(db_path) -> sqlite3.Connection                  # autocommit, foreign keys on
MigrationError                                          # every failure the engine reports
```

`apply_migrations` and `migration_status` take an open connection, so tests can use
`:memory:`.

## Not doing

- Down / revert scripts — restore a snapshot instead.
- Python (non-SQL) migrations.
- Locking against concurrent migrators — assumes one process migrates at a time.
- Squashing old migrations.

## Extracting to its own repo

1. Copy `src/sqlite_migrate/` and `tests/sqlite_migrate/` (or `git filter-repo` them to keep
   history) into a new repo and add a `pyproject.toml`.
2. In the app: `uv add git+https://github.com/<owner>/sqlite-migrate` (or from PyPI), remove
   the in-repo copy, and drop `src/sqlite_migrate` from `[tool.hatch.build.targets.wheel]`
   and the `known-third-party` isort setting. No app code changes.
