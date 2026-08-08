"""
Bulk-load tickers from a file into the warehouse with rate limiting and resumable checkpointing.

Usage:
    uv run python scripts/bulk_load.py --file tickers.txt
    uv run python scripts/bulk_load.py --resume <job_id>
"""

import argparse
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

from src.ingest.bulk import create_job, run_job  # noqa: E402
from src.schema.runner import open_db, warehouse_path  # noqa: E402
from src.ticker_input import parse_ticker_input  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-load tickers into the warehouse.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--file", type=Path, metavar="FILE", help="Text file of tickers (one per line)"
    )
    group.add_argument("--resume", metavar="JOB_ID", help="Resume an existing bulk-load job")
    args = parser.parse_args()

    warehouse = warehouse_path()
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    con = open_db(str(warehouse))

    try:
        if args.resume:
            job_id = args.resume
            log.info("resuming job_id=%s", job_id)
        else:
            raw_text = args.file.read_text(encoding="utf-8")
            tickers = parse_ticker_input(raw_text)
            if not tickers:
                log.error("no tickers found in %s", args.file)
                sys.exit(1)
            job_id = create_job(con, tickers)
            print(f"Created job {job_id} with {len(tickers)} tickers.")

        results = run_job(con, job_id)
        n_ok = sum(1 for _, ok, _ in results if ok)
        n_fail = len(results) - n_ok
        print(f"Done: {n_ok} succeeded, {n_fail} failed.")
        for ticker, ok, msg in results:
            if not ok:
                print(f"  FAILED {ticker}: {msg}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
