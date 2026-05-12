-- 001_initial.sql
-- Initial schema for the fundamentals dashboard.
--
-- Conventions (see AGENTS.md for rationale):
--   - All monetary values stored in native currency. Sibling _ccy column
--     where the currency isn't already obvious from context.
--   - Camel-case vendor field names normalized to snake_case here. Two known
--     EODHD typos are silently corrected: `capitalSurpluse` -> capital_surplus,
--     `nonCurrrentAssetsOther` -> non_current_assets_other.
--   - Every UPSERT-mode table has a `loaded_at` timestamp for restatement
--     detection. Latest-wins by (natural_key, MAX(loaded_at)).
--   - DOUBLE used for monetary values (15 significant digits is more than
--     enough for our purposes; precision is not consistency-critical here).
--   - PRIMARY KEY on the natural key so that INSERT ... ON CONFLICT works
--     cleanly for UPSERT semantics.

-- =============================================================================
-- Migrations registry
-- =============================================================================
CREATE TABLE IF NOT EXISTS _schema_migrations (
    version     VARCHAR PRIMARY KEY,
    applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =============================================================================
-- Universe (user-managed list of followed tickers)
-- =============================================================================
CREATE TABLE IF NOT EXISTS universe (
    ticker      VARCHAR PRIMARY KEY,
    added_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active      BOOLEAN   NOT NULL DEFAULT TRUE,
    notes       VARCHAR
);


-- =============================================================================
-- Security master (from General block; effectively static per ticker)
-- =============================================================================
CREATE TABLE IF NOT EXISTS security_master (
    ticker                  VARCHAR PRIMARY KEY,
    code                    VARCHAR NOT NULL,
    exchange                VARCHAR NOT NULL,
    name                    VARCHAR,
    type                    VARCHAR,
    currency_code           VARCHAR NOT NULL,
    country_name            VARCHAR,
    country_iso             VARCHAR,
    isin                    VARCHAR,
    cusip                   VARCHAR,
    cik                     VARCHAR,
    open_figi               VARCHAR,
    lei                     VARCHAR,
    primary_ticker          VARCHAR,
    sector                  VARCHAR,
    industry                VARCHAR,
    gic_sector              VARCHAR,
    gic_group               VARCHAR,
    gic_industry            VARCHAR,
    gic_sub_industry        VARCHAR,
    home_category           VARCHAR,
    fiscal_year_end         VARCHAR,        -- e.g. "September"
    ipo_date                DATE,
    is_delisted             BOOLEAN NOT NULL DEFAULT FALSE,
    full_time_employees     INTEGER,
    description             VARCHAR,
    web_url                 VARCHAR,
    logo_url                VARCHAR,
    vendor_updated_at       TIMESTAMP,      -- EODHD's UpdatedAt
    loaded_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =============================================================================
-- Quarterly fundamentals (from Highlights block; MRQ/TTM snapshot)
-- =============================================================================
-- Note: vendor-derived ratios like MarketCapitalization, PERatio, PEGRatio
-- are intentionally NOT stored. They depend on price/forecasts and we derive
-- them ourselves. We do store the TTM aggregates because they're cheap and
-- useful for sanity checks against our own computed TTMs.
CREATE TABLE IF NOT EXISTS quarterly_fundamentals (
    ticker                          VARCHAR NOT NULL,
    mrq_period_end                  DATE NOT NULL,
    currency                        VARCHAR NOT NULL,
    -- TTM aggregates from vendor
    revenue_ttm                     DOUBLE,
    revenue_per_share_ttm           DOUBLE,
    gross_profit_ttm                DOUBLE,
    ebitda                          DOUBLE,
    profit_margin                   DOUBLE,
    operating_margin_ttm            DOUBLE,
    return_on_assets_ttm            DOUBLE,
    return_on_equity_ttm            DOUBLE,
    diluted_eps_ttm                 DOUBLE,
    -- Per-share figures
    earnings_share                  DOUBLE,
    book_value                      DOUBLE,
    dividend_share                  DOUBLE,
    -- Growth (vendor pre-computes; we'll verify ourselves)
    quarterly_revenue_growth_yoy    DOUBLE,
    quarterly_earnings_growth_yoy   DOUBLE,
    loaded_at                       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, mrq_period_end)
);


-- =============================================================================
-- Balance sheet (64 vendor fields, normalized to snake_case)
-- =============================================================================
CREATE TABLE IF NOT EXISTS balance_sheet (
    ticker                                              VARCHAR NOT NULL,
    fiscal_period_end                                   DATE NOT NULL,
    report_date                                         DATE,       -- from vendor filing_date
    currency                                            VARCHAR NOT NULL,
    -- Assets
    total_assets                                        DOUBLE,
    total_current_assets                                DOUBLE,
    cash                                                DOUBLE,
    cash_and_equivalents                                DOUBLE,
    cash_and_short_term_investments                     DOUBLE,
    short_term_investments                              DOUBLE,
    long_term_investments                               DOUBLE,
    net_receivables                                     DOUBLE,
    inventory                                           DOUBLE,
    other_current_assets                                DOUBLE,
    other_assets                                        DOUBLE,
    property_plant_equipment                            DOUBLE,
    property_plant_and_equipment_gross                  DOUBLE,
    property_plant_and_equipment_net                    DOUBLE,
    accumulated_depreciation                            DOUBLE,
    intangible_assets                                   DOUBLE,
    goodwill                                            DOUBLE,         -- vendor: goodWill
    negative_goodwill                                   DOUBLE,
    accumulated_amortization                            DOUBLE,
    net_tangible_assets                                 DOUBLE,
    earning_assets                                      DOUBLE,         -- bank-specific; often NULL
    deferred_long_term_asset_charges                    DOUBLE,
    non_current_assets_total                            DOUBLE,
    non_current_assets_other                            DOUBLE,         -- vendor typo: nonCurrrentAssetsOther
    -- Liabilities
    total_liab                                          DOUBLE,
    total_current_liabilities                           DOUBLE,
    accounts_payable                                    DOUBLE,
    current_deferred_revenue                            DOUBLE,
    short_term_debt                                     DOUBLE,
    short_long_term_debt                                DOUBLE,
    short_long_term_debt_total                          DOUBLE,
    long_term_debt                                      DOUBLE,
    long_term_debt_total                                DOUBLE,
    net_debt                                            DOUBLE,         -- vendor-computed; see PLAN.md known limitations
    capital_lease_obligations                           DOUBLE,
    deferred_long_term_liab                             DOUBLE,
    other_current_liab                                  DOUBLE,
    other_liab                                          DOUBLE,
    non_current_liabilities_total                       DOUBLE,
    non_current_liabilities_other                       DOUBLE,
    -- Equity
    total_stockholder_equity                            DOUBLE,
    common_stock                                        DOUBLE,
    common_stock_total_equity                           DOUBLE,
    capital_stock                                       DOUBLE,
    additional_paid_in_capital                          DOUBLE,
    capital_surplus                                     DOUBLE,         -- vendor typo: capitalSurpluse
    retained_earnings                                   DOUBLE,
    retained_earnings_total_equity                      DOUBLE,
    treasury_stock                                      DOUBLE,
    preferred_stock_total_equity                        DOUBLE,
    preferred_stock_redeemable                          DOUBLE,
    other_stockholder_equity                            DOUBLE,
    accumulated_other_comprehensive_income              DOUBLE,
    total_permanent_equity                              DOUBLE,
    noncontrolling_interest_in_consolidated_entity      DOUBLE,
    temporary_equity_redeemable_noncontrolling_interests DOUBLE,
    warrants                                            DOUBLE,
    -- Summary lines / cross-checks
    liabilities_and_stockholders_equity                 DOUBLE,
    net_working_capital                                 DOUBLE,
    net_invested_capital                                DOUBLE,
    common_stock_shares_outstanding                     BIGINT,
    -- Audit
    loaded_at                                           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_period_end)
);

CREATE INDEX IF NOT EXISTS idx_balance_sheet_report_date
    ON balance_sheet(ticker, report_date);


-- =============================================================================
-- Income statement (34 vendor fields)
-- =============================================================================
CREATE TABLE IF NOT EXISTS income_statement (
    ticker                                  VARCHAR NOT NULL,
    fiscal_period_end                       DATE NOT NULL,
    report_date                             DATE,
    currency                                VARCHAR NOT NULL,
    -- Revenue and cost
    total_revenue                           DOUBLE,
    cost_of_revenue                         DOUBLE,
    gross_profit                            DOUBLE,
    -- Operating
    research_development                    DOUBLE,
    selling_general_administrative          DOUBLE,
    selling_and_marketing_expenses          DOUBLE,
    other_operating_expenses                DOUBLE,
    total_operating_expenses                DOUBLE,
    operating_income                        DOUBLE,
    -- Other income / expense
    interest_income                         DOUBLE,
    interest_expense                        DOUBLE,
    net_interest_income                     DOUBLE,
    non_operating_income_net_other          DOUBLE,
    total_other_income_expense_net          DOUBLE,
    -- Earnings before tax
    ebit                                    DOUBLE,
    ebitda                                  DOUBLE,
    depreciation_and_amortization           DOUBLE,
    reconciled_depreciation                 DOUBLE,
    income_before_tax                       DOUBLE,
    tax_provision                           DOUBLE,
    income_tax_expense                      DOUBLE,
    -- Special items
    minority_interest                       DOUBLE,
    extraordinary_items                     DOUBLE,
    non_recurring                           DOUBLE,
    other_items                             DOUBLE,
    discontinued_operations                 DOUBLE,
    effect_of_accounting_charges            DOUBLE,
    -- Net income
    net_income                              DOUBLE,
    net_income_from_continuing_ops          DOUBLE,
    net_income_applicable_to_common_shares  DOUBLE,
    preferred_stock_and_other_adjustments   DOUBLE,
    -- Audit
    loaded_at                               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_period_end)
);

CREATE INDEX IF NOT EXISTS idx_income_statement_report_date
    ON income_statement(ticker, report_date);


-- =============================================================================
-- Cash flow (32 vendor fields)
-- =============================================================================
CREATE TABLE IF NOT EXISTS cash_flow (
    ticker                                          VARCHAR NOT NULL,
    fiscal_period_end                               DATE NOT NULL,
    report_date                                     DATE,
    currency                                        VARCHAR NOT NULL,
    -- Operating
    net_income                                      DOUBLE,
    depreciation                                    DOUBLE,
    stock_based_compensation                        DOUBLE,
    change_to_netincome                             DOUBLE,
    change_to_account_receivables                   DOUBLE,
    change_receivables                              DOUBLE,
    change_to_inventory                             DOUBLE,
    change_to_liabilities                           DOUBLE,
    change_in_working_capital                       DOUBLE,
    change_to_operating_activities                  DOUBLE,
    cash_flows_other_operating                      DOUBLE,
    other_non_cash_items                            DOUBLE,
    total_cash_from_operating_activities            DOUBLE,
    -- Investing
    capital_expenditures                            DOUBLE,
    investments                                     DOUBLE,
    other_cashflows_from_investing_activities       DOUBLE,
    total_cashflows_from_investing_activities       DOUBLE,
    -- Financing
    dividends_paid                                  DOUBLE,
    net_borrowings                                  DOUBLE,
    issuance_of_capital_stock                       DOUBLE,
    sale_purchase_of_stock                          DOUBLE,
    other_cashflows_from_financing_activities       DOUBLE,
    total_cash_from_financing_activities            DOUBLE,
    -- Reconciliation
    exchange_rate_changes                           DOUBLE,
    change_in_cash                                  DOUBLE,
    cash_and_cash_equivalents_changes               DOUBLE,
    begin_period_cash_flow                          DOUBLE,
    end_period_cash_flow                            DOUBLE,
    -- Vendor-computed FCF (kept; we may also recompute as CFO - capex)
    free_cash_flow                                  DOUBLE,
    -- Audit
    loaded_at                                       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_period_end)
);

CREATE INDEX IF NOT EXISTS idx_cash_flow_report_date
    ON cash_flow(ticker, report_date);


-- =============================================================================
-- Earnings events (from Earnings.History)
-- =============================================================================
CREATE TABLE IF NOT EXISTS earnings_events (
    ticker              VARCHAR NOT NULL,
    fiscal_period_end   DATE NOT NULL,
    report_date         DATE,
    before_after_market VARCHAR,        -- "BeforeMarket" / "AfterMarket" / NULL
    currency            VARCHAR,
    eps_estimate        DOUBLE,
    eps_actual          DOUBLE,
    eps_difference      DOUBLE,
    surprise_percent    DOUBLE,
    loaded_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_period_end)
);


-- =============================================================================
-- Shares outstanding (quarterly history from outstandingShares.quarterly)
-- =============================================================================
CREATE TABLE IF NOT EXISTS shares_outstanding (
    ticker      VARCHAR NOT NULL,
    period_end  DATE NOT NULL,
    shares      BIGINT,                 -- raw count
    shares_mln  DOUBLE,                 -- vendor convenience field
    loaded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, period_end)
);


-- =============================================================================
-- Dividends — declared events (from SplitsDividends scalar fields)
-- =============================================================================
-- Vendor only gives us the most-recent forward declaration cleanly. Full
-- historical dividend payment history would need a separate endpoint
-- (EODHD `/api/div/<ticker>`); add in a future migration if needed.
CREATE TABLE IF NOT EXISTS dividends_declared (
    ticker                          VARCHAR NOT NULL,
    ex_date                         DATE NOT NULL,
    pay_date                        DATE,
    forward_annual_dividend_rate    DOUBLE,
    forward_annual_dividend_yield   DOUBLE,
    payout_ratio                    DOUBLE,
    currency                        VARCHAR,
    loaded_at                       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, ex_date)
);


-- =============================================================================
-- Dividends — annual history (from SplitsDividends.NumberDividendsByYear)
-- =============================================================================
CREATE TABLE IF NOT EXISTS dividends_annual (
    ticker          VARCHAR NOT NULL,
    year            INTEGER NOT NULL,
    count           INTEGER,            -- number of dividends paid that year
    loaded_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, year)
);


-- =============================================================================
-- Splits
-- =============================================================================
-- Vendor only exposes LastSplitFactor / LastSplitDate in fundamentals. Full
-- history can be derived from the price series; add a separate splits feed
-- if a future migration needs it.
CREATE TABLE IF NOT EXISTS splits (
    ticker      VARCHAR NOT NULL,
    split_date  DATE NOT NULL,
    factor      VARCHAR NOT NULL,       -- e.g. "4:1"
    loaded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, split_date)
);


-- =============================================================================
-- Daily forward snapshot (analyst expectations as of a given calendar day)
-- =============================================================================
-- This is the ONE table that grows by one row per ticker per day. Every
-- field is forward-looking and cannot be reconstructed from history.
CREATE TABLE IF NOT EXISTS daily_forward_snapshot (
    ticker                  VARCHAR NOT NULL,
    snapshot_date           DATE NOT NULL,
    -- Analyst rating breakdown
    consensus_rating        DOUBLE,             -- 1.0 (Strong Buy) .. 5.0 (Strong Sell)
    target_price            DOUBLE,
    n_strong_buy            INTEGER,
    n_buy                   INTEGER,
    n_hold                  INTEGER,
    n_sell                  INTEGER,
    n_strong_sell           INTEGER,
    -- Forward EPS estimates by horizon
    eps_estimate_curr_q     DOUBLE,
    eps_estimate_next_q     DOUBLE,
    eps_estimate_curr_y     DOUBLE,
    eps_estimate_next_y     DOUBLE,
    currency                VARCHAR,
    loaded_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, snapshot_date)
);


-- =============================================================================
-- Analyst estimates history (per future period, snapshotted daily)
-- =============================================================================
-- One row per (ticker, snapshot_date, future_period). Captures Earnings.Trend
-- so we can detect estimate revisions over time.
CREATE TABLE IF NOT EXISTS analyst_estimates_history (
    ticker                      VARCHAR NOT NULL,
    snapshot_date               DATE NOT NULL,
    period                      VARCHAR NOT NULL,     -- e.g. "0q", "+1q", "0y", "+1y"
    period_end                  DATE,
    -- Earnings estimates
    eps_avg                     DOUBLE,
    eps_low                     DOUBLE,
    eps_high                    DOUBLE,
    eps_year_ago                DOUBLE,
    eps_num_analysts            INTEGER,
    eps_growth                  DOUBLE,
    -- Revenue estimates
    revenue_avg                 DOUBLE,
    revenue_low                 DOUBLE,
    revenue_high                DOUBLE,
    revenue_year_ago            DOUBLE,
    revenue_num_analysts        INTEGER,
    revenue_growth              DOUBLE,
    currency                    VARCHAR,
    loaded_at                   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, snapshot_date, period)
);


-- =============================================================================
-- Prices (daily OHLCV; adjusted_close re-derived each load)
-- =============================================================================
CREATE TABLE IF NOT EXISTS prices_daily (
    ticker          VARCHAR NOT NULL,
    date            DATE NOT NULL,
    open            DOUBLE,
    high            DOUBLE,
    low             DOUBLE,
    close           DOUBLE,
    adjusted_close  DOUBLE,                     -- mutable; overwritten on each load
    volume          BIGINT,
    loaded_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_date ON prices_daily(date);


-- =============================================================================
-- FX rates (designed in now, activated in Phase 8)
-- =============================================================================
-- Convention: rate is the multiplier to convert FROM `currency` TO USD.
-- Example row: ('JPY', '2026-05-11', 0.0064) means 1 JPY = 0.0064 USD.
CREATE TABLE IF NOT EXISTS fx_rates_daily (
    currency    VARCHAR NOT NULL,
    date        DATE NOT NULL,
    rate_to_usd DOUBLE NOT NULL,
    loaded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (currency, date)
);


-- =============================================================================
-- Mark this migration as applied
-- =============================================================================
INSERT INTO _schema_migrations (version) VALUES ('001_initial')
ON CONFLICT (version) DO NOTHING;
