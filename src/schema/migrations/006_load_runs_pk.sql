-- 006_load_runs_pk.sql
-- Add PRIMARY KEY (ticker, run_started_at) to load_runs.
-- DuckDB doesn't support ALTER TABLE ADD PRIMARY KEY, so we follow the
-- same rename/recreate/copy pattern as migration 004.

ALTER TABLE load_runs RENAME TO _load_runs_old;

CREATE TABLE load_runs (
    ticker          VARCHAR NOT NULL,
    run_started_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status          VARCHAR NOT NULL,
    duration_ms     INTEGER,
    error_message   VARCHAR,
    PRIMARY KEY (ticker, run_started_at)
);

INSERT INTO load_runs (ticker, run_started_at, status, duration_ms, error_message)
SELECT ticker, run_started_at, status, duration_ms, error_message
FROM _load_runs_old;

DROP TABLE _load_runs_old;
