"""
Phase 13: Forward-looking screens.

Section A — Vendor trends: work immediately using EODHD pre-computed deltas.
Section B — Snapshot history: require >= 30 days of daily_forward_snapshot accumulation.
"""

import pandas as pd
import streamlit as st

from src.app import sidebar as app_sidebar
from src.services import queries
from src.services.screeners import run_forward_screen
from src.watchlist import create_watchlist

st.set_page_config(page_title="Forward Screens", layout="wide")

MIN_HISTORY_DAYS = 30


@st.cache_resource
def _get_con():
    return queries.open_warehouse()


def _save_as_watchlist(df: "pd.DataFrame", key_prefix: str) -> None:
    with st.expander("Save these results as a watchlist"):
        wl_name = st.text_input("Watchlist name", key=f"{key_prefix}_wl_name")
        if st.button("Save", key=f"{key_prefix}_wl_btn"):
            if not wl_name.strip():
                st.error("Watchlist name is required.")
            else:
                try:
                    create_watchlist(_get_con(), wl_name.strip(), df["ticker"].tolist())
                    st.success(f"Saved '{wl_name}' with {len(df)} ticker(s).")
                except Exception as exc:
                    st.error(str(exc))


def _fmt_df(df: pd.DataFrame) -> pd.DataFrame:
    labels = {
        "ticker": "Ticker",
        "name": "Name",
        "sector": "Sector",
        "periods_revised_up": "Periods Revised Up",
        "max_eps_delta_pct": "Max EPS Delta %",
        "avg_eps_current": "Avg EPS Curr",
        "net_revisions": "Net Revisions",
        "revisions_up": "Revisions Up",
        "revisions_down": "Revisions Down",
        "surprise_percent": "Surprise %",
        "eps_delta_pct": "Fwd EPS Delta %",
        "fiscal_period_end": "Fiscal Period",
        "eps_estimate": "EPS Est",
        "eps_actual": "EPS Actual",
        "period": "Period",
        "period_end": "Period End",
        "eps_trend_current": "EPS Trend (curr)",
        "eps_trend_30days_ago": "EPS Trend (30d ago)",
        "rating_now": "Rating Now",
        "rating_then": "Rating Then",
        "rating_shift": "Rating Shift",
        "tp_now": "TP Now",
        "tp_then": "TP Then",
        "tp_change_pct": "TP Change %",
        "last_snap": "Last Snapshot",
    }
    display = df.rename(columns={c: labels.get(c, c) for c in df.columns})
    float_cols = display.select_dtypes(include="float").columns
    fmt = {col: "{:.2f}" for col in float_cols}
    return display.style.format(fmt, na_rep="—")


def main() -> None:
    con = _get_con()
    display_filter = app_sidebar.watchlist_selector(con)

    st.title("Forward Screens")

    # ----------------------------------------------------------------
    # Section A: Vendor trends
    # ----------------------------------------------------------------
    st.header("Vendor-provided trends (works immediately)")
    st.caption(
        "These screens use EODHD pre-computed 7/30-day EPS trend deltas and revision counts "
        "from the Earnings.Trend block. No snapshot history required."
    )

    vendor_screen = st.selectbox(
        "Screen",
        [
            "EPS Estimate Revised Up",
            "Net Upward EPS Revisions",
            "Beat and Raise",
        ],
        key="vendor_screen",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Vendor Screen Filters")

    if vendor_screen == "EPS Estimate Revised Up":
        lookback = st.sidebar.selectbox("Lookback", [7, 30], index=1, key="eps_rev_lb")
        min_delta = st.sidebar.number_input(
            "Min EPS delta %", min_value=0.0, max_value=50.0, value=0.0, step=0.5, key="eps_rev_min"
        )
        period_opts = {
            "All": None,
            "Current Q (0q)": "0q",
            "Next Q (+1q)": "+1q",
            "Current Y (0y)": "0y",
            "Next Y (+1y)": "+1y",
        }
        period_lbl = st.sidebar.selectbox("Period", list(period_opts.keys()), key="eps_rev_period")
        df = run_forward_screen(
            con,
            display_filter=display_filter,
            screen="eps_revised_up",
            filters={
                "lookback_days": int(lookback),
                "min_delta_pct": float(min_delta),
                "period_filter": period_opts[period_lbl],
            },
        ).rows
        if df.empty:
            st.info("No tickers match.")
        else:
            cols = [
                c
                for c in ["ticker", "name", "sector", "periods_revised_up", "max_eps_delta_pct"]
                if c in df.columns
            ]
            st.dataframe(_fmt_df(df[cols]), hide_index=True, width="stretch")
            st.caption(f"{len(df)} ticker(s) match.")
            _save_as_watchlist(df, "eps_revised_up")

    elif vendor_screen == "Net Upward EPS Revisions":
        lookback = st.sidebar.selectbox("Lookback", [7, 30], index=1, key="net_rev_lb")
        min_net = st.sidebar.number_input(
            "Min net upward revisions",
            min_value=1,
            max_value=100,
            value=3,
            step=1,
            key="net_rev_min",
        )
        period_opts = {
            "All": None,
            "Current Q (0q)": "0q",
            "Next Q (+1q)": "+1q",
            "Current Y (0y)": "0y",
            "Next Y (+1y)": "+1y",
        }
        period_lbl = st.sidebar.selectbox("Period", list(period_opts.keys()), key="net_rev_period")
        df = run_forward_screen(
            con,
            display_filter=display_filter,
            screen="net_upward_eps_revisions",
            filters={
                "lookback_days": int(lookback),
                "min_net": int(min_net),
                "period_filter": period_opts[period_lbl],
            },
        ).rows
        if df.empty:
            st.info("No tickers match.")
        else:
            cols = [
                c
                for c in [
                    "ticker",
                    "name",
                    "sector",
                    "net_revisions",
                    "revisions_up",
                    "revisions_down",
                ]
                if c in df.columns
            ]
            st.dataframe(_fmt_df(df[cols]), hide_index=True, width="stretch")
            st.caption(f"{len(df)} ticker(s) match.")
            _save_as_watchlist(df, "net_revisions")

    elif vendor_screen == "Beat and Raise":
        min_surprise = st.sidebar.number_input(
            "Min EPS surprise %", min_value=0.0, max_value=50.0, value=2.0, step=0.5, key="bnr_surp"
        )
        min_fwd_delta = st.sidebar.number_input(
            "Min fwd EPS delta %", min_value=0.0, max_value=20.0, value=0.0, step=0.5, key="bnr_fwd"
        )
        df = run_forward_screen(
            con,
            display_filter=display_filter,
            screen="beat_and_revise",
            filters={
                "min_surprise_pct": float(min_surprise),
                "min_eps_delta_pct": float(min_fwd_delta),
            },
        ).rows
        if df.empty:
            st.info("No tickers match.")
        else:
            cols = [
                c
                for c in ["ticker", "name", "sector", "surprise_percent", "eps_delta_pct", "period"]
                if c in df.columns
            ]
            st.dataframe(_fmt_df(df[cols]), hide_index=True, width="stretch")
            st.caption(f"{len(df)} ticker(s) match.")
            _save_as_watchlist(df, "beat_raise")

    st.markdown("---")

    # ----------------------------------------------------------------
    # Section B: Snapshot history
    # ----------------------------------------------------------------
    st.header(f"Snapshot history screens (requires >= {MIN_HISTORY_DAYS} days)")
    st.caption(
        "These screens compare the latest analyst snapshot to one N days ago. "
        f"Tickers with fewer than {MIN_HISTORY_DAYS} daily snapshots are excluded automatically."
    )

    history_screen = st.selectbox(
        "Screen",
        ["Consensus Rating Shift", "Target Price Raised"],
        key="history_screen",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("History Screen Filters")

    if history_screen == "Consensus Rating Shift":
        lookback = st.sidebar.number_input(
            "Lookback days", min_value=7, max_value=365, value=30, step=7, key="rating_lb"
        )
        min_shift = st.sidebar.number_input(
            "Min rating shift", min_value=0.1, max_value=4.0, value=0.5, step=0.1, key="rating_min"
        )
        result = run_forward_screen(
            con,
            display_filter=display_filter,
            screen="consensus_rating_shift",
            filters={
                "lookback_days": int(lookback),
                "min_shift": float(min_shift),
                "min_history_days": MIN_HISTORY_DAYS,
            },
        )
        df, n_excluded = result.rows, result.excluded_count
        if n_excluded:
            st.info(
                f"{n_excluded} ticker(s) excluded — insufficient snapshot history (< {MIN_HISTORY_DAYS} days)."
            )
        if df.empty:
            st.info("No tickers with significant rating shifts.")
        else:
            cols = [
                c
                for c in ["ticker", "name", "sector", "rating_now", "rating_then", "rating_shift"]
                if c in df.columns
            ]
            st.dataframe(_fmt_df(df[cols]), hide_index=True, width="stretch")
            st.caption(
                f"{len(df)} ticker(s) match. Rating scale: 1 = Strong Buy, 5 = Strong Sell. "
                "Negative shift = upgrade."
            )
            _save_as_watchlist(df, "rating_shift")

    elif history_screen == "Target Price Raised":
        lookback = st.sidebar.number_input(
            "Lookback days", min_value=7, max_value=365, value=30, step=7, key="tp_lb"
        )
        min_change = st.sidebar.number_input(
            "Min TP change %", min_value=0.1, max_value=50.0, value=5.0, step=0.5, key="tp_min"
        )
        result = run_forward_screen(
            con,
            display_filter=display_filter,
            screen="target_price_raised",
            filters={
                "lookback_days": int(lookback),
                "min_change_pct": float(min_change),
                "min_history_days": MIN_HISTORY_DAYS,
            },
        )
        df, n_excluded = result.rows, result.excluded_count
        if n_excluded:
            st.info(
                f"{n_excluded} ticker(s) excluded — insufficient snapshot history (< {MIN_HISTORY_DAYS} days)."
            )
        if df.empty:
            st.info("No tickers with target price raised by that threshold.")
        else:
            cols = [
                c
                for c in ["ticker", "name", "sector", "tp_now", "tp_then", "tp_change_pct"]
                if c in df.columns
            ]
            st.dataframe(_fmt_df(df[cols]), hide_index=True, width="stretch")
            st.caption(f"{len(df)} ticker(s) match.")
            _save_as_watchlist(df, "tp_raised")


main()
