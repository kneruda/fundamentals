from datetime import date

import duckdb
import pandas as pd

from ._util import to_date, to_float, to_int, upsert_df


def ingest_analyst_snapshot(
    con: duckdb.DuckDBPyConnection,
    ticker: str,
    data: dict,
    snapshot_date: date | None = None,
) -> None:
    if snapshot_date is None:
        snapshot_date = date.today()

    currency = data.get("General", {}).get("CurrencyCode")
    ar = data.get("AnalystRatings", {})
    h = data.get("Highlights", {})

    upsert_df(
        con,
        "daily_forward_snapshot",
        pd.DataFrame(
            [
                {
                    "ticker": ticker,
                    "snapshot_date": snapshot_date,
                    "consensus_rating": to_float(ar.get("Rating")),
                    "target_price": to_float(ar.get("TargetPrice")),
                    "n_strong_buy": to_int(ar.get("StrongBuy")),
                    "n_buy": to_int(ar.get("Buy")),
                    "n_hold": to_int(ar.get("Hold")),
                    "n_sell": to_int(ar.get("Sell")),
                    "n_strong_sell": to_int(ar.get("StrongSell")),
                    "eps_estimate_curr_q": to_float(h.get("EPSEstimateCurrentQuarter")),
                    "eps_estimate_next_q": to_float(h.get("EPSEstimateNextQuarter")),
                    "eps_estimate_curr_y": to_float(h.get("EPSEstimateCurrentYear")),
                    "eps_estimate_next_y": to_float(h.get("EPSEstimateNextYear")),
                    "currency": currency,
                }
            ]
        ),
        ["ticker", "snapshot_date"],
    )

    trend_rows = [
        {
            "ticker": ticker,
            "snapshot_date": snapshot_date,
            "period_end": to_date(entry.get("date")),
            "period": entry.get("period"),
            "eps_avg": to_float(entry.get("earningsEstimateAvg")),
            "eps_low": to_float(entry.get("earningsEstimateLow")),
            "eps_high": to_float(entry.get("earningsEstimateHigh")),
            "eps_year_ago": to_float(entry.get("earningsEstimateYearAgoEps")),
            "eps_num_analysts": to_int(entry.get("earningsEstimateNumberOfAnalysts")),
            "eps_growth": to_float(entry.get("earningsEstimateGrowth")),
            "revenue_avg": to_float(entry.get("revenueEstimateAvg")),
            "revenue_low": to_float(entry.get("revenueEstimateLow")),
            "revenue_high": to_float(entry.get("revenueEstimateHigh")),
            "revenue_year_ago": to_float(entry.get("revenueEstimateYearAgoEps")),
            "revenue_num_analysts": to_int(entry.get("revenueEstimateNumberOfAnalysts")),
            "revenue_growth": to_float(entry.get("revenueEstimateGrowth")),
            "currency": currency,
        }
        for entry in data.get("Earnings", {}).get("Trend", {}).values()
    ]
    if trend_rows:
        upsert_df(
            con,
            "analyst_estimates_history",
            pd.DataFrame(trend_rows),
            ["ticker", "snapshot_date", "period_end"],
        )
