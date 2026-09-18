"""Shared sidebar watchlist selector — call from every page."""

import duckdb
import streamlit as st

from src.services.watchlists import available_watchlists, display_filter_for_watchlist


def watchlist_selector(con: duckdb.DuckDBPyConnection) -> list[str] | None:
    """Render the sidebar watchlist selectbox and return the display_filter list (or None).

    Persists the selected watchlist_id in st.session_state["active_watchlist_id"].
    Returns None when "Full universe" is selected; returns a list of ticker strings otherwise.
    """
    watchlists = available_watchlists(con)
    options = ["Full universe"] + watchlists["name"].tolist()

    # Determine default selection from session state
    default_idx = 0
    active_id = st.session_state.get("active_watchlist_id")
    if active_id is not None and not watchlists.empty:
        match = watchlists[watchlists["watchlist_id"] == active_id]
        if not match.empty:
            name = match.iloc[0]["name"]
            if name in options:
                default_idx = options.index(name)

    selected = st.sidebar.selectbox(
        "Watchlist", options, index=default_idx, key="watchlist_selector"
    )

    if selected == "Full universe":
        st.session_state["active_watchlist_id"] = None
        return None

    row = watchlists[watchlists["name"] == selected].iloc[0]
    wid = int(row["watchlist_id"])
    st.session_state["active_watchlist_id"] = wid
    return display_filter_for_watchlist(con, wid)
