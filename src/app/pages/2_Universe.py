"""
Universe management page — add, remove, and refresh tickers.
"""

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
        display = df[["ticker", "name", "sector", "added_at", "last_loaded", "active", "notes"]].copy()
        display.columns = ["Ticker", "Name", "Sector", "Added", "Last Loaded", "Active", "Notes"]
        st.dataframe(display, hide_index=True, use_container_width=True)

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
