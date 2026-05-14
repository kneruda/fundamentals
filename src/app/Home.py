"""
Home page — universe summary table with conditional formatting.
"""

import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pandas.io.formats.style import Styler

from src.app import queries
from src.app import sidebar as app_sidebar

load_dotenv()

st.set_page_config(
    page_title="Fundamentals Dashboard",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)


@st.cache_resource
def _get_con():
    return queries.open_warehouse()


@st.cache_data
def _universe_summary(_con, mtime: float) -> pd.DataFrame:
    return queries.universe_summary(_con)


def _style_table(df: pd.DataFrame) -> Styler:
    format_map = {
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

    style = df.style.format(format_map, na_rep="—")

    # Higher is better (green = high)
    for col in ["rev_yoy_pct", "eps_yoy_pct", "target_upside_pct", "div_yield_pct"]:
        if col in df.columns and df[col].notna().any():
            style = style.background_gradient(cmap="RdYlGn", subset=[col], axis=0)

    # Lower is better (green = low) for valuation multiples
    for col in ["pe_trailing", "pe_forward", "ps_trailing", "pb_trailing", "ev_ebitda_trailing"]:
        if col in df.columns and df[col].notna().any():
            style = style.background_gradient(cmap="RdYlGn_r", subset=[col], axis=0)

    # Consensus: 1=Strong Buy (green), 5=Strong Sell (red)
    if "consensus_rating" in df.columns and df["consensus_rating"].notna().any():
        style = style.background_gradient(cmap="RdYlGn_r", subset=["consensus_rating"], axis=0)

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

    rename = {
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
    display_df = df.rename(columns=rename)
    display_cols = list(rename.values())
    # Only keep columns that exist after rename
    display_cols = [c for c in display_cols if c in display_df.columns]

    style = _style_table(df)
    style = style.set_table_styles([])  # clear defaults so column names render from rename below

    # Apply renamed columns for display (re-apply formatting on renamed df)
    display_format = {
        rename.get(k, k): v
        for k, v in {
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
        }.items()
    }

    display_df_subset = display_df[display_cols]
    display_style = display_df_subset.style.format(display_format, na_rep="—")

    # Gradient on renamed columns
    for col_orig, col_disp in rename.items():
        if col_disp not in display_df_subset.columns:
            continue
        if not display_df_subset[col_disp].notna().any():
            continue
        if col_orig in ("rev_yoy_pct", "eps_yoy_pct", "target_upside_pct", "div_yield_pct"):
            display_style = display_style.background_gradient(
                cmap="RdYlGn", subset=[col_disp], axis=0
            )
        elif col_orig in (
            "pe_trailing",
            "pe_forward",
            "ps_trailing",
            "pb_trailing",
            "ev_ebitda_trailing",
            "consensus_rating",
        ):
            display_style = display_style.background_gradient(
                cmap="RdYlGn_r", subset=[col_disp], axis=0
            )

    st.dataframe(display_style, width="stretch", hide_index=True)

    st.caption("Consensus rating: 1 = Strong Buy | 2 = Buy | 3 = Hold | 4 = Sell | 5 = Strong Sell")


main()
