"""
Fetch fresh data from EODHD for every active ticker and ingest it into the warehouse.

Usage:
    uv run python scripts/load_daily.py
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingest.orchestrator import ingest_universe  # noqa: E402
from src.schema.runner import open_db  # noqa: E402


def main() -> None:
    warehouse = os.environ.get("WAREHOUSE_PATH", "data/warehouse.duckdb")
    Path(warehouse).parent.mkdir(parents=True, exist_ok=True)
    con = open_db(warehouse)
    try:
        ingest_universe(con)
    finally:
        con.close()
    log.info("daily load complete")


if __name__ == "__main__":
    main()
