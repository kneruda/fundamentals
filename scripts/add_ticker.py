"""
Add a ticker to the universe and backfill all historical data.

Usage:
    uv run python scripts/add_ticker.py SHOP
    uv run python scripts/add_ticker.py 7203.TSE
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
from src.universe import add_ticker  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: add_ticker.py <TICKER>")
        sys.exit(1)
    ticker = sys.argv[1].upper()
    warehouse = os.environ.get("WAREHOUSE_PATH", "data/warehouse.duckdb")
    Path(warehouse).parent.mkdir(parents=True, exist_ok=True)
    con = open_db(warehouse)
    try:
        add_ticker(con, ticker)
    except Exception as exc:
        log.error("could not add ticker=%s: %s", ticker, exc)
        sys.exit(1)
    finally:
        con.close()
    log.info("done ticker=%s", ticker)


if __name__ == "__main__":
    main()
