"""
Universe management page — add, remove, and refresh tickers.
"""

import io

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src import universe as univ
from src.app import queries

load_dotenv()

st.set_page_config(page_title="Universe", layout="wide")


@st.cache_resource
def _get_con():
    return queries.open_warehouse()


@st.cache_data
def _universe_list(_con, mtime: float):
    return queries.universe_management_list(_con)


@st.cache_data
def _snapshot_coverage(_con, mtime: float):
    return queries.snapshot_coverage(_con)


def _clear_cache() -> None:
    st.cache_data.clear()


def main() -> None:
    con = _get_con()
    mtime = queries.warehouse_mtime()

    st.title("Universe Management")

    df = _universe_list(con, mtime)

    # ---- Current universe table ----
    st.subheader("Current Universe")
    if df.empty:
        st.info("No tickers in universe yet.")
    else:
        display = df[
            [
                "ticker", "name", "sector", "added_at",
                "last_load_at", "load_status", "price_start", "price_end",
                "active", "notes",
            ]
        ].copy()
        display.columns = [
            "Ticker", "Name", "Sector", "Added",
            "Last Load", "Status", "Price Start", "Price End",
            "Active", "Notes",
        ]
        st.dataframe(display, hide_index=True, width="stretch")

    # ---- Snapshot coverage ----
    st.subheader("Analyst Snapshot Coverage")
    st.caption(
        "Forward analyst data is captured once per day. "
        "Forward-looking screens require at least 30 days of history."
    )
    cov = _snapshot_coverage(con, mtime)
    if cov.empty:
        st.info("No active tickers yet.")
    else:
        cov_display = cov.rename(
            columns={
                "ticker": "Ticker",
                "first_snapshot": "First Snapshot",
                "last_snapshot": "Last Snapshot",
                "n_days": "Days Collected",
                "days_since_last": "Days Since Last",
            }
        )
        st.dataframe(cov_display, hide_index=True, width="stretch")

    # ---- Add ticker form ----
    st.subheader("Add Ticker")
    with st.form("add_ticker_form", clear_on_submit=True):
        col_t, col_n = st.columns([1, 2])
        new_ticker = col_t.text_input("Ticker symbol", placeholder="e.g. AAPL")
        notes = col_n.text_input("Notes (optional)", placeholder="e.g. Added for earnings play")
        submitted = st.form_submit_button("Add Ticker")

    if submitted:
        ticker_clean = new_ticker.strip().upper()
        if not ticker_clean:
            st.warning("Enter a ticker symbol.")
        else:
            with st.spinner(f"Adding {ticker_clean} — fetching and ingesting all history..."):
                try:
                    univ.add_ticker(con, ticker_clean, notes.strip() or None)
                    _clear_cache()
                    st.success(f"{ticker_clean} added successfully.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to add {ticker_clean}: {exc}")

    # ---- Bulk add ----
    st.subheader("Bulk Add Tickers")
    st.caption(
        "Paste tickers one per line, or upload a .txt file. "
        "Lines starting with # and blank lines are ignored. "
        "Non-US tickers need the exchange suffix (e.g. SHOP.TO)."
    )

    bulk_text = st.text_area(
        "Tickers (one per line)",
        height=120,
        placeholder="AAPL\nMSFT\nGOOG",
        key="bulk_text",
    )
    uploaded_file = st.file_uploader("Or upload a .txt file", type=["txt"], key="bulk_file")
    bulk_submitted = st.button("Add All", key="bulk_submit")

    if bulk_submitted:
        raw_text = bulk_text or ""
        if uploaded_file is not None:
            raw_text = io.StringIO(uploaded_file.read().decode("utf-8", errors="replace")).read()

        tickers = univ.parse_tickers(raw_text)
        if not tickers:
            st.warning("No valid ticker symbols found.")
        else:
            results: list[tuple[str, bool, str]] = []
            progress = st.progress(0, text="Starting...")
            for i, ticker in enumerate(tickers):
                progress.progress((i + 1) / len(tickers), text=f"Processing {ticker}...")
                was_present = (
                    con.execute(
                        "SELECT COUNT(*) FROM universe WHERE ticker = ?", [ticker]
                    ).fetchone()[0]
                    > 0
                )
                try:
                    univ.add_ticker(con, ticker)
                    msg = "already present, refreshed" if was_present else "added"
                    results.append((ticker, True, msg))
                except Exception as exc:
                    results.append((ticker, False, str(exc)))
            progress.empty()
            _clear_cache()

            result_df = pd.DataFrame(results, columns=["Ticker", "OK", "Message"])
            n_ok = result_df["OK"].sum()
            n_fail = len(result_df) - n_ok
            if n_fail == 0:
                st.success(f"All {n_ok} ticker(s) processed successfully.")
            else:
                st.warning(f"{n_ok} succeeded, {n_fail} failed.")
            st.dataframe(result_df, hide_index=True, width="stretch")
            st.rerun()

    # ---- Per-ticker actions ----
    active_tickers = df[df["active"]]["ticker"].tolist() if not df.empty else []
    inactive_tickers = df[~df["active"]]["ticker"].tolist() if not df.empty else []

    if active_tickers:
        st.subheader("Remove or Refresh Active Tickers")
        st.caption("Removing is a soft delete — historical data is preserved.")

        for ticker in active_tickers:
            col_name, col_remove, col_refresh = st.columns([3, 1, 1])
            row = df[df["ticker"] == ticker].iloc[0]
            col_name.write(f"**{ticker}** — {row.get('name') or '—'}")

            if col_remove.button("Remove", key=f"remove_{ticker}"):
                univ.remove_ticker(con, ticker)
                _clear_cache()
                st.success(f"{ticker} removed from active universe.")
                st.rerun()

            if col_refresh.button("Refresh", key=f"refresh_{ticker}"):
                with st.spinner(f"Re-ingesting {ticker}..."):
                    try:
                        univ.add_ticker(con, ticker)
                        _clear_cache()
                        st.success(f"{ticker} refreshed.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Refresh failed for {ticker}: {exc}")

    if inactive_tickers:
        with st.expander(f"Inactive tickers ({len(inactive_tickers)})"):
            for ticker in inactive_tickers:
                col_name, col_reactivate = st.columns([4, 1])
                col_name.write(f"{ticker}")
                if col_reactivate.button("Re-add", key=f"readd_{ticker}"):
                    with st.spinner(f"Re-adding {ticker}..."):
                        try:
                            univ.add_ticker(con, ticker)
                            _clear_cache()
                            st.success(f"{ticker} re-added.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed: {exc}")


main()
