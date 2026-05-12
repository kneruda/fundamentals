import re
from datetime import UTC, date, datetime

import duckdb
import pandas as pd

# Vendor field names that need explicit remapping (typos or single-word nouns).
_RENAMES: dict[str, str] = {
    "capitalSurpluse": "capital_surplus",  # vendor typo: spurious 'e'
    "nonCurrrentAssetsOther": "non_current_assets_other",  # vendor typo: triple 'r'
    "goodWill": "goodwill",  # one word, not two
}


def col(name: str) -> str:
    """Normalize a vendor camelCase field name to its snake_case DB column."""
    if name in _RENAMES:
        return _RENAMES[name]
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def to_float(val: object) -> float | None:
    if val is None:
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def to_int(val: object) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def to_date(val: object) -> date | None:
    if not val or val == "0000-00-00":
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None


def upsert_df(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame, pk: list[str]) -> None:
    """INSERT rows from df into table; on PK conflict update all non-PK columns."""
    if df.empty:
        return

    df = df.copy()
    df["loaded_at"] = datetime.now(UTC).replace(tzinfo=None)

    tmp = f"_stage_{table}"
    con.register(tmp, df)
    try:
        data_cols = [c for c in df.columns if c not in pk]
        insert_cols = ", ".join(f'"{c}"' for c in df.columns)
        pk_clause = ", ".join(f'"{c}"' for c in pk)
        update_clause = ", ".join(f'"{c}" = excluded."{c}"' for c in data_cols)
        con.execute(f"""
            INSERT INTO {table} ({insert_cols})
            SELECT {insert_cols} FROM {tmp}
            ON CONFLICT ({pk_clause}) DO UPDATE SET {update_clause}
        """)
    finally:
        con.unregister(tmp)
