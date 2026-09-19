"""In-process refresh jobs for the HTTP universe-management adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock, Thread
from uuid import uuid4

from src.ingest.orchestrator import refresh_universe_threaded
from src.services import queries


@dataclass
class RefreshJob:
    job_id: str
    total: int
    status: str = "queued"
    fetched: int = 0
    ingested: int = 0
    failed: int = 0
    current_ticker: str | None = None
    results: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def response(self) -> dict[str, object]:
        result = asdict(self)
        result.pop("created_at")
        return result


_lock = Lock()
_jobs: dict[str, RefreshJob] = {}


def start_refresh_all() -> dict[str, object]:
    """Start the existing refresh routine in a single background worker."""
    with _lock:
        if any(job.status in {"queued", "running"} for job in _jobs.values()):
            raise ValueError("A universe refresh is already running.")

        con = queries.open_warehouse()
        try:
            total = len(queries.active_tickers(con))
        finally:
            con.close()

        job = RefreshJob(job_id=str(uuid4()), total=total)
        _jobs[job.job_id] = job

    Thread(target=_run_job, args=(job.job_id,), daemon=True).start()
    return job.response()


def get_refresh_job(job_id: str) -> dict[str, object]:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise ValueError(f"Refresh job not found: {job_id}")
        return job.response()


def _run_job(job_id: str) -> None:
    con = queries.open_warehouse()
    try:
        with _lock:
            job = _jobs[job_id]
            job.status = "running"

        def on_progress(ticker: str, phase: str) -> None:
            with _lock:
                job = _jobs[job_id]
                if phase in {"fetch_done", "fetch_failed"}:
                    job.fetched += 1
                if phase == "fetch_failed":
                    job.failed += 1
                if phase == "ingest_start":
                    job.current_ticker = ticker
                if phase in {"ingest_done", "ingest_failed"}:
                    job.ingested += 1
                    job.current_ticker = None
                if phase == "ingest_failed":
                    job.failed += 1

        results = refresh_universe_threaded(con, on_progress=on_progress)
        with _lock:
            job = _jobs[job_id]
            job.results = [
                {"ticker": ticker, "ok": ok, "message": message or "refreshed"}
                for ticker, ok, message in results
            ]
            job.failed = sum(1 for _, ok, _ in results if not ok)
            job.status = "complete"
    except Exception as exc:
        with _lock:
            job = _jobs[job_id]
            job.status = "failed"
            job.error = str(exc)
    finally:
        con.close()
