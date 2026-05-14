"""
Fetch fresh data from EODHD for every active ticker and ingest it into the warehouse.

Usage:
    uv run python scripts/load_daily.py
"""

import logging
import sys
import time
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


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins, secs = divmod(int(seconds), 60)
    if mins < 60:
        return f"{mins}m {secs}s"
    hours, mins = divmod(mins, 60)
    return f"{hours}h {mins}m {secs}s"


def main() -> None:
    warehouse = warehouse_path()
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    con = open_db(str(warehouse))
    t0 = time.monotonic()
    try:
        results = ingest_universe(con)
    finally:
        con.close()

    elapsed = time.monotonic() - t0
    n_ok = sum(1 for _, ok, _ in results if ok)
    n_fail = len(results) - n_ok
    log.info("daily load complete: %d ok / %d failed in %s", n_ok, n_fail, _fmt_duration(elapsed))
    if n_fail:
        for ticker, ok, msg in results:
            if not ok:
                log.warning("  FAILED %s: %s", ticker, msg)


if __name__ == "__main__":
    main()
