import os
import re
from pathlib import Path

import duckdb
import yaml

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yml"
_ROOT = Path(__file__).parent.parent.parent


def warehouse_path() -> Path:
    """Return the absolute warehouse path from settings, overridable via WAREHOUSE_PATH env var."""
    env = os.environ.get("WAREHOUSE_PATH")
    if env:
        return Path(env)
    with _SETTINGS_PATH.open() as f:
        cfg = yaml.safe_load(f)
    return _ROOT / cfg["paths"]["warehouse"]


def open_db(db_path: str | Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path))
    _run_migrations(con)
    from src.compute import setup_views

    setup_views(con)
    return con


def _run_migrations(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            version    VARCHAR PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    applied = {r[0] for r in con.execute("SELECT version FROM _schema_migrations").fetchall()}

    for script in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if script.stem not in applied:
            for stmt in _split_sql(script.read_text()):
                con.execute(stmt)
            con.execute(
                "INSERT INTO _schema_migrations (version) VALUES (?) ON CONFLICT (version) DO NOTHING",
                [script.stem],
            )


def _split_sql(sql: str) -> list[str]:
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]
