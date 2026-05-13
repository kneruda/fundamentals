-- 002_monitoring.sql
-- Per-ticker load monitoring and bulk-job checkpoint tables.

CREATE TABLE IF NOT EXISTS load_runs (
    ticker          VARCHAR NOT NULL,
    run_started_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status          VARCHAR NOT NULL,
    duration_ms     INTEGER,
    error_message   VARCHAR
);

CREATE TABLE IF NOT EXISTS bulk_load_jobs (
    job_id          VARCHAR NOT NULL,
    ticker          VARCHAR NOT NULL,
    status          VARCHAR NOT NULL DEFAULT 'pending',
    error_message   VARCHAR,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, ticker)
);
