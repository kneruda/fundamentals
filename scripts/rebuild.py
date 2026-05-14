"""
Rebuild the warehouse from local raw JSON files (no re-fetch from EODHD).

Useful after a schema migration that needs the existing local cache
re-ingested. Iterates over every <ticker>.json in data/raw/fundamentals/
and pairs it with data/raw/prices/<ticker>.json when present.

Usage:
    uv run python scripts/rebuild.py
    uv run python scripts/rebuild.py --tickers AAPL MSFT
    uv run python scripts/rebuild.py --skip-prices       # fundamentals only
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingest.orchestrator import ingest_ticker  # noqa: E402
from src.schema.runner import open_db, warehouse_path  # noqa: E402

_SETTINGS_PATH = Path(__file__).parent.parent / "config" / "settings.yml"


def _raw_dirs() -> tuple[Path, Path]:
    with _SETTINGS_PATH.open() as f:
        cfg = yaml.safe_load(f)
    root = Path(__file__).parent.parent
    paths = cfg.get("paths", {})
    fund_dir = root / paths.get("raw_fundamentals", "data/raw/fundamentals")
    price_dir = root / paths.get("raw_prices", "data/raw/prices")
    return fund_dir, price_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild warehouse from local raw files.")
    parser.add_argument(
        "--tickers",
        nargs="+",
        metavar="TICKER",
        help="Specific tickers to re-ingest (default: all)",
    )
    parser.add_argument(
        "--skip-prices", action="store_true", help="Re-ingest fundamentals only, skip price files"
    )
    args = parser.parse_args()

    fund_dir, price_dir = _raw_dirs()
    if not fund_dir.exists():
        log.error("raw fundamentals dir not found: %s", fund_dir)
        sys.exit(1)

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = sorted(p.stem for p in fund_dir.glob("*.json"))

    if not tickers:
        log.warning("no fundamentals files found in %s", fund_dir)
        return

    warehouse = warehouse_path()
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    con = open_db(str(warehouse))

    t0 = time.monotonic()
    n_ok = 0
    n_fail = 0
    try:
        for i, ticker in enumerate(tickers, 1):
            fund_path = fund_dir / f"{ticker}.json"
            if not fund_path.exists():
                log.warning("[%d/%d] %s: no fundamentals file, skipping", i, len(tickers), ticker)
                n_fail += 1
                continue

            price_path: Path | None = None
            if not args.skip_prices:
                candidate = price_dir / f"{ticker}.json"
                if candidate.exists():
                    price_path = candidate

            try:
                ingest_ticker(con, fund_path, price_path, ticker=ticker)
                n_ok += 1
                log.info("[%d/%d] %s ok", i, len(tickers), ticker)
            except Exception as exc:
                n_fail += 1
                log.exception("[%d/%d] %s failed: %s", i, len(tickers), ticker, exc)
    finally:
        con.close()

    elapsed = time.monotonic() - t0
    log.info("rebuild complete: %d ok / %d failed in %.1fs", n_ok, n_fail, elapsed)


if __name__ == "__main__":
    main()
