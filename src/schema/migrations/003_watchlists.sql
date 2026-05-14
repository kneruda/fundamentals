-- 003_watchlists.sql
-- Named watchlists with optional portfolio columns (shares/cost_basis reserved for Phase 10.5+).

CREATE TABLE IF NOT EXISTS watchlist (
    watchlist_id INTEGER PRIMARY KEY,
    name         VARCHAR NOT NULL,
    description  VARCHAR,
    created_at   TIMESTAMP NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_name ON watchlist (lower(name));

CREATE TABLE IF NOT EXISTS watchlist_membership (
    watchlist_id INTEGER NOT NULL,
    ticker       VARCHAR NOT NULL,
    shares       DOUBLE,
    cost_basis   DOUBLE,
    notes        VARCHAR,
    added_at     TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (watchlist_id, ticker)
);
