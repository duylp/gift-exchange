# Migrations in gift-exchange

The schema is evolved with forward-only plain-SQL migrations run by the in-repo
`sqlite_migrate` engine. How the engine works (file rules, transactions, safety checks,
snapshots): `src/sqlite_migrate/README.md`.

## Where things are

- SQL files: `src/gift_exchange/core/db/migrations/NNNN_name.sql` — inside the package so
  they ship with it (e.g. in the Docker image). Path constant: `gift_exchange.core.db.MIGRATIONS_DIR`.
- Engine: `src/sqlite_migrate/` (standalone; must not import `gift_exchange`).
- Tests: `tests/sqlite_migrate/` (engine), `tests/core/db/test_schema.py` (the app's real
  migrations apply cleanly, re-applying is a no-op, and the schema's constraints hold).

## When migrations run

**At app startup, automatically** (`main.py`): safety checks → snapshot (if anything is
pending) → apply all pending migrations. If anything fails, the app does not start.

## CLI

```sh
uv run python -m gift_exchange.migrate status   # current version, applied & pending
uv run python -m gift_exchange.migrate up       # snapshot + apply all pending (same as startup)
```

Uses `DB_PATH` from settings. On the Droplet it runs inside the container
(`docker compose exec app python -m gift_exchange.migrate status`).

## Development

While a migration exists only on your laptop, edit it freely: delete the local database
file and restart (or re-run the seed script). The dev database is disposable.

**Never edit a migration after it has been applied on the Droplet** — write a new one.

## Rolling back in production

Snapshots are written next to the database as `gift.db.bak-v<version>-<timestamp>` (the 5
newest are kept).

1. Stop the app (`docker compose stop app`).
2. Copy the snapshot over the database file (`cp gift.db.bak-v3-… gift.db`).
3. Deploy the code version that matches it, and start the app.

Snapshots live on the Droplet, so they protect against bad migrations, not against losing
the Droplet — that's what the later off-Droplet R2 backups are for.
