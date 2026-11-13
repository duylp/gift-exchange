"""Forward-only SQL migration engine for SQLite. See README.md in this package."""

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SNAPSHOTS_TO_KEEP = 5

_FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
# Statements the engine owns. Matched per line so CREATE TRIGGER ... BEGIN ... END is fine.
_FORBIDDEN = re.compile(
    r"^\s*(BEGIN(\s+(DEFERRED|IMMEDIATE|EXCLUSIVE))?(\s+TRANSACTION)?\s*;"
    r"|COMMIT\b|ROLLBACK\b|END\s+TRANSACTION\b|PRAGMA\s+foreign_keys\b)",
    re.IGNORECASE | re.MULTILINE,
)

_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    checksum   TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


class MigrationError(Exception):
    """Migrations can't be applied safely; the message says why and what to do."""


@dataclass(frozen=True)
class Migration:
    """One migration file.

    Attributes:
        version: The 4-digit number from the file name, as an int (e.g. 1 for `0001_…`).
        name: The description part of the file name (e.g. "initial").
        path: Where the file is.
        sql: The file's contents.
        checksum: sha256 hex digest of `sql`, stored when applied to detect later edits.
    """

    version: int
    name: str
    path: Path
    sql: str
    checksum: str


@dataclass(frozen=True)
class Status:
    """Where a database stands relative to the migration files.

    Attributes:
        current: Highest applied version (0 for an empty database).
        applied: Versions recorded in `schema_migrations`, ascending.
        pending: Migrations not yet applied, in the order they will run.
    """

    current: int
    applied: tuple[int, ...]
    pending: tuple[Migration, ...]


def load_migrations(migrations_dir: Path) -> list[Migration]:
    """Read and validate all migration files in a folder.

    Args:
        migrations_dir: Folder holding `NNNN_name.sql` files. Files that don't end in
            `.sql` (e.g. README) are ignored.

    Returns:
        Migrations sorted by version.

    Raises:
        MigrationError: If a `.sql` file is badly named, versions have gaps or duplicates
            or don't start at 0001, or a script contains a statement the engine owns
            (BEGIN / COMMIT / ROLLBACK / PRAGMA foreign_keys).
    """
    migrations = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if not match:
            raise MigrationError(
                f"Bad migration file name {path.name!r}: expected NNNN_lowercase_name.sql"
            )
        sql = path.read_text(encoding="utf-8")
        if bad := _FORBIDDEN.search(sql):
            raise MigrationError(
                f"{path.name} contains {bad.group(0).strip()!r}; the engine manages "
                "transactions and foreign keys, remove it."
            )
        migrations.append(
            Migration(
                version=int(match.group(1)),
                name=match.group(2),
                path=path,
                sql=sql,
                checksum=hashlib.sha256(sql.encode()).hexdigest(),
            )
        )
    migrations.sort(key=lambda m: m.version)
    expected = list(range(1, len(migrations) + 1))
    actual = [m.version for m in migrations]
    if actual != expected:
        raise MigrationError(
            f"Migration versions must be 0001, 0002, … with no gaps or duplicates; "
            f"found {', '.join(f'{v:04d}' for v in actual)}"
        )
    return migrations


def migration_status(conn: sqlite3.Connection, migrations_dir: Path) -> Status:
    """Compare the database with the migration files, running all safety checks.

    Args:
        conn: Connection in autocommit mode (`isolation_level=None`), e.g. from
            `connect`. The tracking table is created if missing.
        migrations_dir: Folder holding the migration files.

    Returns:
        The database's current version, applied versions and pending migrations.

    Raises:
        MigrationError: If the files are invalid (see `load_migrations`), the database has
            a version with no file (database ahead of code), or an applied migration's
            file has been edited since (checksum mismatch); or `conn` is not in
            autocommit mode.
    """
    _check_connection(conn)
    migrations = load_migrations(migrations_dir)
    conn.execute(_TRACKING_TABLE)
    rows = conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
    applied = {row[0]: row[1] for row in rows}
    by_version = {m.version: m for m in migrations}

    unknown = sorted(set(applied) - set(by_version))
    if unknown:
        raise MigrationError(
            f"Database has migration(s) {', '.join(f'{v:04d}' for v in unknown)} that this "
            "code doesn't know: the database is ahead of the code. Deploy the newer code, "
            "or restore a snapshot."
        )
    for version, checksum in applied.items():
        if by_version[version].checksum != checksum:
            raise MigrationError(
                f"{by_version[version].path.name} was edited after being applied. Undo the "
                "edit and put the change in a new migration."
            )

    return Status(
        current=max(applied, default=0),
        applied=tuple(sorted(applied)),
        pending=tuple(m for m in migrations if m.version not in applied),
    )


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[int]:
    """Apply all pending migrations, each in its own transaction.

    Does not take a snapshot; use `migrate_database` for a database file.

    Args:
        conn: Connection in autocommit mode (`isolation_level=None`, e.g. from `connect`),
            not inside a transaction.
        migrations_dir: Folder holding the migration files.

    Returns:
        Versions applied, in order (empty if none were pending).

    Raises:
        MigrationError: If a safety check fails (see `migration_status`), or a migration
            fails or leaves a foreign-key violation. Migrations before the failing one stay
            applied; the failing one is rolled back completely.
    """
    _check_connection(conn)
    applied = []
    for migration in migration_status(conn, migrations_dir).pending:
        _apply_one(conn, migration)
        applied.append(migration.version)
    return applied


def _apply_one(conn: sqlite3.Connection, migration: Migration) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")  # no effect inside a transaction, so set first
    try:
        # BEGIN must be in the same executescript() call: a separate executescript()
        # would implicitly COMMIT an open transaction before running.
        conn.executescript(f"BEGIN;\n{migration.sql}\n;")
        conn.execute(
            "INSERT INTO schema_migrations (version, name, checksum, applied_at) "
            "VALUES (?, ?, ?, ?)",
            (migration.version, migration.name, migration.checksum, _utc_now().isoformat()),
        )
        if violations := conn.execute("PRAGMA foreign_key_check").fetchall():
            tables = sorted({row[0] for row in violations})
            raise MigrationError(
                f"{migration.path.name} leaves foreign-key violations in: {', '.join(tables)}"
            )
        conn.execute("COMMIT")
    except Exception as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError(f"{migration.path.name} failed: {exc}") from exc
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def snapshot(db_path: Path, version: int, keep: int = SNAPSHOTS_TO_KEEP) -> Path:
    """Copy a database file to a timestamped backup next to it, pruning old backups.

    Uses SQLite's online backup API, so the copy is consistent even if the database is
    open elsewhere.

    Args:
        db_path: The database file to copy. Must exist.
        version: The database's current schema version, recorded in the backup's name.
        keep: How many backups of this database to keep; older ones are deleted.

    Returns:
        Path of the backup written: `<db name>.bak-v<version>-<UTC timestamp>`.
    """
    stamp = _utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    dest = db_path.with_name(f"{db_path.name}.bak-v{version}-{stamp}")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    backups = sorted(
        db_path.parent.glob(f"{db_path.name}.bak-v*-*"),
        key=lambda p: p.name.rsplit("-", 1)[1],
    )
    for old in backups[:-keep]:
        old.unlink()
    return dest


def migrate_database(db_path: Path, migrations_dir: Path) -> list[int]:
    """Bring a database file up to date: safety checks → snapshot → apply pending.

    The usual entry point for an app's startup and for `python -m sqlite_migrate up`.
    A snapshot is only taken if something is pending and the file already existed.

    Args:
        db_path: The database file. Created (empty) if it doesn't exist.
        migrations_dir: Folder holding the migration files.

    Returns:
        Versions applied, in order (empty if already up to date).

    Raises:
        MigrationError: See `migration_status` and `apply_migrations`.
    """
    existed = db_path.exists()
    conn = connect(db_path)
    try:
        status = migration_status(conn, migrations_dir)
        if not status.pending:
            return []
        if existed:
            snapshot(db_path, status.current)
        return apply_migrations(conn, migrations_dir)
    finally:
        conn.close()


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a connection in the mode the engine needs.

    Args:
        db_path: Path to the SQLite file, or ":memory:". The parent directory is created
            if it doesn't exist.

    Returns:
        A connection in autocommit mode (`isolation_level=None`) with foreign keys on.
    """
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _check_connection(conn: sqlite3.Connection) -> None:
    if conn.isolation_level is not None:
        raise MigrationError(
            "The connection must be in autocommit mode: open it with isolation_level=None "
            "(or use sqlite_migrate.connect)."
        )
    if conn.in_transaction:
        raise MigrationError("The connection has an open transaction; commit or roll back first.")


def _utc_now() -> datetime:
    return datetime.now(UTC)
