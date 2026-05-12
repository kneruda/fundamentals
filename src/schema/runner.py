import re
from pathlib import Path

import duckdb

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def open_db(db_path: str | Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path))
    _run_migrations(con)
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


def _split_sql(sql: str) -> list[str]:
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]
