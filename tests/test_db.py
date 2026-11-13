from sqlite_migrate import apply_migrations, load_migrations

from gift_exchange.core.db import MIGRATIONS_DIR, connect


def test_app_migrations_apply_cleanly_and_are_idempotent() -> None:
    conn = connect(":memory:")
    expected = [m.version for m in load_migrations(MIGRATIONS_DIR)]
    assert apply_migrations(conn, MIGRATIONS_DIR) == expected
    assert apply_migrations(conn, MIGRATIONS_DIR) == []
