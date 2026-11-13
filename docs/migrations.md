# Migration engine

Status: **design** (not yet implemented). Code will live in `src/gift_exchange/core/migrations.py`.

A minimal engine for evolving the SQLite schema with plain SQL files. No Alembic, no ORM —
the schema exists only in these files.

**Forward-only.** There are no `down` scripts. The undo is a database snapshot taken
automatically before every migration run (see [Backups](#backups)). A `down` script can only
restore the schema, not data an `up` dropped; restoring a snapshot gets both back, and it
means half as many files to write and test.

## Files

```
migrations/
  0001_initial.sql
  0002_add_guesses.sql
```

- Name: `NNNN_short_description.sql`. `NNNN` is a 4-digit version, starting at `0001`,
  increasing by 1 with no gaps or duplicates. The engine refuses to run otherwise.
- Plain SQL only. A script must **not** contain `BEGIN`, `COMMIT`, `ROLLBACK` or
  `PRAGMA foreign_keys` — the engine manages transactions and foreign keys (see below).
- Data changes (backfills etc.) are written in SQL in the same file. No Python migrations;
  add that only if a real need appears.
- **Never edit a migration after it has been applied on the Droplet.** Write a new migration
  instead. The engine detects edits via checksums (see below).
- While a migration exists only on your laptop, edit it freely: delete the local database
  file and restart (or re-run the seed script). The dev database is disposable.

## Tracking table

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,      -- e.g. "initial"
    checksum   TEXT NOT NULL,      -- sha256 of the script
    applied_at TEXT NOT NULL       -- UTC ISO-8601
);
```

Created by the engine itself, not by a migration. The current schema version is
`MAX(version)` (0 for an empty database).

## Applying one migration

For each pending migration, in order:

1. `PRAGMA foreign_keys = OFF` — must be set outside a transaction. Needed so scripts can use
   SQLite's table-rebuild pattern (create new table → copy → drop old → rename), which is how
   most column changes are done in SQLite.
2. `BEGIN`
3. Run the script.
4. Insert its row into `schema_migrations`.
5. `PRAGMA foreign_key_check` — if any row now breaks a foreign key, roll back and fail.
6. `COMMIT` (or `ROLLBACK` on any error — SQLite DDL is transactional, so a failed
   migration leaves no trace).
7. `PRAGMA foreign_keys = ON`

Each migration is its own transaction: if `0003` fails, `0001`–`0002` stay applied and the
error names `0003`.

Implementation note: Python's `sqlite3` `executescript()` commits any open transaction
first, so the engine uses a connection with `isolation_level=None` (autocommit) and issues
`BEGIN` / `COMMIT` itself around the script.

## Safety checks (before doing anything)

- **Bad files:** gaps, duplicates or a malformed name → error.
- **Edited migration:** an applied version whose file's checksum no longer matches the table
  → error naming the file. (Fix: undo your edit and write a new migration.)
- **Database ahead of code:** the database has a version with no file (e.g. code was rolled
  back after a migration ran) → error. The app refuses to start rather than run against a
  schema it doesn't know. (Fix: deploy the newer code, or restore a snapshot.)

## Backups

Before applying any pending migration to a database file, the engine snapshots it with
SQLite's online backup API, to `<db>.bak-v<current version>-<UTC timestamp>` next to the
database. It keeps the 5 most recent snapshots and deletes older ones. No snapshot is taken
when nothing is pending, or for an in-memory database (tests).

**To undo a migration in production:**

1. Stop the app (`docker compose stop app`).
2. Copy the snapshot over the database file (`cp gift.db.bak-v3-… gift.db`).
3. Deploy the code version that matches it, and start the app.

Snapshots live on the Droplet, so they protect against bad migrations, not against losing
the Droplet — that's what the later off-Droplet R2 backups are for.

## When migrations run

**At app startup, automatically:** safety checks → snapshot (if anything is pending) → apply
all pending migrations. If anything fails, the app does not start.

## CLI

```sh
uv run python -m gift_exchange.migrate status   # current version, applied & pending
uv run python -m gift_exchange.migrate up       # snapshot + apply all pending (same as startup)
```

Uses `DB_PATH` from settings, like the app. On the Droplet it runs inside the container
(`docker compose exec app python -m gift_exchange.migrate status`).

## Python API

```python
apply_migrations(conn, migrations_dir) -> list[int]   # versions applied
migration_status(conn, migrations_dir) -> Status      # current, applied, pending
snapshot(db_path, keep=5) -> Path                      # backup file written
```

`apply_migrations` and `migration_status` take an open connection, so tests can use
`:memory:`. Callers that work on a file (app startup, CLI) take the snapshot first.

## Testing

- The **real** `migrations/` folder applies cleanly to an empty database, and applying again
  is a no-op.
- Engine behaviour with temporary migration folders: ordering, skipping applied ones, a
  failing migration rolls back only itself, gap / duplicate / bad-name errors, checksum
  mismatch, database-ahead-of-code, foreign-key violation is caught.
- Snapshot: file is a valid copy of the database; only the 5 newest are kept.

## Not doing (v1)

- `down` / revert scripts — restore a snapshot instead.
- Python (non-SQL) migrations.
- Locking against concurrent migrators — there is only ever one app process (NiceGUI runs a
  single worker).
- Squashing old migrations.
