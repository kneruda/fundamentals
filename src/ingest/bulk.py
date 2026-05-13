"""Rate-limited, resumable bulk ticker loader with job checkpointing."""

import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import yaml

from src.universe import add_ticker

log = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yml"


def _bulk_rpm() -> float:
    with _SETTINGS_PATH.open() as f:
        cfg = yaml.safe_load(f)
    return float(cfg.get("bulk_load", {}).get("requests_per_minute", 20))


def create_job(con: duckdb.DuckDBPyConnection, tickers: list[str]) -> str:
    """Create a new bulk-load job and return its job_id."""
    job_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    for ticker in tickers:
        con.execute(
            """
            INSERT INTO bulk_load_jobs (job_id, ticker, status, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?)
            ON CONFLICT (job_id, ticker) DO NOTHING
            """,
            [job_id, ticker, now, now],
        )
    log.info("created job_id=%s tickers=%d", job_id, len(tickers))
    return job_id


def run_job(con: duckdb.DuckDBPyConnection, job_id: str) -> list[tuple[str, bool, str]]:
    """Process all pending tickers for job_id with per-ticker rate limiting.

    Returns list of (ticker, success, message) tuples for tickers processed in this run.
    """
    rows = con.execute(
        "SELECT ticker FROM bulk_load_jobs WHERE job_id = ? AND status = 'pending' ORDER BY ticker",
        [job_id],
    ).fetchall()
    if not rows:
        total = con.execute(
            "SELECT COUNT(*) FROM bulk_load_jobs WHERE job_id = ?", [job_id]
        ).fetchone()[0]
        if total == 0:
            raise ValueError(f"Job not found: {job_id}")
        log.info("job_id=%s no pending tickers (already complete)", job_id)
        return []

    tickers = [r[0] for r in rows]
    rpm = _bulk_rpm()
    sleep_secs = 60.0 / rpm
    log.info("job_id=%s resuming %d pending tickers at %.1f RPM", job_id, len(tickers), rpm)

    results = []
    for i, ticker in enumerate(tickers):
        try:
            add_ticker(con, ticker)
            _update_job(con, job_id, ticker, "ok", None)
            results.append((ticker, True, "ok"))
            log.info("job_id=%s [%d/%d] ticker=%s ok", job_id, i + 1, len(tickers), ticker)
        except Exception as exc:
            msg = str(exc)
            _update_job(con, job_id, ticker, "failed", msg)
            results.append((ticker, False, msg))
            log.warning(
                "job_id=%s [%d/%d] ticker=%s failed: %s", job_id, i + 1, len(tickers), ticker, msg
            )

        if i < len(tickers) - 1:
            time.sleep(sleep_secs)

    return results


def _update_job(
    con: duckdb.DuckDBPyConnection,
    job_id: str,
    ticker: str,
    status: str,
    error_message: str | None,
) -> None:
    con.execute(
        """
        UPDATE bulk_load_jobs
        SET status = ?, error_message = ?, updated_at = now()
        WHERE job_id = ? AND ticker = ?
        """,
        [status, error_message, job_id, ticker],
    )
