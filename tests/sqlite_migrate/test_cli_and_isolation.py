import subprocess
import sys
from pathlib import Path

import pytest
from sqlite_migrate.cli import main


def test_cli_up_then_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mdir = tmp_path / "m"
    mdir.mkdir()
    (mdir / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
    db = tmp_path / "gift.db"
    args = ["--db", str(db), "--dir", str(mdir)]

    assert main([*args, "up"]) == 0
    assert "Applied: 0001" in capsys.readouterr().out
    assert main([*args, "status"]) == 0
    out = capsys.readouterr().out
    assert "Current version: 0001" in out and "Pending: none" in out


def test_cli_reports_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "1_bad.sql").write_text("SELECT 1;")
    assert main(["--db", str(tmp_path / "x.db"), "--dir", str(tmp_path), "up"]) == 1
    assert "Bad migration file name" in capsys.readouterr().err


def test_package_does_not_import_the_app() -> None:
    # Keeps sqlite_migrate extractable into its own repo.
    code = "import sys, sqlite_migrate, sqlite_migrate.cli; print('gift_exchange' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
