-- 004_statements_period_type.sql
-- Add period_type ('quarterly'|'annual') as a PK component on statement tables.
-- DuckDB 1.5 does not support ALTER TABLE ADD COLUMN with constraints or
-- ALTER TABLE DROP/ADD PRIMARY KEY, so we rename, recreate, and copy.

-- =============================================================================
-- income_statement
-- =============================================================================
DROP INDEX IF EXISTS idx_income_statement_report_date;
ALTER TABLE income_statement RENAME TO _income_statement_old;

CREATE TABLE income_statement (
    ticker                                  VARCHAR NOT NULL,
    fiscal_period_end                       DATE NOT NULL,
    period_type                             VARCHAR NOT NULL DEFAULT 'quarterly',
    report_date                             DATE,
    currency                                VARCHAR NOT NULL,
    total_revenue                           DOUBLE,
    cost_of_revenue                         DOUBLE,
    gross_profit                            DOUBLE,
    research_development                    DOUBLE,
    selling_general_administrative          DOUBLE,
    selling_and_marketing_expenses          DOUBLE,
    other_operating_expenses                DOUBLE,
    total_operating_expenses                DOUBLE,
    operating_income                        DOUBLE,
    interest_income                         DOUBLE,
    interest_expense                        DOUBLE,
    net_interest_income                     DOUBLE,
    non_operating_income_net_other          DOUBLE,
    total_other_income_expense_net          DOUBLE,
    ebit                                    DOUBLE,
    ebitda                                  DOUBLE,
    depreciation_and_amortization           DOUBLE,
    reconciled_depreciation                 DOUBLE,
    income_before_tax                       DOUBLE,
    tax_provision                           DOUBLE,
    income_tax_expense                      DOUBLE,
    minority_interest                       DOUBLE,
    extraordinary_items                     DOUBLE,
    non_recurring                           DOUBLE,
    other_items                             DOUBLE,
    discontinued_operations                 DOUBLE,
    effect_of_accounting_charges            DOUBLE,
    net_income                              DOUBLE,
    net_income_from_continuing_ops          DOUBLE,
    net_income_applicable_to_common_shares  DOUBLE,
    preferred_stock_and_other_adjustments   DOUBLE,
    loaded_at                               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_period_end, period_type)
);

INSERT INTO income_statement
SELECT
    ticker, fiscal_period_end, 'quarterly', report_date, currency,
    total_revenue, cost_of_revenue, gross_profit,
    research_development, selling_general_administrative,
    selling_and_marketing_expenses, other_operating_expenses,
    total_operating_expenses, operating_income,
    interest_income, interest_expense, net_interest_income,
    non_operating_income_net_other, total_other_income_expense_net,
    ebit, ebitda, depreciation_and_amortization, reconciled_depreciation,
    income_before_tax, tax_provision, income_tax_expense,
    minority_interest, extraordinary_items, non_recurring, other_items,
    discontinued_operations, effect_of_accounting_charges,
    net_income, net_income_from_continuing_ops,
    net_income_applicable_to_common_shares,
    preferred_stock_and_other_adjustments,
    loaded_at
FROM _income_statement_old;

DROP TABLE _income_statement_old;

CREATE INDEX IF NOT EXISTS idx_income_statement_report_date
    ON income_statement(ticker, report_date);

-- =============================================================================
-- balance_sheet
-- =============================================================================
DROP INDEX IF EXISTS idx_balance_sheet_report_date;
ALTER TABLE balance_sheet RENAME TO _balance_sheet_old;

CREATE TABLE balance_sheet (
    ticker                                              VARCHAR NOT NULL,
    fiscal_period_end                                   DATE NOT NULL,
    period_type                                         VARCHAR NOT NULL DEFAULT 'quarterly',
    report_date                                         DATE,
    currency                                            VARCHAR NOT NULL,
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
    goodwill                                            DOUBLE,
    negative_goodwill                                   DOUBLE,
    accumulated_amortization                            DOUBLE,
    net_tangible_assets                                 DOUBLE,
    earning_assets                                      DOUBLE,
    deferred_long_term_asset_charges                    DOUBLE,
    non_current_assets_total                            DOUBLE,
    non_current_assets_other                            DOUBLE,
    total_liab                                          DOUBLE,
    total_current_liabilities                           DOUBLE,
    accounts_payable                                    DOUBLE,
    current_deferred_revenue                            DOUBLE,
    short_term_debt                                     DOUBLE,
    short_long_term_debt                                DOUBLE,
    short_long_term_debt_total                          DOUBLE,
    long_term_debt                                      DOUBLE,
    long_term_debt_total                                DOUBLE,
    net_debt                                            DOUBLE,
    capital_lease_obligations                           DOUBLE,
    deferred_long_term_liab                             DOUBLE,
    other_current_liab                                  DOUBLE,
    other_liab                                          DOUBLE,
    non_current_liabilities_total                       DOUBLE,
    non_current_liabilities_other                       DOUBLE,
    total_stockholder_equity                            DOUBLE,
    common_stock                                        DOUBLE,
    common_stock_total_equity                           DOUBLE,
    capital_stock                                       DOUBLE,
    additional_paid_in_capital                          DOUBLE,
    capital_surplus                                     DOUBLE,
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
    liabilities_and_stockholders_equity                 DOUBLE,
    net_working_capital                                 DOUBLE,
    net_invested_capital                                DOUBLE,
    common_stock_shares_outstanding                     BIGINT,
    loaded_at                                           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_period_end, period_type)
);

INSERT INTO balance_sheet
SELECT
    ticker, fiscal_period_end, 'quarterly', report_date, currency,
    total_assets, total_current_assets, cash, cash_and_equivalents,
    cash_and_short_term_investments, short_term_investments, long_term_investments,
    net_receivables, inventory, other_current_assets, other_assets,
    property_plant_equipment, property_plant_and_equipment_gross,
    property_plant_and_equipment_net, accumulated_depreciation,
    intangible_assets, goodwill, negative_goodwill, accumulated_amortization,
    net_tangible_assets, earning_assets, deferred_long_term_asset_charges,
    non_current_assets_total, non_current_assets_other,
    total_liab, total_current_liabilities, accounts_payable,
    current_deferred_revenue, short_term_debt, short_long_term_debt,
    short_long_term_debt_total, long_term_debt, long_term_debt_total, net_debt,
    capital_lease_obligations, deferred_long_term_liab,
    other_current_liab, other_liab,
    non_current_liabilities_total, non_current_liabilities_other,
    total_stockholder_equity, common_stock, common_stock_total_equity,
    capital_stock, additional_paid_in_capital, capital_surplus,
    retained_earnings, retained_earnings_total_equity, treasury_stock,
    preferred_stock_total_equity, preferred_stock_redeemable,
    other_stockholder_equity, accumulated_other_comprehensive_income,
    total_permanent_equity, noncontrolling_interest_in_consolidated_entity,
    temporary_equity_redeemable_noncontrolling_interests, warrants,
    liabilities_and_stockholders_equity, net_working_capital,
    net_invested_capital, common_stock_shares_outstanding,
    loaded_at
FROM _balance_sheet_old;

DROP TABLE _balance_sheet_old;

CREATE INDEX IF NOT EXISTS idx_balance_sheet_report_date
    ON balance_sheet(ticker, report_date);

-- =============================================================================
-- cash_flow
-- =============================================================================
DROP INDEX IF EXISTS idx_cash_flow_report_date;
ALTER TABLE cash_flow RENAME TO _cash_flow_old;

CREATE TABLE cash_flow (
    ticker                                          VARCHAR NOT NULL,
    fiscal_period_end                               DATE NOT NULL,
    period_type                                     VARCHAR NOT NULL DEFAULT 'quarterly',
    report_date                                     DATE,
    currency                                        VARCHAR NOT NULL,
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
    capital_expenditures                            DOUBLE,
    investments                                     DOUBLE,
    other_cashflows_from_investing_activities       DOUBLE,
    total_cashflows_from_investing_activities       DOUBLE,
    dividends_paid                                  DOUBLE,
    net_borrowings                                  DOUBLE,
    issuance_of_capital_stock                       DOUBLE,
    sale_purchase_of_stock                          DOUBLE,
    other_cashflows_from_financing_activities       DOUBLE,
    total_cash_from_financing_activities            DOUBLE,
    exchange_rate_changes                           DOUBLE,
    change_in_cash                                  DOUBLE,
    cash_and_cash_equivalents_changes               DOUBLE,
    begin_period_cash_flow                          DOUBLE,
    end_period_cash_flow                            DOUBLE,
    free_cash_flow                                  DOUBLE,
    loaded_at                                       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, fiscal_period_end, period_type)
);

INSERT INTO cash_flow
SELECT
    ticker, fiscal_period_end, 'quarterly', report_date, currency,
    net_income, depreciation, stock_based_compensation, change_to_netincome,
    change_to_account_receivables, change_receivables, change_to_inventory,
    change_to_liabilities, change_in_working_capital, change_to_operating_activities,
    cash_flows_other_operating, other_non_cash_items,
    total_cash_from_operating_activities,
    capital_expenditures, investments,
    other_cashflows_from_investing_activities,
    total_cashflows_from_investing_activities,
    dividends_paid, net_borrowings, issuance_of_capital_stock,
    sale_purchase_of_stock, other_cashflows_from_financing_activities,
    total_cash_from_financing_activities,
    exchange_rate_changes, change_in_cash, cash_and_cash_equivalents_changes,
    begin_period_cash_flow, end_period_cash_flow, free_cash_flow,
    loaded_at
FROM _cash_flow_old;

DROP TABLE _cash_flow_old;

CREATE INDEX IF NOT EXISTS idx_cash_flow_report_date
    ON cash_flow(ticker, report_date);
