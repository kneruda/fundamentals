"""
Home page — universe summary table with conditional formatting.
"""

import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.app import queries
from src.app import sidebar as app_sidebar

load_dotenv()

st.set_page_config(
    page_title="Fundamentals Dashboard",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)


_COLUMN_FORMATS: dict[str, str] = {
    "price": "${:.2f}",
    "pct_1d": "{:.2f}%",
    "mktcap_b": "${:.1f}B",
    "pe_trailing": "{:.1f}",
    "pe_forward": "{:.1f}",
    "ps_trailing": "{:.1f}",
    "pb_trailing": "{:.1f}",
    "ev_ebitda_trailing": "{:.1f}",
    "rev_yoy_pct": "{:.1f}%",
    "eps_yoy_pct": "{:.1f}%",
    "div_yield_pct": "{:.2f}%",
    "consensus_rating": "{:.2f}",
    "target_price": "${:.2f}",
    "target_upside_pct": "{:.1f}%",
}

_COLUMN_LABELS: dict[str, str] = {
    "ticker": "Ticker",
    "name": "Name",
    "sector": "Sector",
    "price": "Price",
    "pct_1d": "1D %",
    "mktcap_b": "Mkt Cap ($B)",
    "pe_trailing": "P/E",
    "pe_forward": "Fwd P/E",
    "ps_trailing": "P/S",
    "pb_trailing": "P/B",
    "ev_ebitda_trailing": "EV/EBITDA",
    "rev_yoy_pct": "Rev YoY %",
    "eps_yoy_pct": "EPS YoY %",
    "div_yield_pct": "Div Yield %",
    "consensus_rating": "Rating",
    "target_price": "Target",
    "target_upside_pct": "Upside %",
}

# Columns where higher is better (green on high end).
_HIGH_GOOD = {"rev_yoy_pct", "eps_yoy_pct", "target_upside_pct", "div_yield_pct"}
# Columns where lower is better (green on low end). Consensus rating: 1 = Strong Buy.
_LOW_GOOD = {
    "pe_trailing",
    "pe_forward",
    "ps_trailing",
    "pb_trailing",
    "ev_ebitda_trailing",
    "consensus_rating",
}


@st.cache_resource
def _get_con():
    return queries.open_warehouse()


@st.cache_data
def _universe_summary(_con, mtime: float) -> pd.DataFrame:
    return queries.universe_summary(_con)


def _style_table(df: pd.DataFrame):
    """Apply formatting + conditional gradients on the (already-renamed) display DataFrame."""
    display_format = {_COLUMN_LABELS.get(k, k): v for k, v in _COLUMN_FORMATS.items()}
    style = df.style.format(display_format, na_rep="—")

    for col_key in _HIGH_GOOD:
        col = _COLUMN_LABELS.get(col_key, col_key)
        if col in df.columns and df[col].notna().any():
            style = style.background_gradient(cmap="RdYlGn", subset=[col], axis=0)
    for col_key in _LOW_GOOD:
        col = _COLUMN_LABELS.get(col_key, col_key)
        if col in df.columns and df[col].notna().any():
            style = style.background_gradient(cmap="RdYlGn_r", subset=[col], axis=0)
    return style


def main() -> None:
    con = _get_con()
    mtime = queries.warehouse_mtime()
    updated = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else "—"

    display_filter = app_sidebar.watchlist_selector(con)

    st.title("Fundamentals Dashboard")
    st.caption(f"Warehouse last updated: {updated}")

    df = _universe_summary(con, mtime)
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)].reset_index(drop=True)

    if df.empty:
        st.info("No active tickers in universe. Add tickers on the Universe page.")
        return

    display_df = df.rename(columns=_COLUMN_LABELS)
    display_cols = [
        _COLUMN_LABELS[c] for c in _COLUMN_LABELS if _COLUMN_LABELS[c] in display_df.columns
    ]
    display_df = display_df[display_cols]

    st.dataframe(_style_table(display_df), width="stretch", hide_index=True)
    st.caption("Consensus rating: 1 = Strong Buy | 2 = Buy | 3 = Hold | 4 = Sell | 5 = Strong Sell")


main()
