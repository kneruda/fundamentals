"""
Fetch fresh data from EODHD for every active ticker and ingest it into the warehouse.

Usage:
    uv run python scripts/load_daily.py
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingest.orchestrator import ingest_universe  # noqa: E402
from src.schema.runner import open_db, warehouse_path  # noqa: E402


def main() -> None:
    warehouse = warehouse_path()
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    con = open_db(str(warehouse))
    try:
        ingest_universe(con)
    finally:
        con.close()
    log.info("daily load complete")


if __name__ == "__main__":
    main()
