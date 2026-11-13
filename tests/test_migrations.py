import sqlite3
from pathlib import Path

import pytest

from gift_exchange.core.db import connect
from gift_exchange.core.migrations import (
    MIGRATIONS_DIR,
    MigrationError,
    apply_migrations,
    load_migrations,
    migrate_database,
    migration_status,
    snapshot,
)


@pytest.fixture
def mdir(tmp_path: Path) -> Path:
    d = tmp_path / "migrations"
    d.mkdir()
    return d


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def write(mdir: Path, name: str, sql: str) -> Path:
    path = mdir / name
    path.write_text(sql)
    return path


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {r[0] for r in rows} - {"schema_migrations"}


# --- the real migrations folder ----------------------------------------------------


def test_real_migrations_apply_cleanly_and_are_idempotent(conn: sqlite3.Connection) -> None:
    expected = [m.version for m in load_migrations(MIGRATIONS_DIR)]
    assert apply_migrations(conn, MIGRATIONS_DIR) == expected
    assert apply_migrations(conn, MIGRATIONS_DIR) == []


# --- applying ---------------------------------------------------------------------


def test_applies_in_order_and_records_versions(mdir: Path, conn: sqlite3.Connection) -> None:
    write(mdir, "0002_b.sql", "ALTER TABLE a ADD COLUMN y INTEGER;")
    write(mdir, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    write(mdir, "README.md", "ignored")
    assert apply_migrations(conn, mdir) == [1, 2]
    status = migration_status(conn, mdir)
    assert status.current == 2 and status.applied == (1, 2) and status.pending == ()
    assert [r[1] for r in conn.execute("PRAGMA table_info(a)")] == ["x", "y"]


def test_skips_already_applied(mdir: Path, conn: sqlite3.Connection) -> None:
    write(mdir, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    assert apply_migrations(conn, mdir) == [1]
    write(mdir, "0002_b.sql", "CREATE TABLE b (x INTEGER);")
    assert apply_migrations(conn, mdir) == [2]
    assert tables(conn) == {"a", "b"}


def test_empty_folder_is_fine(mdir: Path, conn: sqlite3.Connection) -> None:
    assert apply_migrations(conn, mdir) == []
    assert migration_status(conn, mdir).current == 0


def test_failing_migration_rolls_back_only_itself(mdir: Path, conn: sqlite3.Connection) -> None:
    write(mdir, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    write(mdir, "0002_b.sql", "CREATE TABLE b (x INTEGER);\nINSERT INTO nope VALUES (1);")
    with pytest.raises(MigrationError, match="0002_b.sql failed"):
        apply_migrations(conn, mdir)
    assert tables(conn) == {"a"}
    assert migration_status(conn, mdir).applied == (1,)
    assert not conn.in_transaction
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_foreign_key_violation_is_caught(mdir: Path, conn: sqlite3.Connection) -> None:
    write(
        mdir,
        "0001_a.sql",
        "CREATE TABLE p (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE c (p_id INTEGER REFERENCES p(id));\n"
        "INSERT INTO c VALUES (42);",
    )
    with pytest.raises(MigrationError, match="foreign-key violations in: c"):
        apply_migrations(conn, mdir)
    assert tables(conn) == set()


def test_table_rebuild_pattern_works(mdir: Path, conn: sqlite3.Connection) -> None:
    # Dropping a referenced parent table mid-rebuild only works with foreign keys off.
    write(
        mdir,
        "0001_a.sql",
        "CREATE TABLE p (id INTEGER PRIMARY KEY, junk TEXT);\n"
        "CREATE TABLE c (p_id INTEGER REFERENCES p(id));\n"
        "INSERT INTO p VALUES (1, 'x'); INSERT INTO c VALUES (1);",
    )
    write(
        mdir,
        "0002_drop_junk.sql",
        "CREATE TABLE p_new (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO p_new SELECT id FROM p;\n"
        "DROP TABLE p;\n"
        "ALTER TABLE p_new RENAME TO p;",
    )
    assert apply_migrations(conn, mdir) == [1, 2]
    assert conn.execute("SELECT p_id FROM c").fetchall()[0][0] == 1


def test_trigger_with_begin_end_is_allowed(mdir: Path, conn: sqlite3.Connection) -> None:
    write(
        mdir,
        "0001_a.sql",
        "CREATE TABLE a (x INTEGER);\nCREATE TRIGGER t AFTER INSERT ON a\nBEGIN\n  SELECT 1;\nEND;",
    )
    assert apply_migrations(conn, mdir) == [1]


def test_refuses_inside_open_transaction(mdir: Path, conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN")
    with pytest.raises(MigrationError, match="open transaction"):
        apply_migrations(conn, mdir)


# --- file validation ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["1_a.sql", "0001-a.sql", "0001_A.sql", "0001.sql"])
def test_bad_file_name(mdir: Path, name: str) -> None:
    write(mdir, name, "SELECT 1;")
    with pytest.raises(MigrationError, match="Bad migration file name"):
        load_migrations(mdir)


@pytest.mark.parametrize(
    "files",
    [["0002_a.sql"], ["0001_a.sql", "0003_c.sql"], ["0001_a.sql", "0001_b.sql"]],
    ids=["no-0001", "gap", "duplicate"],
)
def test_version_gaps_and_duplicates(mdir: Path, files: list[str]) -> None:
    for f in files:
        write(mdir, f, "SELECT 1;")
    with pytest.raises(MigrationError, match="no gaps or duplicates"):
        load_migrations(mdir)


@pytest.mark.parametrize(
    "sql",
    ["BEGIN;", "begin transaction;", "COMMIT;", "ROLLBACK;", "PRAGMA foreign_keys = ON;"],
)
def test_engine_owned_statements_rejected(mdir: Path, sql: str) -> None:
    write(mdir, "0001_a.sql", f"CREATE TABLE a (x);\n{sql}")
    with pytest.raises(MigrationError, match="engine manages"):
        load_migrations(mdir)


# --- safety checks ------------------------------------------------------------------


def test_edited_migration_detected(mdir: Path, conn: sqlite3.Connection) -> None:
    path = write(mdir, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    apply_migrations(conn, mdir)
    path.write_text("CREATE TABLE a (x INTEGER, y INTEGER);")
    with pytest.raises(MigrationError, match="0001_a.sql was edited"):
        migration_status(conn, mdir)


def test_database_ahead_of_code_detected(mdir: Path, conn: sqlite3.Connection) -> None:
    write(mdir, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    b = write(mdir, "0002_b.sql", "CREATE TABLE b (x INTEGER);")
    apply_migrations(conn, mdir)
    b.unlink()
    with pytest.raises(MigrationError, match="ahead of the code"):
        migration_status(conn, mdir)


# --- snapshots and migrate_database -------------------------------------------------


def test_snapshot_is_a_valid_copy(tmp_path: Path) -> None:
    db = tmp_path / "gift.db"
    c = connect(db)
    c.execute("CREATE TABLE a (x)")
    c.execute("INSERT INTO a VALUES (7)")
    c.close()
    backup = snapshot(db, version=3)
    assert backup.name.startswith("gift.db.bak-v3-")
    assert sqlite3.connect(backup).execute("SELECT x FROM a").fetchone() == (7,)


def test_snapshot_keeps_only_newest(tmp_path: Path) -> None:
    db = tmp_path / "gift.db"
    connect(db).close()
    made = [snapshot(db, version=v, keep=2) for v in range(4)]
    assert sorted(tmp_path.glob("gift.db.bak-*")) == sorted(made[-2:])


def test_migrate_database_new_file_no_snapshot(tmp_path: Path, mdir: Path) -> None:
    write(mdir, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    db = tmp_path / "sub" / "gift.db"
    assert migrate_database(db, mdir) == [1]
    assert list(db.parent.glob("*.bak-*")) == []


def test_migrate_database_snapshots_before_applying(tmp_path: Path, mdir: Path) -> None:
    write(mdir, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    db = tmp_path / "gift.db"
    migrate_database(db, mdir)
    assert migrate_database(db, mdir) == []  # nothing pending -> no snapshot
    assert list(tmp_path.glob("*.bak-*")) == []

    write(mdir, "0002_b.sql", "CREATE TABLE b (x INTEGER);")
    assert migrate_database(db, mdir) == [2]
    (backup,) = tmp_path.glob("*.bak-*")
    assert backup.name.startswith("gift.db.bak-v1-")
    backup_tables = {
        r[0] for r in sqlite3.connect(backup).execute("SELECT name FROM sqlite_master")
    }
    assert "a" in backup_tables and "b" not in backup_tables
