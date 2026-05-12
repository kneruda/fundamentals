"""
Seed the universe table from config/universe.yml.

Skips tickers already present in the universe table. Safe to run multiple times.

Usage:
    uv run python scripts/seed_universe.py
"""

import logging
import os
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

from src.schema.runner import open_db  # noqa: E402
from src.universe import seed_from_config  # noqa: E402

_UNIVERSE_YML = Path(__file__).parent.parent / "config" / "universe.yml"


def main() -> None:
    warehouse = os.environ.get("WAREHOUSE_PATH", "data/warehouse.duckdb")
    Path(warehouse).parent.mkdir(parents=True, exist_ok=True)
    con = open_db(warehouse)
    try:
        seed_from_config(con, _UNIVERSE_YML)
    finally:
        con.close()
    log.info("seeding complete")


if __name__ == "__main__":
    main()
